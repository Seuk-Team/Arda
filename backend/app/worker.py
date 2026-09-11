"""Backward-compat shim (ADR-0035 Phase 3e). 실체 → `app.shared.worker`."""

from app.shared.worker import *  # noqa: F401,F403
