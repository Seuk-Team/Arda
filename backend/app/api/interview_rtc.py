"""Backward-compat shim (ADR-0035 Phase 3h). 실체 → `app.interview.api.interview_rtc`."""

from app.interview.api.interview_rtc import *  # noqa: F401,F403
from app.interview.api.interview_rtc import router  # noqa: F401
