"""Backward-compat shim (ADR-0035 Phase 3h). 실체 → `app.interview.api.scoring`."""

from app.interview.api.scoring import *  # noqa: F401,F403
from app.interview.api.scoring import router  # noqa: F401
