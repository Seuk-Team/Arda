"""Backward-compat shim (ADR-0035 Phase 3e). 실체 → `app.shared.s3`."""

from app.shared.s3 import *  # noqa: F401,F403
