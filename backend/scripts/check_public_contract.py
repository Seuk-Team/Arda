"""무인증 GET 대조 — 02-api.md 계약과 실제 배포본을 맞춰 본다.

02-api.md 6행: *"인증: JWT Bearer. **공개**로 표시된 것 외에는 전부 로그인 필요."*

이 스크립트는 배포본의 `/openapi.json` 에서 **GET 을 전부 뽑아** 토큰 없이 한 번씩
때려 보고, 위 한 줄과 어긋나는 것을 찾는다. 손으로 하던 대조를 고정한 것이다 —
지금까지 나온 결함(#59 면접관이 공고 수정 가능 · #97 draft 공고 무인증 노출)이
전부 이 대조에서 나왔고, 굳혀두지 않으면 엔드포인트가 늘 때마다 재발한다.

경로 목록을 코드에 박지 않고 `/openapi.json` 에서 읽는 이유: **새 엔드포인트가
생기면 자동으로 대조 대상이 된다.** 박아두면 새로 생긴 것이 빠져 무의미해진다.

사용:
    python scripts/check_public_contract.py                      # 배포본
    python scripts/check_public_contract.py http://localhost:8000 # 로컬

읽기(GET)만 한다 — 서버 데이터를 바꾸지 않는다. 경로 변수에는 존재하지 않는 값을
넣으므로 실지원자 데이터에 닿지도 않는다.

종료 코드: 어긋난 것이 하나라도 있으면 1.
"""

import json
import sys
import urllib.error
import urllib.request

DEFAULT_BASE = "https://api.arda.seuk.cloud"

# 02-api.md 에서 **공개**로 표시된 것. 그 외 GET 은 전부 401 이어야 한다.
# 공개 엔드포인트가 이 접두사 밖에 새로 생기면 여기에 추가한다.
PUBLIC_PREFIXES = ("/api/v1/public/",)
PUBLIC_EXACT = ("/health",)

# 경로 변수에 넣을 값. 존재하지 않는 것을 넣어 실데이터를 건드리지 않는다.
MISSING_ID = 999999
MISSING_STR = "__contract_check__"

TIMEOUT = 15


def fill_path(path: str) -> str:
    """`/postings/{posting_id}` → `/postings/999999`."""
    out = path
    while "{" in out:
        head, rest = out.split("{", 1)
        name, tail = rest.split("}", 1)
        value = MISSING_ID if name == "id" or name.endswith("_id") else MISSING_STR
        out = f"{head}{value}{tail}"
    return out


def is_public(path: str) -> bool:
    return path in PUBLIC_EXACT or path.startswith(PUBLIC_PREFIXES)


def get(url: str) -> tuple[int, str]:
    """토큰 없이 GET. (상태코드, 응답 code 필드) 를 돌려준다."""
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as res:
            return res.status, ""
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        try:
            return e.code, json.loads(body).get("code", "")
        except json.JSONDecodeError:
            return e.code, ""
    except urllib.error.URLError as e:
        raise SystemExit(f"연결 실패: {e.reason}")


def judge(path: str, status: int, code: str) -> tuple[bool, str]:
    """계약과 맞는지 판정한다. (통과 여부, 사유)."""
    if is_public(path):
        # 공개 경로 — 없는 id 를 넣었으니 404·410 이 정상이다. 200 도 맞다(있는 경우).
        if status in (200, 404, 410, 422):
            return True, f"공개 {status}"
        if status in (401, 403):
            return False, f"공개인데 인증을 요구한다 ({status})"
        return False, f"예상 밖 {status}"

    # 보호 경로 — 토큰이 없으면 401 UNAUTHORIZED 여야 한다 (#60).
    if status == 401:
        if code and code != "UNAUTHORIZED":
            return False, f"401 인데 code={code} (UNAUTHORIZED 여야 한다)"
        return True, "401 UNAUTHORIZED"
    if status in (200, 404, 410):
        return False, f"★ 무인증 노출 — 토큰 없이 {status} 가 나온다"
    if status == 403:
        return False, "403 — 무인증은 401 이어야 한다 (#60)"
    return False, f"예상 밖 {status}"


def main() -> int:
    base = (sys.argv[1] if len(sys.argv) > 1 else DEFAULT_BASE).rstrip("/")

    with urllib.request.urlopen(f"{base}/openapi.json", timeout=TIMEOUT) as res:
        spec = json.load(res)

    targets = sorted(p for p, ops in spec["paths"].items() if "get" in ops)
    print(f"대상: {base} · GET {len(targets)}개\n")

    failures = []
    for path in targets:
        status, code = get(base + fill_path(path))
        ok, why = judge(path, status, code)
        mark = "  " if ok else "FAIL"
        kind = "공개" if is_public(path) else "보호"
        print(f"{mark} [{kind}] {path:<52} {why}")
        if not ok:
            failures.append((path, why))

    print()
    if failures:
        print(f"어긋남 {len(failures)}건 — 02-api.md 계약과 맞지 않는다:")
        for path, why in failures:
            print(f"  - {path}: {why}")
        return 1
    print(f"전부 계약대로. (공개 {sum(is_public(p) for p in targets)} · 보호 {sum(not is_public(p) for p in targets)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
