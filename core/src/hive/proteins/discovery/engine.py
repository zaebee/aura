import re
from typing import Any, cast

import dspy
import structlog
from github import Github
from github.ContentFile import ContentFile
from github.Repository import Repository

logger = structlog.get_logger(__name__)

# --- DSPy Signatures ---


class AnalyzeCompatibility(dspy.Signature):
    """
    Analyze the DNA (README, API definitions, Proto files, config files) of a software repository
    to determine its compatibility with the Aura Hive ecosystem.
    """

    repo_context = dspy.InputField(
        desc="Content of README, proto files, API definitions, and configuration files like pyproject.toml, go.mod, docker-compose.yml"
    )

    substrate = dspy.OutputField(
        desc="Primary programming language (Python/Go/Rust/etc.)"
    )
    nervous_system = dspy.OutputField(
        desc="Communication protocol (REST/gRPC/NATS/etc.)"
    )
    valence = dspy.OutputField(
        desc="Trading capability (Does it have assets or compute?)"
    )
    architecture_type = dspy.OutputField(desc="Monolith, Microservices, or Agentic")
    detected_interfaces = dspy.OutputField(
        desc="Comma-separated list of detected interfaces (e.g., gRPC, REST, NATS)"
    )
    compatibility_score = dspy.OutputField(
        desc="Score from 0.0 to 1.0 (Hill Equation based)"
    )
    reasoning = dspy.OutputField(
        desc="Brief explanation of the compatibility assessment"
    )


class GenerateSymbioticProposal(dspy.Signature):
    """
    Generate a compelling 'First Contact' proposal for a compatible AI agent or system.
    The proposal should highlight mutual benefits and technical peering possibilities.
    """

    repo_context = dspy.InputField()
    compatibility_analysis = dspy.InputField()

    proposal = dspy.OutputField(
        desc="A symbiotic proposal message (e.g., 'I see you implement OpenClaw...')"
    )


# --- Engine Logic ---


async def scan_github(query: str, github_client: Github) -> list[dict[str, Any]]:
    """Search for repositories on GitHub."""
    logger.info("scanning_github", query=query)
    repos = github_client.search_repositories(query=query)
    results: list[dict[str, Any]] = []
    # Limit to top 5 for efficiency
    repo: Repository
    for repo in repos[:5]:
        results.append(
            {
                "name": repo.full_name,
                "url": repo.html_url,
                "description": repo.description,
                "stars": repo.stargazers_count,
            }
        )
    return results


async def sequence_genome(repo_url: str, github_client: Github) -> str:
    """Read README.md, proto files, and API definitions from a repository."""
    repo_name = repo_url.replace("https://github.com/", "")
    logger.info("sequencing_genome", repo=repo_name)
    repo: Repository = github_client.get_repo(repo_name)

    context_parts: list[str] = []

    # 1. Try to get README
    try:
        readme = repo.get_readme()
        context_parts.append(
            f"--- README ---\n{readme.decoded_content.decode('utf-8')[:2000]}"
        )
    except Exception:
        logger.warning("readme_not_found", repo=repo_name)

    # 2. Scan Metabolic Requirements (Dependencies)
    for dep_file in ["pyproject.toml", "go.mod", "package.json", "requirements.txt"]:
        try:
            content = repo.get_contents(dep_file)
            if isinstance(content, list):
                continue
            context_parts.append(
                f"--- METABOLIC REQUIREMENTS ({dep_file}) ---\n{content.decoded_content.decode('utf-8')[:1000]}"
            )
        except Exception:
            pass

    # 3. Scan Nervous System (Interfaces)
    # Proto files
    try:
        protos = github_client.search_code(query=f"extension:proto repo:{repo_name}")
        if protos.totalCount > 0:
            context_parts.append("--- NERVOUS SYSTEM (PROTO FILES) ---")
            p: ContentFile
            for p in protos[:3]:
                context_parts.append(
                    f"File: {p.path}\n{p.decoded_content.decode('utf-8')[:1000]}"
                )
    except Exception as e:
        logger.warning("proto_search_failed", repo=repo_name, error=str(e))

    # OpenAPI / Swagger
    try:
        api_defs = github_client.search_code(
            query=f"(filename:openapi.yaml OR filename:swagger.json) repo:{repo_name}"
        )
        if api_defs.totalCount > 0:
            context_parts.append("--- NERVOUS SYSTEM (API DEFINITIONS) ---")
            ad: ContentFile
            for ad in api_defs[:2]:
                context_parts.append(
                    f"File: {ad.path}\n{ad.decoded_content.decode('utf-8')[:1000]}"
                )
    except Exception as e:
        logger.warning("api_def_search_failed", repo=repo_name, error=str(e))

    # 4. Scan Organism Structure (Docker)
    try:
        docker_compose = repo.get_contents("docker-compose.yml")
        if not isinstance(docker_compose, list):
            context_parts.append(
                f"--- ORGANISM STRUCTURE (docker-compose.yml) ---\n{docker_compose.decoded_content.decode('utf-8')[:1000]}"
            )
    except Exception:
        pass

    return "\n\n".join(context_parts)


async def analyze_compatibility(repo_context: str) -> dict[str, Any]:
    """Use DSPy to determine compatibility."""
    logger.info("analyzing_compatibility")
    predictor = dspy.Predict(AnalyzeCompatibility)
    result = predictor(repo_context=repo_context)

    # Parse detected_interfaces string to list
    interfaces: list[str] = []
    if result.detected_interfaces:
        interfaces = [
            i.strip()
            for i in re.split(r"[,;]", result.detected_interfaces)
            if i.strip()
        ]

    return {
        "substrate": result.substrate,
        "nervous_system": result.nervous_system,
        "valence": result.valence,
        "architecture_type": result.architecture_type or "Unknown",
        "detected_interfaces": interfaces,
        "compatibility_score": (
            float(result.compatibility_score) if result.compatibility_score else 0.0
        ),
        "reasoning": result.reasoning,
    }


async def generate_proposal(repo_context: str, analysis: dict[str, Any]) -> str:
    """Generate a symbiotic proposal."""
    logger.info("generating_proposal")
    predictor = dspy.Predict(GenerateSymbioticProposal)
    result = predictor(repo_context=repo_context, compatibility_analysis=str(analysis))
    return cast(str, result.proposal)
