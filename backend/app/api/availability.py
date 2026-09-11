"""Backward-compat shim (ADR-0035 Phase 3h). 실체 → `app.interview.api.availability`."""

from app.interview.api.availability import *  # noqa: F401,F403
from app.interview.api.availability import router  # noqa: F401
