"""Test configuration for the api-gateway.

The gateway's ``Settings`` (env_prefix ``AURA_GATEWAY__``) requires
``core_service_host`` and ``redis_url`` at import time. Provide dummy values so
the suite is self-contained and does not depend on the ambient environment.
``setdefault`` keeps any real values a developer/CI already exported.
"""

import os

os.environ.setdefault("AURA_GATEWAY__CORE_SERVICE_HOST", "localhost")
os.environ.setdefault("AURA_GATEWAY__REDIS_URL", "redis://localhost:6379")
