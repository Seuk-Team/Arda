"""Backward-compat shim (ADR-0035 Phase 3i). 실체 → `app.application.api.emails`."""

from app.application.api.emails import *  # noqa: F401,F403
from app.application.api.emails import router  # noqa: F401
