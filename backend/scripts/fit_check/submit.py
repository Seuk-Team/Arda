"""적합도 확인용 지원자 투입 — 공개 지원 폼으로 넣는다. 로그인이 필요 없다.

    python scripts/fit_check/submit.py --role frontend --posting 12
    python scripts/fit_check/submit.py --role backend  --token <공개 링크 토큰>
    python scripts/fit_check/submit.py --role frontend --posting 12 --dry-run

- `--posting` 은 공고 id, `--token` 은 `/apply/<token>` 의 토큰. 둘 중 하나.
- 같은 공고에 같은 이메일은 서버가 409 로 막는다(C6). 다시 넣으려면 담당자 화면에서
  지우거나 `--suffix 2` 로 이메일을 `fitcheck-fe-01+2@example.com` 처럼 바꾼다.
- 제출이 끝나면 서버가 백그라운드로 요약·적합도·임베딩을 만든다. 1건에 Claude 3회라
  12명이면 1~2분 걸린다. 그 뒤 `report.py` 로 본다.

설명서: docs/07_eval/fit-check-2026-09.md
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import yaml  # backend 의존성(pyyaml)에 있다

BASE = "https://api.seuk.suvisdev.cloud/api/v1"
HERE = Path(__file__).parent

for _stream in (sys.stdout, sys.stderr):  # Windows 콘솔 cp949 대비
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")


def _get(url: str) -> dict:
    try:
        with urllib.request.urlopen(url, timeout=20) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        try:
            msg = json.load(e).get("message")
        except Exception:
            msg = e.reason
        print(f"공고 조회 실패 {e.code}: {msg} ({url})")
        sys.exit(1)


def _post(url: str, body: dict) -> tuple[int, dict]:
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.load(e)
        except Exception:
            return e.code, {"message": e.reason}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--role", choices=["frontend", "backend"], required=True)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--posting", type=int, help="공고 id")
    g.add_argument("--token", help="공개 링크 토큰 (/apply/<token>)")
    p.add_argument("--base", default=BASE)
    p.add_argument("--suffix", default="", help="이메일 로컬파트에 +suffix 를 붙여 재투입")
    p.add_argument("--only", nargs="*", help="이 이메일(들)만 넣는다")
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args()

    if a.token:
        posting = _get(f"{a.base}/public/postings/by-token/{a.token}")
    else:
        posting = _get(f"{a.base}/public/postings/{a.posting}")
    pid = posting["id"]
    print(f"공고 #{pid} {posting['title']}")
    if not (posting.get("description") or "").strip():
        print("  ⚠ description 이 비어 있다 — 적합도 평가는 description 만 본다. 요강을 먼저 넣어라.")

    data = yaml.safe_load((HERE / "applicants.yaml").read_text(encoding="utf-8"))
    people = data[a.role]
    if a.only:
        people = [x for x in people if x["email"] in set(a.only)]

    ok = dup = fail = 0
    for x in people:
        email = x["email"]
        if a.suffix:
            local, _, domain = email.partition("@")
            email = f"{local}+{a.suffix}@{domain}"
        body = {
            "name": x["name"],
            "email": email,
            "phone": "010-0000-0000",
            "birth_date": "1995-01-01",
            "education": x.get("education"),
            "career_years": x.get("career_years"),
            "skills": x.get("skills") or None,
            "self_intro": x["self_intro"].strip(),
            "privacy_agreed": True,
            "files": [],
        }
        tag = f"{x['name']:<8} {email:<36} 기대 {x['expect']['tier']}"
        if a.dry_run:
            print(f"  (dry) {tag}")
            continue
        code, res = _post(f"{a.base}/public/postings/{pid}/applications", body)
        if code == 201:
            ok += 1
            print(f"  ✓ #{res.get('id'):<4} {tag}")
        elif code == 409:
            dup += 1
            print(f"  = 중복    {tag}")
        else:
            fail += 1
            print(f"  ✗ {code} {res.get('message') or res}  {tag}")
        time.sleep(0.3)  # 백그라운드 요약이 한꺼번에 몰리지 않게

    print(f"\n완료: 접수 {ok} · 중복 {dup} · 실패 {fail}. 요약 생성에 1~2분 뒤 report.py")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
