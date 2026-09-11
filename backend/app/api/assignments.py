"""Backward-compat shim (ADR-0035 Phase 3h). 실체 → `app.interview.api.assignments`."""

from app.interview.api.assignments import *  # noqa: F401,F403
from app.interview.api.assignments import router  # noqa: F401
