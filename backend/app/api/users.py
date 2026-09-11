"""Backward-compat shim (ADR-0035 Phase 3j). 실체 → `app.talent.api.users`."""

from app.talent.api.users import *  # noqa: F401,F403
from app.talent.api.users import router  # noqa: F401
