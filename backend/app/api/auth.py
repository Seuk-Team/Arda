"""Backward-compat shim (ADR-0035 Phase 3j). 실체 → `app.talent.api.auth`."""

from app.talent.api.auth import *  # noqa: F401,F403
from app.talent.api.auth import router  # noqa: F401
