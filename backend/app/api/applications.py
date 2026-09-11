"""Backward-compat shim (ADR-0035 Phase 3i). 실체 → `app.application.api.applications`."""

from app.application.api.applications import *  # noqa: F401,F403
from app.application.api.applications import router  # noqa: F401
