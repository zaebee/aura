import os
import subprocess  # nosec B404
import sys
from pathlib import Path
from typing import Any

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class CustomBuildHook(BuildHookInterface):
    def initialize(self, version: str, build_data: Any) -> None:
        project_root = Path(self.root)

        possible_proto_paths = [
            project_root / "proto",
            project_root.parent.parent / "proto",
        ]

        proto_dir = None
        for p in possible_proto_paths:
            if p.exists():
                proto_dir = p.absolute()
                break

        if not proto_dir:
            print(f"⚠️ DNA Source (proto) not found in: {possible_proto_paths}")
            return

        out_dir = project_root / "src" / "aura_core" / "gen"
        out_dir.mkdir(parents=True, exist_ok=True)

        print(f"🧬 Bio-Digital Transcription: {proto_dir} -> {out_dir}")

        try:
            import grpc_tools.protoc  # noqa
        except ImportError:
            print("❌ Error: 'grpcio-tools' is missing in build-system.requires")
            return

        proto_file = proto_dir / "aura" / "dna" / "v1" / "dna.proto"

        try:
            result = subprocess.run(  # nosec B603
                [
                    sys.executable,
                    "-m",
                    "grpc_tools.protoc",
                    f"--proto_path={proto_dir}",
                    f"--python_betterproto_out={out_dir}",
                    str(proto_file),
                ],
                capture_output=True,
                text=True,
            )

            if result.returncode != 0:
                print(f"❌ Protoc Error:\n{result.stderr}")
                raise RuntimeError(f"Protoc failed with status {result.returncode}")

            self._ensure_init_files(out_dir)
            print("✅ DNA successfully expressed.")

        except Exception as e:
            print(f"❌ Critical Transcription failure: {e}")
            raise e

    def _ensure_init_files(self, base_path: Path) -> None:
        for root, dirs, _files in os.walk(base_path):
            for d in dirs:
                init_file = Path(root) / d / "__init__.py"
                if not init_file.exists():
                    init_file.touch()
            root_init = Path(base_path) / "__init__.py"
            if not root_init.exists():
                root_init.touch()
