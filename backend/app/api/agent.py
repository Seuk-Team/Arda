"""Backward-compat shim (ADR-0035 Phase 3i). 실체 → `app.application.api.agent`."""

from app.application.api.agent import *  # noqa: F401,F403
from app.application.api.agent import router  # noqa: F401
