"""채용 요강 2건을 Arda 에 공고로 넣고(선택) 지원자 24명까지 투입한다 — 한 명령.

    python scripts/fit_check/create_postings.py            # 공고 2개 생성 + 공개 링크
    python scripts/fit_check/create_postings.py --submit   # + 지원자 24명 투입 (submit.py)
    python scripts/fit_check/create_postings.py --dry-run  # 무엇을 보낼지만 출력

- 담당자 이메일·비밀번호는 **터미널이 직접 묻는다**(코드·인자·파일에 적지 않는다).
- 요강 원문은 docs/06_company/01-채용요강-2026-09.md. 그 문서의 "Arda description 에 붙여
  넣을 것" 블록을 여기 그대로 옮겼다 — 문서를 고치면 여기도 같이 고친다.
- 자동 심사(ADR-0034, PR #147)가 배포된 서버면 임계 60·auto 모드가 같이 저장되고, 아직이면
  서버가 그 필드를 무시한다(Pydantic 기본). 어느 쪽이든 공고는 만들어진다.
- 같은 제목의 공고가 이미 있으면 새로 만들지 않고 그 id 를 쓴다 — 두 번 돌려도 중복 공고가 안 생긴다.

설명서: docs/07_eval/fit-check-2026-09.md
"""

from __future__ import annotations

import argparse
import getpass
import json
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

BASE = "https://api.seuk.suvisdev.cloud/api/v1"
HERE = Path(__file__).parent
DEADLINE = "2026-10-15"

# Windows 콘솔(cp949)에서 '—' 같은 글자로 죽지 않게. 팀장 PC 가 Windows 다.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

POSTINGS = {
    "frontend": {
        "title": "프론트엔드 개발자 (React·TypeScript) — 경력 2~6년",
        "location": "서울 성동구 성수동2가 (하이브리드 주 2일 사무실)",
        "employment_type": "정규직",
        "experience_min": 2,
        "experience_max": 6,
        "remote_policy": "하이브리드 — 주 2일 사무실 · 주 3일 재택 (신입 첫 3개월 주 3일 사무실 권장)",
        "requirements": (
            "- React + TypeScript 실서비스 2년 이상 (운영 경험 포함)\n"
            "- REST API 연동 경험 (인증 토큰·401 처리·낙관적 갱신 중 하나 이상)\n"
            "- Git 브랜치→PR→머지 협업 경험\n"
            "- 결정과 근거를 문서(PR 본문·설계 메모)로 남긴 경험"
        ),
        "preferred": (
            "- Vite·번들·초기 로딩 최적화\n- WebSocket·WebRTC 실시간 화면\n- Flutter 또는 React Native 모바일\n"
            "- 디자인 시스템(토큰·컴포넌트 라이브러리) 운영\n- 접근성(키보드·스크린리더) 대응\n- 오픈소스 기여 또는 공개 포트폴리오"
        ),
        "benefits": "연차 15일 + 리프레시 5일 · 실비 보험 · 건강검진 · 도서비 무제한 · 컨퍼런스 연 1회 · 노트북 자율 선택(400만원) · 재택 세팅 100만원 · 출근일 점심",
        "description": """[담당 업무]
- 신제품 웹 프론트엔드를 기획부터 출시·운영까지 (프로젝트당 3~6개월, 3~5명 팀)
- 디자인 시안을 컴포넌트로 옮기고 백엔드와 API 계약(OpenAPI)을 함께 정함
- 출시 뒤 성능·접근성·오류를 지표로 보고 개선

[자격 요건 — 필수]
- React + TypeScript 실서비스 2년 이상 (운영 경험 포함)
- REST API 연동 경험 (인증 토큰·401 처리·낙관적 갱신 중 하나 이상)
- Git 브랜치→PR→머지 협업 경험
- 결정과 근거를 문서(PR 본문·설계 메모)로 남긴 경험

[우대]
- Vite·번들·초기 로딩 최적화 / WebSocket·WebRTC 실시간 화면 / Flutter 또는 RN 모바일 / 디자인 시스템 운영 / 접근성 대응 / 오픈소스·공개 포트폴리오

[인재상]
- 자기 도메인은 자기가 판단 (승인 대기 X) / 필요하면 백엔드 코드도 고침 / 실패를 공개하고 원인·조치를 짧게 적음
- 잘 안 맞는 경우: 세세한 지시가 있어야 편함 / 회의로 결정 선호 / 완벽할 때까지 릴리스 안 함

[조건] 정규직 · 성수동 하이브리드(주2 사무실) · 재량근무 · 경력 2~6년 · 2026-10-15 마감""",
    },
    "backend": {
        "title": "백엔드 개발자 (Python·FastAPI·PostgreSQL) — 경력 3~8년",
        "location": "서울 성동구 성수동2가 (하이브리드 주 2일 사무실)",
        "employment_type": "정규직",
        "experience_min": 3,
        "experience_max": 8,
        "remote_policy": "하이브리드 — 주 2일 사무실 · 주 3일 재택",
        "requirements": (
            "- Python 실서비스 API 3년 이상 개발·운영 (FastAPI·Django·Flask 중 하나)\n"
            "- 관계형 DB 스키마 설계 + 인덱스·쿼리 튜닝\n"
            "- 인증(JWT 등)·권한 모델 설계 경험\n"
            "- pytest 등 테스트를 CI 에서 돌린 경험\n"
            "- Docker 배포 경험"
        ),
        "preferred": (
            "- asyncio·WebSocket 서버\n- 큐·워커(SQS·Redis·Celery)\n- AWS(EC2·S3·IAM) 운영 또는 온프레미스 이전\n"
            "- LLM API(도구 호출·RAG·임베딩)\n- pgvector 벡터 검색\n- append-only·해시 체인 감사 로그"
        ),
        "benefits": "연차 15일 + 리프레시 5일 · 실비 보험 · 건강검진 · 도서비 무제한 · 컨퍼런스 연 1회 · 노트북 자율 선택(400만원) · 재택 세팅 100만원 · 출근일 점심",
        "description": """[담당 업무]
- 신제품 API 서버·데이터 모델 설계·구현 (Python·FastAPI·PostgreSQL)
- alembic 마이그레이션으로 스키마 관리, ERD 를 팀 계약으로 유지
- 파일 업로드(S3 presigned)·메일·큐를 서버 밖으로 빼는 구조
- 컨테이너·CI 배포 자동화, 백업·경보 운영
- 인수 프로젝트를 3주 안에 파악해 운영 가능 상태로

[자격 요건 — 필수]
- Python 실서비스 API 3년 이상 개발·운영 (FastAPI·Django·Flask 중 하나)
- 관계형 DB 스키마 설계 + 인덱스·쿼리 튜닝
- 인증(JWT 등)·권한 모델 설계 경험
- pytest 등 테스트를 CI 에서 돌린 경험
- Docker 배포 경험

[우대]
- asyncio·WebSocket / 큐·워커(SQS·Redis·Celery) / AWS(EC2·S3·IAM) 또는 온프레미스 이전 / LLM API(도구 호출·RAG·임베딩) / pgvector 벡터 검색 / append-only·해시 체인 감사 로그

[인재상]
- 기술 결정을 ADR 처럼 문서로 남김 / 배포 사고를 스스로 공개 / 프론트·인프라 코드도 필요하면 고침
- 잘 안 맞는 경우: 자기 도메인만 지킴 / 승인 라인에 태우는 것이 편함

[조건] 정규직 · 성수동 하이브리드(주2 사무실) · 재량근무 · 경력 3~8년 · 2026-10-15 마감""",
    },
}


def _req(method: str, url: str, token: str | None = None, body: dict | None = None) -> tuple[int, dict]:
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, (json.load(r) if r.status != 204 else {})
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


def find_existing(base: str, token: str, title: str) -> dict | None:
    code, res = _req("GET", f"{base}/postings", token)
    if code != 200:
        return None
    for p in res:
        if p.get("title") == title:
            return p
    return None


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--base", default=BASE)
    p.add_argument("--submit", action="store_true", help="공고 생성 뒤 지원자 24명까지 투입")
    p.add_argument("--threshold", type=int, default=60, help="자동 심사 임계 (ADR-0034, 서버가 지원할 때만)")
    p.add_argument("--mode", choices=["auto", "manual"], default="auto", help="자동 심사 모드")
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args()

    if a.dry_run:
        for role, spec in POSTINGS.items():
            print(f"[{role}] {spec['title']} · 마감 {DEADLINE} · 임계 {a.threshold} · {a.mode}")
            print("  description:", spec["description"].splitlines()[0], "... (", len(spec["description"]), "자 )")
        return 0

    token = login(a.base)
    made: dict[str, dict] = {}
    for role, spec in POSTINGS.items():
        existing = find_existing(a.base, token, spec["title"])
        if existing:
            pid = existing["id"]
            print(f"= 이미 있음 #{pid} {spec['title']}")
        else:
            body = {**spec, "status": "open", "deadline": DEADLINE,
                    "pass_threshold": a.threshold, "screening_mode": a.mode}
            code, res = _req("POST", f"{a.base}/postings", token, body)
            if code != 201:
                print(f"✗ 공고 생성 실패 {code}: {res.get('message') or res}")
                return 1
            pid = res["id"]
            print(f"✓ 생성 #{pid} {spec['title']} (임계 {res.get('pass_threshold', '서버 미지원')})")
        code, link = _req("POST", f"{a.base}/postings/{pid}/public-link", token)
        url = link.get("url") if code == 201 else None
        print(f"  공개 링크: {url or f'발급 실패 {code}'}")
        made[role] = {"id": pid, "url": url}

    print("\n공고 id:", {r: m["id"] for r, m in made.items()})
    if a.submit:
        for role, m in made.items():
            print(f"\n== {role} 투입 ==")
            subprocess.run(
                [sys.executable, str(HERE / "submit.py"), "--role", role, "--posting", str(m["id"]), "--base", a.base],
                check=False,
            )
        print("\n1~2분 뒤: python scripts/fit_check/report.py --role frontend --posting", made["frontend"]["id"])
    else:
        print("지원자 투입: 위 id 로 submit.py, 또는 이 명령에 --submit")
    return 0


if __name__ == "__main__":
    sys.exit(main())
