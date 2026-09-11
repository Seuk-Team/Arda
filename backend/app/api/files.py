"""Backward-compat shim (ADR-0035 Phase 3j). 실체 → `app.shared.api.files`."""

from app.shared.api.files import *  # noqa: F401,F403
from app.shared.api.files import router  # noqa: F401
