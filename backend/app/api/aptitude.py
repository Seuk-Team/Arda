"""Backward-compat shim (ADR-0035 Phase 3i). 실체 → `app.application.api.aptitude`."""

from app.application.api.aptitude import *  # noqa: F401,F403
from app.application.api.aptitude import router  # noqa: F401
