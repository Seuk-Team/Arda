"""Backward-compat shim (ADR-0035 Phase 3h). 실체 → `app.interview.api.schedules`."""

from app.interview.api.schedules import *  # noqa: F401,F403
from app.interview.api.schedules import router  # noqa: F401
