"""Backward-compat shim (ADR-0035 Phase 3j). 실체 → `app.shared.api.integrity`."""

from app.shared.api.integrity import *  # noqa: F401,F403
from app.shared.api.integrity import router  # noqa: F401
