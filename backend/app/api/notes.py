"""Backward-compat shim (ADR-0035 Phase 3i). 실체 → `app.application.api.notes`."""

from app.application.api.notes import *  # noqa: F401,F403
from app.application.api.notes import router  # noqa: F401
