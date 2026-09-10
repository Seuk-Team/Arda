"""적합도 확인용 지원자 투입 — 공개 지원 폼으로 넣는다. 로그인이 필요 없다.

    python scripts/fit_check/submit.py --role frontend --posting 12
    python scripts/fit_check/submit.py --role backend  --token <공개 링크 토큰>
    python scripts/fit_check/submit.py --role frontend --posting 12 --dry-run

    # 이력서·자기소개서 PDF 를 함께 붙여 실제 지원자처럼 투입 (F1·F2 파이프라인 검증)
    python scripts/fit_check/submit.py --role frontend --posting 12 \\
        --files-dir "C:/Users/suteagy/Desktop/fit-check-지원자24명"

- `--posting` 은 공고 id, `--token` 은 `/apply/<token>` 의 토큰. 둘 중 하나.
- `--files-dir` 를 주면 그 폴더에서 `{이름}_이력서.pdf` · `{이름}_자기소개서.pdf` 를 찾아
  presign (`/public/files/presign-upload`) → S3 PUT → 지원서 files 에 붙여 함께 제출한다.
  최유진처럼 FE·BE 양쪽에 지원한 사람은 `최유진(FE)_...` · `최유진(BE)_...` 를 쓴다.
  파일이 없으면 그 지원자는 파일 없이 (기존 방식대로) 제출된다.
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


def _put_s3(upload_url: str, path: Path, content_type: str) -> int:
    """presigned PUT 으로 S3 에 파일을 올린다. 성공 시 200."""
    data = path.read_bytes()
    req = urllib.request.Request(
        upload_url, data=data, method="PUT",
        headers={"Content-Type": content_type},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


def _find_pdfs(files_dir: Path, name: str, role: str) -> list[Path]:
    """이름 → 그 사람의 이력서·자기소개서 PDF 경로 2개. 최유진 은 역할로 태그된 파일을 찾는다."""
    tag = "(FE)" if role == "frontend" else "(BE)"
    candidates = [
        (f"{name}{tag}_이력서.pdf",     "resume"),
        (f"{name}_이력서.pdf",           "resume"),
        (f"{name}{tag}_자기소개서.pdf", "cover_letter"),
        (f"{name}_자기소개서.pdf",       "cover_letter"),
    ]
    found: dict[str, Path] = {}
    for fname, kind in candidates:
        p = files_dir / fname
        if p.exists() and kind not in found:
            found[kind] = p
    return [found[k] for k in ("resume", "cover_letter") if k in found]


def _upload_pdf(base: str, path: Path, kind: str) -> dict | None:
    """presign → S3 PUT → `SubmittedFile` dict 반환. 실패 시 None."""
    size = path.stat().st_size
    presign_body = {
        "filename": path.name,
        "content_type": "application/pdf",
        "kind": kind,
        "size_bytes": size,
    }
    code, res = _post(f"{base}/public/files/presign-upload", presign_body)
    if code != 200:
        print(f"    ✗ presign 실패 {code}: {res.get('message') or res}")
        return None
    upload_url = res["upload_url"]
    s3_key = res["s3_key"]

    put_code = _put_s3(upload_url, path, "application/pdf")
    if put_code != 200:
        print(f"    ✗ S3 PUT 실패 {put_code}  {path.name}")
        return None
    return {
        "s3_key": s3_key,
        "filename": path.name,
        "size_bytes": size,
        "content_type": "application/pdf",
        "kind": kind,
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--role", choices=["frontend", "backend"], required=True)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--posting", type=int, help="공고 id")
    g.add_argument("--token", help="공개 링크 토큰 (/apply/<token>)")
    p.add_argument("--base", default=BASE)
    p.add_argument("--suffix", default="", help="이메일 로컬파트에 +suffix 를 붙여 재투입")
    p.add_argument("--only", nargs="*", help="이 이메일(들)만 넣는다")
    p.add_argument("--files-dir", help="이력서·자기소개서 PDF 폴더 (평탄화된 {이름}_이력서.pdf 형식)")
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

    files_dir = Path(a.files_dir).expanduser() if a.files_dir else None
    if files_dir and not files_dir.exists():
        print(f"✗ --files-dir 이 없다: {files_dir}")
        return 1

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

        submitted_files: list[dict] = []
        if files_dir:
            pdfs = _find_pdfs(files_dir, x["name"], a.role)
            for pdf in pdfs:
                kind = "resume" if "이력서" in pdf.name else "cover_letter"
                if a.dry_run:
                    print(f"    (dry) 업로드 예정 {pdf.name} [{kind}]")
                    continue
                item = _upload_pdf(a.base, pdf, kind)
                if item:
                    submitted_files.append(item)
                    print(f"    ↑ 업로드 {pdf.name} ({item['size_bytes']:,} B)")

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
            "files": submitted_files,
        }
        tag = f"{x['name']:<10} {email:<38} 기대 {x['expect']['tier']}  파일 {len(submitted_files)}"
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
