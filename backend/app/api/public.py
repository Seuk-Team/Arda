"""Backward-compat shim (ADR-0035 Phase 3i). 실체 → `app.application.api.public`."""

from app.application.api.public import *  # noqa: F401,F403
from app.application.api.public import router  # noqa: F401
