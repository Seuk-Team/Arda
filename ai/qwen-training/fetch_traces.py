"""서버 DB 의 agent_traces 를 로컬로 가져온다.

원리:
    로컬은 Docker 데몬이 꺼져있고 DB 도 없다. 서버(arda) 의 `arda-db-1` 컨테이너에
    SSH → docker exec psql 로 붙어 JSON 으로 뽑아 파일에 붙인다.

산출물: raw_traces.json — agent_traces 전건 (label_verdict=null 포함).
        나중에 build_dataset.py 가 여기서 골라 학습셋에 붙인다.
"""

from __future__ import annotations

import json
import shlex
import subprocess
import sys
from pathlib import Path

OUT_PATH = Path(__file__).parent / "raw_traces.json"

# psql 은 tAc 플래그로 헤더/포맷 없이 값만 뱉는다. json_agg 로 한 줄 JSON.
SQL = """
SELECT COALESCE(json_agg(row_to_json(t)), '[]'::json) FROM (
  SELECT id, request_id, session_id, turn_index,
         user_message, assistant_reply, history, tool_calls, pending_action,
         backend, model_tag, input_tokens, output_tokens,
         label_verdict, label_correction, created_at
  FROM agent_traces
  ORDER BY created_at
) t
"""


def main() -> int:
    # WSL 은 Windows 쉘에서 그대로 호출 가능. ssh 로 원격 컨테이너 커맨드를 던진다.
    remote = (
        "docker exec arda-db-1 psql -U postgres -d arda "
        f"-tAc {shlex.quote(SQL)}"
    )
    cmd = ["wsl", "--", "ssh", "arda", remote]

    print(f"[fetch] {' '.join(cmd)}", file=sys.stderr)
    # Windows 기본 코덱(cp949)이 psql 의 UTF-8 한국어 응답을 못 읽는다. bytes 로 받고 직접 디코딩.
    proc = subprocess.run(cmd, capture_output=True, timeout=60)
    stdout_text = proc.stdout.decode("utf-8", errors="replace") if proc.stdout else ""
    stderr_text = proc.stderr.decode("utf-8", errors="replace") if proc.stderr else ""
    if proc.returncode != 0:
        print(f"[fetch] ssh 실패 (exit {proc.returncode})", file=sys.stderr)
        print(stderr_text, file=sys.stderr)
        return 1

    out = stdout_text.strip()
    if not out:
        print("[fetch] 빈 응답 — agent_traces 가 비어있음", file=sys.stderr)
        return 1

    try:
        rows = json.loads(out)
    except json.JSONDecodeError as exc:
        print(f"[fetch] JSON 파싱 실패: {exc}", file=sys.stderr)
        print(out[:500], file=sys.stderr)
        return 1

    OUT_PATH.write_text(
        json.dumps(rows, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    print(f"[fetch] {len(rows)} 건 → {OUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
