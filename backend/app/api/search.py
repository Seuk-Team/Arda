"""Backward-compat shim (ADR-0035 Phase 3i). 실체 → `app.application.api.search`."""

from app.application.api.search import *  # noqa: F401,F403
from app.application.api.search import router  # noqa: F401
