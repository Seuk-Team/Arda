"""Backward-compat shim (ADR-0035 Phase 3h). 실체 → `app.interview.api.interviews`."""

from app.interview.api.interviews import *  # noqa: F401,F403
from app.interview.api.interviews import router  # noqa: F401
