import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from hive.proteins.kinetic.engine import KineticEngine


def test_kinetic_engine_identity_mapping():
    engine = KineticEngine(remotion_project_path="./test", output_dir="./test-out")

    # Test Hyundai mapping
    hyundai = engine.synthesize_identity("Hyundai")
    assert hyundai.primary_color == "#003478"
    assert hyundai.style == "Modern"

    # Test Tesla mapping
    tesla = engine.synthesize_identity("Tesla")
    assert tesla.primary_color == "#E81922"
    assert tesla.style == "Minimal"

    # Test Default mapping
    default = engine.synthesize_identity("Unknown")
    assert default.primary_color == "#FFD700"
    assert default.style == "Hive"


@pytest.mark.asyncio
async def test_kinetic_engine_render_command():
    # Mock asyncio.create_subprocess_exec
    with patch("asyncio.create_subprocess_exec") as mock_subprocess:
        mock_process = MagicMock()
        mock_process.communicate = AsyncMock(return_value=(b"output", b""))
        mock_process.returncode = 0
        mock_subprocess.return_value = mock_process

        engine = KineticEngine(
            remotion_project_path="/tmp/remotion", output_dir="/tmp/artifacts"
        )

        # Mock os.path.exists and os.remove to avoid real file system side effects
        with (
            patch("os.path.exists", return_value=True),
            patch("os.remove"),
            patch("os.makedirs"),
        ):
            props = {"asset_id": "123", "name": "Test Car"}
            await engine.render_video("VisionReport", props, "test.mp4")

            assert mock_subprocess.called
            args = mock_subprocess.call_args[0]
            assert "npx" in args
            assert "remotion" in args
            assert "render" in args
            assert "VisionReport" in args
            # Using os.path.abspath(os.path.join(...)) to match engine.py
            expected_output = os.path.abspath(
                os.path.join("/tmp/artifacts", "test.mp4")
            )
            assert expected_output in args
