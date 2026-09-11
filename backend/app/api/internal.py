"""Backward-compat shim (ADR-0035 Phase 3j). 실체 → `app.shared.api.internal`."""

from app.shared.api.internal import *  # noqa: F401,F403
from app.shared.api.internal import router  # noqa: F401
