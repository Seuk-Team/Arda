"""더미 지원서 PDF 묶음 투입 — 실제 접수 경로(F1 presign → S3 PUT → C2 제출)로 넣는다.

`seed_dummy.py` 와 다르다. 저쪽은 DB 에 직접 INSERT 해서 검색 성능(perf-search.md)
무대를 만드는 것이고, 요약도 임베딩도 만들지 않는다. 이 스크립트는 **사람이 지원 폼으로
낸 것과 같은 경로**로 넣는다 — 그래야 `public.submit` 의 BackgroundTasks 가
`generate_summary_bg` 를 돌리고, 그 안에서 `application_embeddings` 가 채워진다
(app/agent/summarizer.py `_generate_embedding`). DB 직접 INSERT 로 우회하면
임베딩이 안 생겨 시맨틱 검색 대상이 되지 않는다.

2단계로 나눈다 — 1단계만 pypdf 가 필요하고, 실제 투입인 2단계는 표준 라이브러리만 쓴다.

    # 1) PDF → JSON (pypdf 필요. 프로젝트 의존성이 아니라 이 스크립트 전용이다)
    python scripts/ingest_dummy_applications.py parse --src <PDF디렉터리> --out records.json

    # 2) JSON → API 투입 (표준 라이브러리만)
    ADMIN_PASSWORD=<비밀번호> python scripts/ingest_dummy_applications.py ingest \
        --records records.json --api http://localhost:8000 --admin <admin이메일>

    # 비용·시간을 먼저 재고 싶으면 (요약 1건마다 Claude 3회 호출 — ADR-0011)
    ... ingest --records records.json --limit 3

**로컬 전용이다.** `--api` 기본값이 localhost 인 것은 실수로 운영에 쏘지 않기 위해서다.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

# ── PDF 파싱 ────────────────────────────────────────────────────────────

# 이력서 머리말의 라벨. PDF 가 "라벨 값" 한 줄로 뽑힌다.
_LABELS = {
    "이메일": "email",
    "연락처": "phone",
    "최종 학력": "education",
    "경력 연차": "career_raw",
    "기술 스택": "skills_raw",
}

# "백엔드 개발자 (Python·FastAPI) 지원" → 공고 제목
_APPLY_LINE = re.compile(r"^(?P<title>.+?)\s*지원\s*$")

# "5년" / "10년" / "신입"
_YEARS = re.compile(r"(\d+)\s*년")


def _pdf_text(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        sys.exit(
            "pypdf 가 없다. 이 스크립트 전용 의존성이라 pyproject 에 넣지 않았다.\n"
            "  python -m pip install pypdf"
        )
    reader = PdfReader(str(path))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _parse_resume(text: str) -> dict:
    """이력서 PDF 텍스트에서 지원서 필드를 뽑는다."""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    out: dict = {"name": lines[0] if lines else ""}

    for line in lines[1:8]:
        matched = _APPLY_LINE.match(line)
        if matched and "posting_title" not in out:
            out["posting_title"] = matched.group("title").strip()
        for label, field in _LABELS.items():
            if line.startswith(label):
                out[field] = line[len(label):].strip()

    career_raw = out.pop("career_raw", "")
    matched = _YEARS.search(career_raw)
    # "신입" 은 0년이다. NULL 로 두면 임베딩 입력(embedder.build_text)에서 경력 줄이
    # 통째로 빠져 "신입" 이라는 정보 자체가 사라진다.
    out["career_years"] = int(matched.group(1)) if matched else 0

    skills_raw = out.pop("skills_raw", "")
    out["skills"] = [s.strip() for s in skills_raw.split(",") if s.strip()]

    out["resume_text"] = text.strip()
    return out


def cmd_parse(args: argparse.Namespace) -> int:
    src = Path(args.src)
    resumes = sorted(src.glob("*_이력서.pdf"))
    if not resumes:
        sys.exit(f"이력서 PDF 를 찾지 못했다: {src}")

    records = []
    for resume_path in resumes:
        stem = resume_path.stem[: -len("_이력서")]
        cover_path = src / f"{stem}_자소서.pdf"
        if not cover_path.exists():
            print(f"  [건너뜀] 자소서 없음: {stem}")
            continue

        record = _parse_resume(_pdf_text(resume_path))
        record["self_intro"] = _pdf_text(cover_path).strip()
        record["files"] = [
            {"kind": "resume", "path": str(resume_path)},
            {"kind": "cover_letter", "path": str(cover_path)},
        ]
        missing = [f for f in ("name", "email", "phone", "posting_title") if not record.get(f)]
        if missing:
            print(f"  [경고] {stem}: 필드 누락 {missing}")
        records.append(record)
        print(
            f"  {record['name']:<6} {record['email']:<28} "
            f"{record['career_years']}년  {len(record['skills'])}개 스킬  "
            f"자소서 {len(record['self_intro'])}자  → {record.get('posting_title')}"
        )

    Path(args.out).write_text(
        json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n{len(records)}건 → {args.out}")
    return 0


# ── API 투입 ────────────────────────────────────────────────────────────


class Api:
    def __init__(self, base: str):
        self.base = base.rstrip("/")
        self.token: str | None = None

    def _call(self, method: str, path: str, body: dict | None = None) -> dict:
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method)
        if data is not None:
            req.add_header("Content-Type", "application/json")
        if self.token:
            req.add_header("Authorization", f"Bearer {self.token}")
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")
            raise RuntimeError(f"{method} {path} → {exc.code} {detail}") from None
        return json.loads(raw) if raw else {}

    def login(self, email: str, password: str) -> None:
        self.token = self._call(
            "POST", "/api/v1/auth/login", {"email": email, "password": password}
        )["access_token"]

    def ensure_posting(self, title: str, description: str) -> int:
        """같은 제목의 공고가 있으면 그것을 쓰고, 없으면 open 상태로 만든다."""
        for posting in self._call("GET", "/api/v1/postings"):
            if posting["title"] == title:
                if posting["status"] != "open":
                    self._call(
                        "PATCH", f"/api/v1/postings/{posting['id']}", {"status": "open"}
                    )
                return posting["id"]
        created = self._call(
            "POST",
            "/api/v1/postings",
            {"title": title, "description": description, "status": "open"},
        )
        return created["id"]

    def presign(self, filename: str, kind: str, size_bytes: int) -> dict:
        return self._call(
            "POST",
            "/api/v1/public/files/presign-upload",
            {
                "filename": filename,
                "content_type": "application/pdf",
                "kind": kind,
                "size_bytes": size_bytes,
            },
        )

    def submit(self, posting_id: int, payload: dict) -> dict:
        return self._call(
            "POST", f"/api/v1/public/postings/{posting_id}/applications", payload
        )


def _upload(url: str, path: Path, size_bytes: int) -> None:
    """presigned URL 로 S3(로컬은 MinIO)에 직접 올린다. 본문은 API 서버를 지나가지 않는다."""
    body = path.read_bytes()
    req = urllib.request.Request(url, data=body, method="PUT")
    req.add_header("Content-Type", "application/pdf")
    # presign_put 이 서명에 크기를 넣으므로 헤더가 서명과 같아야 S3 가 받는다
    req.add_header("Content-Length", str(size_bytes))
    with urllib.request.urlopen(req, timeout=120):
        pass


# 공고 설명. 요약 Step2(적합도 평가)가 이 요건과 대조한다 — 비어 있으면 평가가 헛돈다.
POSTING_DESCRIPTIONS = {
    "백엔드 개발자 (Python·FastAPI)": (
        "Python·FastAPI 로 채용 관리 서비스의 API 를 만든다.\n"
        "필수: Python 실무 경험, 웹 프레임워크(FastAPI/Django/Flask) 경험, "
        "관계형 DB(PostgreSQL) 설계·튜닝 경험.\n"
        "우대: Docker·AWS 운영 경험, 비동기 작업 큐(Celery 등), 대용량 데이터 처리 경험."
    ),
    "프론트엔드 개발자 (React)": (
        "React·TypeScript 로 채용 담당자용 화면을 만든다.\n"
        "필수: React 실무 경험, TypeScript, 상태 관리 경험.\n"
        "우대: 디자인 시스템·접근성 경험, 테스트(Jest/Playwright), Next.js."
    ),
}


def cmd_ingest(args: argparse.Namespace) -> int:
    records = json.loads(Path(args.records).read_text(encoding="utf-8"))
    if args.limit:
        records = records[: args.limit]

    password = os.getenv("ADMIN_PASSWORD")
    if not password:
        sys.exit("ADMIN_PASSWORD 환경변수가 필요하다 (공고 생성에 로그인이 필요하다)")

    api = Api(args.api)
    api.login(args.admin, password)
    print(f"로그인 완료: {args.admin}")

    posting_ids: dict[str, int] = {}
    ok = 0
    failed: list[tuple[str, str]] = []
    started = time.perf_counter()

    for record in records:
        title = record["posting_title"]
        if title not in posting_ids:
            posting_ids[title] = api.ensure_posting(
                title, POSTING_DESCRIPTIONS.get(title, title)
            )
            print(f"공고 준비: {title} → id={posting_ids[title]}")

        try:
            submitted = []
            for item in record["files"]:
                path = Path(item["path"])
                size = path.stat().st_size
                signed = api.presign(path.name, item["kind"], size)
                _upload(signed["upload_url"], path, size)
                submitted.append(
                    {
                        "s3_key": signed["s3_key"],
                        "filename": path.name,
                        "size_bytes": size,
                        "content_type": "application/pdf",
                        "kind": item["kind"],
                    }
                )

            created = api.submit(
                posting_ids[title],
                {
                    "name": record["name"],
                    "email": record["email"],
                    "phone": record["phone"],
                    "education": record.get("education"),
                    "career_years": record.get("career_years"),
                    "skills": record.get("skills") or None,
                    "self_intro": record.get("self_intro"),
                    "privacy_agreed": True,
                    "files": submitted,
                },
            )
            ok += 1
            print(f"  [{ok}] {record['name']} → application_id={created['id']}")
        except Exception as exc:  # noqa: BLE001 — 한 건 실패로 전체가 멈추면 안 된다
            failed.append((record["name"], str(exc)))
            print(f"  [실패] {record['name']}: {exc}")

    elapsed = time.perf_counter() - started
    print(f"\n접수 {ok}건 / 실패 {len(failed)}건 · {elapsed:.1f}초")
    if failed:
        for name, err in failed:
            print(f"  - {name}: {err}")
    print(
        "\n요약·임베딩은 BackgroundTasks 라 응답 뒤에 돈다. "
        "잠시 뒤 `verify` 로 실제 생성 건수를 센다:\n"
        f"  python scripts/ingest_dummy_applications.py verify"
    )
    return 0


# ── 검증 ────────────────────────────────────────────────────────────────


def cmd_verify(args: argparse.Namespace) -> int:
    """DB 를 직접 보고 요약·임베딩이 몇 건 생겼는지 센다."""
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from sqlalchemy import func, select

    from app.db import SessionLocal, pgvector_ready
    from app.models import Application

    db = SessionLocal()
    try:
        total = db.scalar(
            select(func.count(Application.id)).where(Application.source == "form")
        )
        summarized = db.scalar(
            select(func.count(Application.id)).where(Application.ai_summary.isnot(None))
        )
        print(f"source=form 지원서: {total}건")
        print(f"ai_summary 있음:    {summarized}건")

        if not pgvector_ready():
            print("application_embeddings: pgvector 확장 없음 — 테이블 자체가 없다")
            return 1
        from app.models import ApplicationEmbedding

        embedded = db.scalar(select(func.count(ApplicationEmbedding.id)))
        print(f"임베딩:              {embedded}건")

        if args.query:
            from app.agent.embedder import search_similar

            ids = search_similar(db, args.query, limit=args.top)
            print(f"\n시맨틱 검색 '{args.query}' 상위 {args.top}:")
            for rank, app_id in enumerate(ids, 1):
                row = db.get(Application, app_id)
                skills = ", ".join(row.skills or [])
                print(f"  {rank}. {row.name} ({row.career_years}년) — {skills}")
    finally:
        db.close()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_parse = sub.add_parser("parse", help="PDF → JSON")
    p_parse.add_argument("--src", required=True, help="PDF 디렉터리")
    p_parse.add_argument("--out", default="records.json")
    p_parse.set_defaults(func=cmd_parse)

    p_ingest = sub.add_parser("ingest", help="JSON → API 투입")
    p_ingest.add_argument("--records", required=True)
    p_ingest.add_argument("--api", default="http://localhost:8000")
    p_ingest.add_argument("--admin", required=True, help="공고 생성용 admin 이메일")
    p_ingest.add_argument("--limit", type=int, default=0, help="앞 N 건만 (비용 시험용)")
    p_ingest.set_defaults(func=cmd_ingest)

    p_verify = sub.add_parser("verify", help="요약·임베딩 생성 건수 확인")
    p_verify.add_argument("--query", default="Python 경험자 찾아줘")
    p_verify.add_argument("--top", type=int, default=10)
    p_verify.set_defaults(func=cmd_verify)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
