from typing import Any

from .dna import (
    Aggregator,
    Connector,
    Generator,
    Membrane,
    SkillProtocol,
    Transformer,
)
from .gen.aura.core.v1 import (
    ActionType,
    AgentIdentity,
    Event,
    Money,
    NegotiationOffer,
    Observation,
    Signal,
    SystemVitals,
)
from .gen.aura.core.v1 import (
    Context as HiveContext,
)
from .gen.aura.core.v1 import (
    Intent as IntentAction,
)
from .manifest import (
    ALLOWED_CHAMBERS,
    ALLOWED_ROOT_FILES,
    MACRO_ATCG_FOLDERS,
    find_hive_root,
    get_allowed_chambers,
    get_allowed_root_files,
    get_macro_atcg_folders,
    resolve_brain_path,
)
from .metabolism import (
    BaseConnector,
    MetabolicLoop,
    SkillRegistry,
)


# Utils
def get_raw_key(key_field: Any) -> str:
    from pydantic import SecretStr
    if isinstance(key_field, SecretStr):
        return key_field.get_secret_value()
    return str(key_field)

__all__ = [
    # Manifest (Geography)
    "find_hive_root",
    "MACRO_ATCG_FOLDERS",
    "ALLOWED_ROOT_FILES",
    "ALLOWED_CHAMBERS",
    "get_macro_atcg_folders",
    "get_allowed_root_files",
    "get_allowed_chambers",
    "resolve_brain_path",
    # Protocols (The Law)
    "Aggregator",
    "Transformer",
    "Connector",
    "Generator",
    "Membrane",
    "SkillProtocol",
    # Engine (The Machinery)
    "BaseConnector",
    "SkillRegistry",
    "MetabolicLoop",
    # Types (Genomic DNA)
    "Signal",
    "NegotiationOffer",
    "HiveContext",
    "IntentAction",
    "get_raw_key",
    "Observation",
    "Event",
    "SystemVitals",
    "ActionType",
    "AgentIdentity",
    "Money",
]
