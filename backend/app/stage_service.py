"""Backward-compat shim (ADR-0035 Phase 3d). 실체 → `app.application.stage_service`."""

from app.application.stage_service import *  # noqa: F401,F403
