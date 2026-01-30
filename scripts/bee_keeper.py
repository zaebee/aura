import json
import os
from pathlib import Path

import litellm
import requests
from github import Github


class BeeKeeper:
    def __init__(self) -> None:
        self.github_token = os.getenv("GITHUB_TOKEN")
        self.repo_name = os.getenv("GITHUB_REPOSITORY")
        self.event_path = os.getenv("GITHUB_EVENT_PATH")

        self.gh = None
        self.repo = None
        if self.github_token and self.github_token != "mock":  # nosec
            try:
                self.gh = Github(self.github_token)
                if self.repo_name:
                    self.repo = self.gh.get_repo(self.repo_name)
            except Exception as e:
                print(f"⚠️ Could not initialize GitHub client: {e}")

        self.hive_path = Path("core-service/src/hive")
        self.dna_path = self.hive_path / "dna.py"
        self.allowed_nucleotides = [
            "aggregator.py", "transformer.py", "connector.py",
            "generator.py", "membrane.py", "metabolism.py",
            "dna.py", "__init__.py"
        ]

        # Load persona
        prompt_path = Path("src/prompts/bee_keeper.md")
        self.persona = prompt_path.read_text() if prompt_path.exists() else "You are bee.Keeper, guardian of the Aura Hive."

    def architectural_audit(self) -> list[str]:
        print("🐝 Running Architectural Audit...")
        violations = []

        # 1. Check for unauthorized files in hive directory
        if self.hive_path.exists():
            for file in self.hive_path.iterdir():
                if file.is_file() and file.name not in self.allowed_nucleotides and file.suffix == ".py":
                    violations.append(f"Structural violation: '{file.name}' is not a recognized ATCG nucleotide.")

        # 2. Protocol compliance check using litellm
        if self.dna_path.exists():
            dna_content = self.dna_path.read_text()
            for n_file in ["aggregator.py", "transformer.py", "connector.py", "generator.py"]:
                p = self.hive_path / n_file
                if p.exists():
                    content = p.read_text()
                    prompt = f"""
                    {self.persona}

                    Analyze the following Python code for compliance with the ATCG Protocols defined in dna.py.

                    --- dna.py (Protocols) ---
                    {dna_content}

                    --- {n_file} (Implementation) ---
                    {content}

                    Does this implementation strictly follow the Protocol defined in dna.py?
                    If not, explain why. If it does, say "COMPLIANT".
                    """

                    try:
                        response = litellm.completion(
                            model="gpt-4o-mini", # Defaulting to a small fast model
                            messages=[{"role": "user", "content": prompt}]
                        )
                        result = response.choices[0].message.content
                        if "COMPLIANT" not in result.upper():
                            violations.append(f"Protocol violation in {n_file}: {result}")
                    except Exception as e:
                        print(f"⚠️ Error during LLM audit of {n_file}: {e}")

        return violations

    def honey_check(self) -> None:
        print("🍯 Checking Honey (Metrics)...")
        prometheus_url = os.getenv("PROMETHEUS_URL", "http://prometheus-kube-prometheus-prometheus.monitoring:9090")
        # Query for negotiation success rate
        query = 'sum(rate(negotiation_accepted_total[5m])) / sum(rate(negotiation_total[5m]))'

        try:
            response = requests.get(f"{prometheus_url}/api/v1/query", params={"query": query}, timeout=10)
            response.raise_for_status()
            data = response.json()

            if data["status"] == "success" and data["data"]["result"]:
                success_rate = float(data["data"]["result"][0]["value"][1])
                print(f"📊 Negotiation Success Rate: {success_rate:.2f}")

                if success_rate < 0.7:
                    self.post_hive_alert(f"🚨 Hive Alert! Negotiation success rate is dropping ({success_rate:.2f}). Honey production is low!")
            else:
                print("⚠️ No metrics found for negotiation success rate. Hive is quiet.")
        except Exception as e:
            print(f"⚠️ Could not query Prometheus: {e}")

    def post_hive_alert(self, message: str) -> None:
        print(f"📢 ALERT: {message}")
        if not self.repo:
            print("Skipping GitHub comment (no repo access).")
            return

        try:
            if self.event_path and os.path.exists(self.event_path):
                with open(self.event_path) as f:
                    event_data = json.load(f)

                if "pull_request" in event_data:
                    pr_num = event_data["pull_request"]["number"]
                    self.repo.get_pull(pr_num).create_issue_comment(message)
                    print(f"✅ Posted alert to PR #{pr_num}")
                else:
                    sha = event_data.get("after")
                    if not sha and "head_commit" in event_data:
                        sha = event_data["head_commit"].get("id")

                    if sha:
                        self.repo.get_commit(sha).create_comment(message)
                        print(f"✅ Posted alert to commit {sha}")
            else:
                # Fallback to latest commit on main if no event path
                branch = self.repo.get_branch("main")
                branch.commit.create_comment(message)
                print(f"✅ Posted alert to latest commit on main: {branch.commit.sha}")
        except Exception as e:
            print(f"⚠️ Error posting GitHub comment: {e}")

    def context_sync(self) -> None:
        print("🔄 Synchronizing Context (llms.txt)...")
        proto_dir = Path("proto")
        if not proto_dir.exists():
            print("⚠️ Proto directory not found.")
            return

        proto_files = list(proto_dir.rglob("*.proto"))

        # Determine if we should sync
        should_sync = os.getenv("FORCE_SYNC") == "true"

        if not should_sync:
            try:
                import subprocess  # nosec
                # Check for changes in .proto files in the last commit
                result = subprocess.run(
                    ["git", "diff", "--name-only", "HEAD~1", "HEAD"],
                    capture_output=True,
                    text=True,
                )  # nosec
                if result.returncode == 0:
                    changed = [f for f in result.stdout.splitlines() if f.endswith(".proto")]
                    if changed:
                        print(f"📡 Detected changes in: {', '.join(changed)}")
                        should_sync = True
            except Exception as e:
                print(f"⚠️ Could not check git diff: {e}")
                # Fallback: sync if it's a scheduled run
                if os.getenv("GITHUB_EVENT_NAME") == "schedule":
                    should_sync = True

        if should_sync:
            print(f"Updating llms.txt based on {len(proto_files)} .proto files...")
            self.update_llms_txt(proto_files)
        else:
            print("✨ No .proto changes detected. Context is in sync.")

    def update_llms_txt(self, proto_files: list[Path]) -> None:
        llms_txt_path = Path("llms.txt")
        current_llms_txt = llms_txt_path.read_text() if llms_txt_path.exists() else ""

        proto_contents = ""
        for p in proto_files:
            proto_contents += f"\n--- {p} ---\n{p.read_text()}\n"

        prompt = f"""
        {self.persona}

        The internal Protobuf definitions of the Aura Hive have changed.
        Update the `llms.txt` file to reflect these changes.
        Focus on "Main Tools & Capabilities" and "API Endpoints".

        --- Current llms.txt ---
        {current_llms_txt}

        --- Protobuf Definitions ---
        {proto_contents}

        Return the FULL updated content for `llms.txt`. Do not include any other text or markdown formatting markers.
        """

        try:
            response = litellm.completion(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt}]
            )
            updated_content = response.choices[0].message.content
            # Strip markdown code blocks if present
            if updated_content.startswith("```"):
                lines = updated_content.splitlines()
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines[-1].startswith("```"):
                    lines = lines[:-1]
                updated_content = "\n".join(lines)

            llms_txt_path.write_text(updated_content.strip())
            print("✅ llms.txt updated and synchronized.")
        except Exception as e:
            print(f"⚠️ Error updating llms.txt: {e}")

    def run(self) -> None:
        violations = self.architectural_audit()
        if violations:
            print("❌ Architectural Violations Found:")
            for v in violations:
                print(f"  - {v}")
            self.post_hive_alert("🐝 bee.Keeper has detected architectural impurities in the Hive:\n\n" + "\n".join([f"- {v}" for v in violations]))
        else:
            print("✅ Architecture is pure.")

        self.honey_check()
        self.context_sync()

if __name__ == "__main__":
    keeper = BeeKeeper()
    keeper.run()
