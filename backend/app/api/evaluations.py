"""Backward-compat shim (ADR-0035 Phase 3i). 실체 → `app.application.api.evaluations`."""

from app.application.api.evaluations import *  # noqa: F401,F403
from app.application.api.evaluations import router  # noqa: F401
