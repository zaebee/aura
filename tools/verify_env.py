#!/usr/bin/env python3
"""
Environment Variable Verification Script

Validates synchronization between:
- Pydantic configuration files
- Helm deployment templates
- CI/CD secret mappings

Usage:
    uv run python tools/verify_env.py
"""

import ast
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# ANSI color codes
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BLUE = "\033[94m"
RESET = "\033[0m"


@dataclass
class EnvVar:
    """Represents an environment variable."""

    name: str
    required: bool
    default_value: Any
    source_file: str
    has_localhost_default: bool = False


@dataclass
class VerificationReport:
    """Verification results."""

    errors: list[str]
    warnings: list[str]
    info: list[str]
    success: list[str]


def parse_pydantic_config(file_path: Path) -> list[EnvVar]:
    """Parse a Pydantic config file to extract environment variables."""
    env_vars = []

    try:
        with open(file_path) as f:
            content = f.read()
            tree = ast.parse(content)

        # Find the env_prefix in SettingsConfigDict
        env_prefix = ""
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "model_config":
                        if isinstance(node.value, ast.Call):
                            for keyword in node.value.keywords:
                                if keyword.arg == "env_prefix":
                                    if isinstance(keyword.value, ast.Constant):
                                        env_prefix = keyword.value.value

        # Find class definitions that inherit from BaseModel or BaseSettings
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                bases = [
                    base.id if isinstance(base, ast.Name) else None
                    for base in node.bases
                ]
                if "BaseModel" in bases or "BaseSettings" in bases:
                    # Extract fields
                    for item in node.body:
                        if isinstance(item, ast.AnnAssign) and isinstance(
                            item.target, ast.Name
                        ):
                            field_name = item.target.id

                            # Skip private fields
                            if field_name.startswith("_"):
                                continue

                            # Check if field has default value
                            has_default = item.value is not None
                            default_value = None

                            if has_default and isinstance(item.value, ast.Constant):
                                default_value = item.value.value
                            elif has_default and isinstance(item.value, ast.Call):
                                # Field() call
                                if item.value.args:
                                    if isinstance(item.value.args[0], ast.Constant):
                                        default_value = item.value.args[0].value

                            # Build ENV variable name
                            class_name = node.name.replace("Settings", "").lower()
                            if env_prefix:
                                # Use explicit prefix
                                env_var_name = f"{env_prefix}{field_name}".upper()
                            elif class_name and class_name != "base":
                                # Use class name as section
                                env_var_name = (
                                    f"AURA_{class_name}__{field_name}".upper()
                                )
                            else:
                                env_var_name = field_name.upper()

                            # Check for localhost in defaults
                            has_localhost = False
                            if default_value and isinstance(default_value, str):
                                has_localhost = "localhost" in default_value.lower()

                            # Field is required if no default (or default=None)
                            required = not has_default or default_value is None

                            env_vars.append(
                                EnvVar(
                                    name=env_var_name,
                                    required=required,
                                    default_value=default_value,
                                    source_file=str(file_path.relative_to(Path.cwd())),
                                    has_localhost_default=has_localhost,
                                )
                            )

    except Exception as e:
        print(f"{YELLOW}⚠ Failed to parse {file_path}: {e}{RESET}")

    return env_vars


def parse_helm_templates(templates_dir: Path) -> dict[str, list[str]]:
    """Parse Helm templates to extract environment variable references."""
    env_vars_by_service = {}

    for template_file in templates_dir.glob("*.yaml"):
        # Extract service name from filename (e.g., "core-deployment.yaml" -> "core")
        service_name = template_file.stem.replace("-deployment", "").replace(
            "-statefulset", ""
        )

        env_vars = []

        try:
            with open(template_file) as f:
                content = f.read()

            # Find all "- name: ENV_VAR" patterns
            env_pattern = re.compile(r"- name:\s+([A-Z_]+)")
            matches = env_pattern.findall(content)
            env_vars.extend(matches)

        except Exception as e:
            print(f"{YELLOW}⚠ Failed to parse {template_file}: {e}{RESET}")

        if env_vars:
            env_vars_by_service[service_name] = sorted(set(env_vars))

    return env_vars_by_service


def parse_ci_cd_secrets(ci_cd_file: Path) -> dict[str, str]:
    """Parse CI/CD workflow to extract secret mappings."""
    secrets = {}

    try:
        with open(ci_cd_file) as f:
            content = f.read()

        # Find kubectl create secret command
        secret_pattern = re.compile(r'--from-literal=([^=]+)="\$([^"]+)"')
        matches = secret_pattern.findall(content)

        for k8s_key, github_secret_var in matches:
            secrets[k8s_key] = github_secret_var

    except Exception as e:
        print(f"{YELLOW}⚠ Failed to parse {ci_cd_file}: {e}{RESET}")

    return secrets


def verify_environment() -> VerificationReport:
    """Run comprehensive environment variable verification."""
    report = VerificationReport(errors=[], warnings=[], info=[], success=[])

    # Parse Core service configs
    core_config_dir = Path("core/src/config")
    core_env_vars = []
    if core_config_dir.exists():
        for config_file in core_config_dir.glob("*.py"):
            if config_file.name != "__init__.py":
                vars_found = parse_pydantic_config(config_file)
                core_env_vars.extend(vars_found)

    # Parse Gateway config
    gateway_config_file = Path("api-gateway/src/config.py")
    gateway_env_vars = []
    if gateway_config_file.exists():
        gateway_env_vars = parse_pydantic_config(gateway_config_file)

    # Parse Telegram config
    telegram_config_file = Path("adapters/telegram-bot/src/config.py")
    telegram_env_vars = []
    if telegram_config_file.exists():
        telegram_env_vars = parse_pydantic_config(telegram_config_file)

    # Parse Helm templates
    helm_templates_dir = Path("deploy/aura/templates")
    helm_env_vars = {}
    if helm_templates_dir.exists():
        helm_env_vars = parse_helm_templates(helm_templates_dir)

    # Parse CI/CD secrets
    ci_cd_file = Path(".github/workflows/ci-cd.yaml")
    ci_cd_secrets = {}
    if ci_cd_file.exists():
        ci_cd_secrets = parse_ci_cd_secrets(ci_cd_file)

    # --- Validation Checks ---

    # Check 1: Core Service
    print(f"\n{BLUE}Core Service:{RESET}")
    print(f"  Variables defined: {len(core_env_vars)}")

    required_core = [v for v in core_env_vars if v.required]
    print(f"  Required variables: {len(required_core)}")

    localhost_defaults = [v for v in core_env_vars if v.has_localhost_default]
    if localhost_defaults:
        for var in localhost_defaults:
            report.errors.append(
                f"Core: {var.name} has localhost default in {var.source_file}"
            )
            print(f"  {RED}✗ {var.name} has localhost default{RESET}")
    else:
        report.success.append("Core: No localhost defaults")
        print(f"  {GREEN}✓ No localhost defaults{RESET}")

    # Check 2: Gateway Service
    print(f"\n{BLUE}Gateway Service:{RESET}")
    print(f"  Variables defined: {len(gateway_env_vars)}")

    # Check for AURA_ prefix (should not exist)
    aura_prefixed = [v for v in gateway_env_vars if v.name.startswith("AURA_")]
    if aura_prefixed:
        for var in aura_prefixed:
            report.warnings.append(f"Gateway: {var.name} has AURA_ prefix (unexpected)")
            print(f"  {YELLOW}⚠ {var.name} has AURA_ prefix (unexpected){RESET}")
    else:
        report.info.append("Gateway: No AURA_ prefix (intentional)")
        print(f"  {GREEN}! No AURA_ prefix (intentional){RESET}")

    # Check 3: Telegram Service
    print(f"\n{BLUE}Telegram Service:{RESET}")
    print(f"  Variables defined: {len(telegram_env_vars)}")

    required_telegram = [v for v in telegram_env_vars if v.required]
    print(f"  Required variables: {len(required_telegram)}")

    # Check 4: Helm Templates
    print(f"\n{BLUE}Helm Templates:{RESET}")
    for service, env_vars in helm_env_vars.items():
        print(f"  {service}: {len(env_vars)} variables")
        # List first few
        for env_name in env_vars[:5]:
            print(f"    - {env_name}")
        if len(env_vars) > 5:
            print(f"    ... and {len(env_vars) - 5} more")

    # Check 5: CI/CD Secrets
    print(f"\n{BLUE}CI/CD Secrets:{RESET}")
    print(f"  Total secrets: {len(ci_cd_secrets)}")
    for k8s_key, github_var in sorted(ci_cd_secrets.items()):
        print(f"  {k8s_key} ← ${github_var}")

    # Check for unused secrets
    used_secrets = {
        "telegram-token",
        "api-key",
        "openai-key",
        "secret-encryption-key",
        "solana-private-key",
    }
    unused = set(ci_cd_secrets.keys()) - used_secrets
    if unused:
        for secret in sorted(unused):
            report.warnings.append(f"CI/CD: {secret} is unused")
            print(f"  {YELLOW}⚠ {secret} is unused{RESET}")

    # Check 6: Cross-validation
    print(f"\n{BLUE}Cross-Validation:{RESET}")

    # Check core deployment has required ENV vars
    if "core" in helm_env_vars:
        core_helm_vars = set(helm_env_vars["core"])

        # Check if critical vars are in Helm
        critical_vars = {
            "AURA_DATABASE__URL",
            "AURA_DATABASE__REDIS_URL",
            "AURA_SERVER__HOST",
            "AURA_SERVER__PORT",
        }
        missing_critical = critical_vars - core_helm_vars
        if missing_critical:
            missing_var: str
            for missing_var in sorted(missing_critical):
                report.errors.append(
                    f"Helm: {missing_var} missing from core deployment"
                )
                print(f"  {RED}✗ {missing_var} missing from core deployment{RESET}")
        else:
            report.success.append("Helm: All critical vars present in core deployment")
            print(f"  {GREEN}✓ All critical vars present in core deployment{RESET}")

    # Summary
    print(f"\n{BLUE}{'=' * 60}{RESET}")
    print(f"{BLUE}Summary:{RESET}")
    print(f"  {GREEN}✓ Success: {len(report.success)}{RESET}")
    print(f"  {YELLOW}⚠ Warnings: {len(report.warnings)}{RESET}")
    print(f"  {RED}✗ Errors: {len(report.errors)}{RESET}")
    print(f"  {BLUE}! Info: {len(report.info)}{RESET}")

    if report.errors:
        print(f"\n{RED}Status: NEEDS FIXES{RESET}")
    elif report.warnings:
        print(f"\n{YELLOW}Status: REVIEW WARNINGS{RESET}")
    else:
        print(f"\n{GREEN}Status: ALL CHECKS PASSED{RESET}")

    return report


def main() -> None:
    """Main entry point."""
    print(f"{BLUE}{'=' * 60}{RESET}")
    print(f"{BLUE}Environment Variable Verification Report{RESET}")
    print(f"{BLUE}{'=' * 60}{RESET}")

    report = verify_environment()

    # Detailed output
    if report.errors:
        print(f"\n{RED}Errors:{RESET}")
        for error in report.errors:
            print(f"  {RED}✗ {error}{RESET}")

    if report.warnings:
        print(f"\n{YELLOW}Warnings:{RESET}")
        for warning in report.warnings:
            print(f"  {YELLOW}⚠ {warning}{RESET}")

    if report.info:
        print(f"\n{BLUE}Info:{RESET}")
        for info_msg in report.info:
            print(f"  {BLUE}! {info_msg}{RESET}")

    # Exit code
    if report.errors:
        exit(1)
    else:
        exit(0)


if __name__ == "__main__":
    main()
