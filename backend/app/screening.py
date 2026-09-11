"""Backward-compat shim (ADR-0035 Phase 3d).

실체는 `app.application.screening` 로 이관됐다. 옛 import (`from app import screening`,
`from app.screening import decide_document`) 를 그대로 살려 둔다. 새 코드는 새 위치로
import 한다.
"""

from app.application.screening import *  # noqa: F401,F403
