from typing import TYPE_CHECKING, Any

from .controller import WorkerController
from .node import AuraNode
from .proteins.vision_skill import VisionSkill
from .tunnel import Umbilical

if TYPE_CHECKING:
    from .ui import launch_interactive_node

__all__ = [
    "launch_interactive_node",
    "AuraNode",
    "Umbilical",
    "VisionSkill",
    "WorkerController",
]

# ui.py draws the Gradio panel. Importing it here would make the whole UI stack a
# hard requirement of `import aura_worker` — which a headless node never needs.
# Resolve it on first access instead; see [project.optional-dependencies] ui.
_UI_STACK = frozenset({"gradio", "nest_asyncio", "dotenv"})


def __getattr__(name: str) -> Any:
    if name == "launch_interactive_node":
        try:
            from .ui import launch_interactive_node  # noqa: PLC0415
        except ImportError as exc:
            if exc.name in _UI_STACK:
                raise ImportError(
                    "launch_interactive_node needs the interactive UI stack, "
                    "which is an optional extra: install aura-worker[ui]"
                ) from exc
            raise
        return launch_interactive_node
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
