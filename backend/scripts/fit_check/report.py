"""적합도 확인 결과표 — 담당자 계정으로 로그인해서 본다.

    python scripts/fit_check/report.py --role frontend --posting 12
    python scripts/fit_check/report.py --role backend  --posting 13 --search "React 성능 최적화 경험"

- 실행하면 담당자 이메일·비밀번호를 **터미널에서 직접** 묻는다(코드·인자·파일에 적지 않는다).
- 공고의 지원자 전부를 읽어 아르의 fit_score · fit · concerns · 추천(action) 을
  applicants.yaml 의 기대 등급(A/B/C)과 나란히 놓는다. 등급 순서가 뒤집힌 곳이 곧 발견이다.
- `--search` 를 주면 아르 채팅에 같은 문장을 보내 의미 검색 순위도 찍는다(도구 호출 결과 그대로).
- 결과는 화면 출력 + `docs/07_eval/fit-check-results/<role>-<날짜>.md` 로 저장.

설명서: docs/07_eval/fit-check-2026-09.md
"""

from __future__ import annotations

import argparse
import getpass
import json
import sys
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

import yaml

BASE = "https://api.seuk.suvisdev.cloud/api/v1"
HERE = Path(__file__).parent
OUT_DIR = HERE.parents[2] / "docs" / "07_eval" / "fit-check-results"

for _stream in (sys.stdout, sys.stderr):  # Windows 콘솔 cp949 대비
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")
TIER_OF_SCORE = {5: "A", 4: "A", 3: "B", 2: "C", 1: "C"}


def _req(method: str, url: str, token: str | None = None, body: dict | None = None) -> tuple[int, dict]:
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.load(e)
        except Exception:
            return e.code, {"message": e.reason}


def login(base: str) -> str:
    email = input("담당자 이메일: ").strip()
    pw = getpass.getpass("비밀번호 (화면에 안 보임): ")
    code, res = _req("POST", f"{base}/auth/login", body={"email": email, "password": pw})
    if code != 200:
        print(f"로그인 실패 {code}: {res.get('message')}")
        sys.exit(1)
    return res["access_token"]


def parse_summary(raw: str | None) -> dict:
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except Exception:
        return {"_raw": raw[:80]}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--role", choices=["frontend", "backend"], required=True)
    p.add_argument("--posting", type=int, required=True, help="공고 id")
    p.add_argument("--base", default=BASE)
    p.add_argument("--search", action="append", default=[], help="아르에게 던질 의미 검색 문장 (여러 번 가능)")
    a = p.parse_args()

    token = login(a.base)
    expected = {x["email"].split("+")[0]: x for x in yaml.safe_load((HERE / "applicants.yaml").read_text(encoding="utf-8"))[a.role]}

    code, res = _req("GET", f"{a.base}/applications?posting_id={a.posting}&limit=200&with_total=false", token)
    if code != 200:
        print(f"목록 실패 {code}: {res}")
        return 1
    items = res.get("items") or res if isinstance(res, list) else res.get("items", [])

    rows = []
    for it in items:
        aid = it["id"]
        code, d = _req("GET", f"{a.base}/applications/{aid}", token)
        if code != 200:
            continue
        s = parse_summary(d.get("ai_summary"))
        email_key = (d.get("email") or "").split("+")[0].replace("@example.com", "") + "@example.com"
        exp = expected.get(email_key) or expected.get(d.get("email", ""))
        rows.append({
            "id": aid,
            "name": d.get("name"),
            "email": d.get("email"),
            "expect": (exp or {}).get("expect", {}).get("tier", "?"),
            "why": (exp or {}).get("expect", {}).get("why", ""),
            "fit_score": s.get("fit_score"),
            "got": TIER_OF_SCORE.get(s.get("fit_score"), "-") if s.get("fit_score") else ("ins" if s.get("insufficient") else "-"),
            "action": s.get("action"),
            "fit": s.get("fit") or [],
            "concerns": s.get("concerns") or [],
            "model": d.get("ai_summary_model"),
        })

    rows.sort(key=lambda r: (-(r["fit_score"] or 0), r["expect"]))
    lines = [f"# 적합도 확인 — {a.role} · 공고 #{a.posting} · {date.today().isoformat()}", "",
             "| # | 이름 | 기대 | 결과 | 점수 | 추천 | 맞는 점 | 우려 | 근거(사람) |", "|---|---|---|---|---|---|---|---|---|"]
    mismatch = 0
    for r in rows:
        flag = "" if r["got"] in ("-", "ins") or r["got"] == r["expect"] else " ⚠"
        if flag:
            mismatch += 1
        lines.append(
            f"| {r['id']} | {r['name']} | {r['expect']} | {r['got']}{flag} | {r['fit_score'] or ''} | {r['action'] or ''} | "
            f"{' / '.join(r['fit'])} | {' / '.join(r['concerns'])} | {r['why']} |"
        )
    scored = [r for r in rows if r["fit_score"]]
    lines += ["", f"- 지원자 {len(rows)}명 · 점수 있음 {len(scored)} · 기대와 다른 등급 {mismatch}",
              f"- 모델 태그: {sorted({r['model'] for r in rows if r['model']})}",
              "- 등급 기준: fit_score 4~5 = A · 3 = B · 1~2 = C. 'ins' = 아르가 정보 부족이라고 실토한 것(지어내지 않음 = 정상)."]

    for q in a.search:
        code, res = _req("POST", f"{a.base}/agent/chat", token, {"message": q, "history": []})
        lines += ["", f"## 의미 검색: {q}", ""]
        if code != 200:
            lines.append(f"실패 {code}: {res.get('message')}")
            continue
        for tc in res.get("tool_calls", []):
            out = tc.get("result") or tc.get("output") or {}
            hits = out.get("items") if isinstance(out, dict) else None
            lines.append(f"- 도구 `{tc.get('name')}` · search_mode={out.get('search_mode') if isinstance(out, dict) else '?'}")
            for i, h in enumerate(hits or [], 1):
                lines.append(f"  {i}. #{h.get('id')} {h.get('name')} (공고 {h.get('job_posting_id')})")
        lines.append("")
        lines.append("아르 답변:")
        lines.append(res.get("reply", "").strip())

    text = "\n".join(lines)
    print(text)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"{a.role}-{date.today().isoformat()}.md"
    out.write_text(text + "\n", encoding="utf-8")
    print(f"\n저장: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
