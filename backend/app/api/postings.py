"""Backward-compat shim (ADR-0035 Phase 3j). 실체 → `app.hiring.api.postings`."""

from app.hiring.api.postings import *  # noqa: F401,F403
from app.hiring.api.postings import router  # noqa: F401
