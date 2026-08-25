"""추출 PoC 실행 — 샘플 폴더를 훑어 결과표(markdown)를 만든다.

    uv run python -m app.agent.extract.run_poc [샘플폴더] [출력.md]

기본값: backend/samples/resumes → backend/app/agent/extract/POC-RESULT.md
LLM 호출 없음 (비용 0).
"""

from __future__ import annotations

import sys
from pathlib import Path

from . import ExtractResult, extract_file, pypdf_available

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parents[2]
DEFAULT_SAMPLES = HERE / "samples"
DEFAULT_OUT = HERE / "POC-RESULT.md"


def run(samples: Path) -> list[ExtractResult]:
    if not samples.exists():
        raise SystemExit(f"샘플 폴더가 없다: {samples}\n먼저 make_samples.py 를 실행해라.")
    files = sorted(p for p in samples.rglob("*") if p.is_file())
    return [extract_file(p) for p in files]


def _rel(p: Path) -> str:
    """저장소 밖 절대경로가 문서에 박히지 않게 backend/ 기준 상대경로로."""
    try:
        return str(p.resolve().relative_to(BACKEND))
    except ValueError:
        return p.name


def to_markdown(rows: list[ExtractResult], samples: Path) -> str:
    total = len(rows)
    ok = sum(1 for r in rows if r.ok)
    by_fmt: dict[str, list[ExtractResult]] = {}
    for r in rows:
        by_fmt.setdefault(r.fmt, []).append(r)

    engine = "pypdf" if pypdf_available() else "stdlib 폴백 (pypdf 미설치)"
    # 한글 검증 여부는 **PDF 행만** 본다. docx 샘플은 항상 한글이라
    # 전체 행을 보면 영문 PDF로 돌려도 "검증됨"으로 잘못 뜬다.
    korean = any(
        r.ok and r.fmt == "pdf" and any("\uac00" <= c <= "\ud7a3" for c in r.preview)
        for r in rows
    )
    out = [
        "# 이력서 텍스트 추출 PoC — 결과표",
        "",
        "> 자동 생성: `uv run python -m app.agent.extract.run_poc`",
        f"> 샘플: `backend/{_rel(samples)}` · 총 {total}건 · 성공 {ok}건",
        f"> PDF 엔진: **{engine}** · 한글 본문 검증: **{'예' if korean else '아니오'}**",
        "",
        "## 형식별 요약",
        "",
        "| 형식 | 건수 | 성공 | 판정 |",
        "|---|---|---|---|",
    ]
    verdict = {
        "pdf": "텍스트 PDF는 전부 성공해야 한다 (스캔본 제외)",
        "docx": "전부 성공 기대",
        "hwp": "실패 예상 — 수동 폴백",
    }
    for fmt, items in sorted(by_fmt.items()):
        s = sum(1 for i in items if i.ok)
        out.append(f"| {fmt} | {len(items)} | {s} | {verdict.get(fmt, '-')} |")

    out += [
        "",
        "## 파일별",
        "",
        "| 파일 | 형식 | 엔진 | 결과 | 글자수 | 미리보기 / 사유 |",
        "|---|---|---|---|---|---|",
    ]
    for r in rows:
        name = Path(r.path).name
        mark = "✅" if r.ok else "❌"
        tail = r.preview if r.ok else (r.error or "")
        tail = tail.replace("|", "\\|")
        out.append(f"| `{name}` | {r.fmt} | {r.engine} | {mark} | {r.chars} | {tail} |")

    out += [
        "",
        "## 폴백 규칙",
        "",
        "- **HWP**: 자동 추출 미지원 → 담당자가 상세 폼에 수동 입력. 접수는 막지 않는다.",
        "- **스캔본 PDF**: 텍스트 0글자 → 실패로 표시하고 같은 수동 폴백.",
        "- 추출 실패는 `ai_summary`를 NULL로 두고, 화면에는 '요약 없음'으로만 보인다.",
        "",
        "## 의존성 — 백엔드 오너 협의 필요",
        "",
        "- **`pypdf` (런타임)**: 한글 PDF 추출에 필요하다. 없으면 stdlib 폴백으로 내려가고 "
        "폰트를 심은 PDF에서 텍스트를 얻지 못한다 — 즉 실이력서에서 실패한다.",
        "- **`fpdf2` (개발 전용)**: 한글 샘플 생성에만 쓴다. 런타임에는 필요 없다.",
        "- `backend/pyproject.toml`은 백엔드 도메인 파일이라 이 PoC에서 고치지 않았다. "
        "추가는 백엔드 오너와 인터페이스 PR로 합의한다.",
        "",
        "## 비용",
        "",
        "이 PoC는 **LLM을 호출하지 않는다.** 요약 생성(W3)에서만 호출하고, 더미 10만 건에는 절대 돌리지 않는다.",
        "",
    ]
    return "\n".join(out)


def main() -> None:
    samples = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_SAMPLES
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_OUT
    rows = run(samples)
    out.write_text(to_markdown(rows, samples), encoding="utf-8")
    ok = sum(1 for r in rows if r.ok)
    print(f"{len(rows)}건 처리 · 성공 {ok}건 → {out}")


if __name__ == "__main__":
    main()
