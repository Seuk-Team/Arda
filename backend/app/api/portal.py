"""Backward-compat shim (ADR-0035 Phase 3i). 실체 → `app.application.api.portal`."""

from app.application.api.portal import *  # noqa: F401,F403
from app.application.api.portal import router  # noqa: F401
