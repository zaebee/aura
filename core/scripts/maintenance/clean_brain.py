#!/usr/bin/env python3
import json
import re
from pathlib import Path


def clean_markdown(text: str) -> str:
    """Remove Markdown code blocks from string."""
    if not isinstance(text, str):
        return text
    # Remove ```json and ``` markers with a single robust regex
    text = re.sub(r"^\s*```(?:json)?\s*|\s*```\s*$", "", text, flags=re.IGNORECASE)
    return text.strip()


def process_demo(demo: dict) -> dict:
    """Process a single demo: unify keys and clean markdown."""
    new_demo = {}

    # Map reasoning -> thought, response -> action, ideal_response -> action and keep others
    for k, v in demo.items():
        target_key = k
        if k in ["reasoning", "thought"]:
            target_key = "thought"
        elif k in ["response", "ideal_response", "action"]:
            target_key = "action"

        # Check for key collisions to avoid silent data loss
        if target_key in new_demo:
            raise ValueError(
                f"Data collision: demo already has '{target_key}' key. "
                f"Original keys: {list(demo.keys())}"
            )

        # If action is a dict, convert to JSON string before cleaning
        if target_key == "action" and isinstance(v, dict):
            v = json.dumps(v, indent=2)

        # Clean markdown if it's a string
        if isinstance(v, str):
            v = clean_markdown(v)

        new_demo[target_key] = v

    return new_demo


def clean_brain_file(filepath: str):
    """Parse, clean and unify JSON data files."""
    path = Path(filepath)
    if not path.exists():
        print(f"Error: File {filepath} not found.")
        return

    with open(path, encoding="utf-8") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError as e:
            print(f"Error decoding JSON: {e}")
            return

    # Case 1: DSPy compiled program (dict with 'negotiate' field)
    if isinstance(data, dict) and "negotiate" in data:
        for field in ["demos", "train", "traces"]:
            if field in data["negotiate"] and isinstance(
                data["negotiate"][field], list
            ):
                print(f"Processing {filepath} -> negotiate.{field}...")
                data["negotiate"][field] = [
                    process_demo(entry) for entry in data["negotiate"][field]
                ]

    # Case 2: Training data (list of scenarios with 'turns')
    elif isinstance(data, list):
        print(f"Processing {filepath} scenarios...")
        for scenario in data:
            if "turns" in scenario and isinstance(scenario["turns"], list):
                scenario["turns"] = [process_demo(turn) for turn in scenario["turns"]]

    # Save cleaned data
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"Successfully cleaned {filepath}")


if __name__ == "__main__":
    # Target files
    targets = ["core/data/aura_brain.json", "core/data/negotiation_training.json"]
    for target in targets:
        if Path(target).exists():
            clean_brain_file(target)
