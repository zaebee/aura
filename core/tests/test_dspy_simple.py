import tempfile
from pathlib import Path
from unittest.mock import patch

from src.hive.proteins.reasoning.engine import (
    AuraNegotiator,
    DSPyStrategy,
)


def test_dspy_strategy_init_minimal():
    # Create a temporary compiled program for testing
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
        tmp.write(b'{"test": "data"}')
        tmp_path = tmp.name

    try:
        # Mock the loading to avoid file issues
        with patch("src.hive.proteins.reasoning.engine.dspy.load") as mock_load:
            mock_load.return_value = AuraNegotiator()

            strategy = DSPyStrategy(
                model="gpt-3.5-turbo", compiled_program_path=tmp_path
            )
            assert strategy is not None
            assert strategy.negotiator is not None
    finally:
        # Clean up
        Path(tmp_path).unlink()
