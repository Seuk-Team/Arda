#!/usr/bin/env python3
"""J7 파트 A — 배치 파일 검증기.

사용법:
    python backend/scripts/seed/check_batch.py <JSON 파일>

파일 종류는 경로·파일명으로 판별한다.

    materials/names.json          성 50개 이상 / 이름 300개 이상
    materials/schools.json        학교 30개 이상
    materials/skill-patterns.json 직군 패턴 10개 이상
    sentences/<카테고리>-NN.json   문장 100개

규격은 docs/tasks/J7-더미데이터-생성기.md 파트 A를 따른다. 표준 라이브러리만 쓴다.
문장 길이는 치환 전 원문(text) 글자 수로 잰다.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from difflib import SequenceMatcher
from pathlib import Path

ALLOWED_VARS = ("학교", "전공", "기술", "경력", "직무", "회사명")
CATEGORIES = ("motivation", "growth", "strength", "experience", "goal")

SENTENCE_COUNT = 100
LEN_MIN, LEN_MAX = 40, 120
SIMILAR_RATIO = 0.90
MAX_LISTED = 20  # 오류·경고를 이만큼만 찍고 나머지는 건수로 줄인다 (--all로 전체)

MIN_LAST, MIN_FIRST = 50, 300
MIN_SCHOOLS = 30
MIN_SKILL_PATTERNS = 10

VAR_RE = re.compile(r"\{\{\s*([^{}]*?)\s*\}\}")
POLITE_RE = re.compile(r"(니다|어요|아요|에요|예요|세요|십시오)\.$")
WS_RE = re.compile(r"\s+")


class Report:
    """오류·경고를 모아 한 번에 출력한다. 오류가 하나라도 있으면 실패."""

    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.notes: list[str] = []

    def error(self, msg: str) -> None:
        self.errors.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)

    def note(self, msg: str) -> None:
        self.notes.append(msg)

    @property
    def ok(self) -> bool:
        return not self.errors


def norm(text: str) -> str:
    """공백을 모두 없앤 비교용 문자열."""
    return WS_RE.sub("", text)


def load_json(path: Path, rep: Report):
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        rep.error(f"파일이 없다: {path}")
        return None
    except UnicodeDecodeError as exc:
        rep.error(f"UTF-8로 읽을 수 없다: {exc}")
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        rep.error(f"JSON 파싱 실패 — {exc.lineno}행 {exc.colno}열: {exc.msg}")
        return None


def check_str_list(values, label: str, minimum: int, rep: Report, note: bool = True) -> None:
    """문자열 목록 공통 검사 — 타입·빈 값·중복·최소 건수.

    note=False면 건수 요약을 남기지 않는다. 항목마다 한 줄씩 찍혀 출력이 길어지는 것을 막는다.
    """
    if not isinstance(values, list):
        rep.error(f"{label}: 배열이어야 하는데 {type(values).__name__}이다")
        return
    seen: dict[str, int] = {}
    for i, v in enumerate(values):
        if not isinstance(v, str):
            rep.error(f"{label}[{i}]: 문자열이어야 하는데 {type(v).__name__}이다")
            continue
        if not v.strip():
            rep.error(f"{label}[{i}]: 빈 값이다")
            continue
        if v in seen:
            rep.error(f"{label}[{i}] {v!r}: {seen[v]}번과 중복이다")
        else:
            seen[v] = i
    if len(values) < minimum:
        rep.error(f"{label}: {len(values)}개 — 최소 {minimum}개가 필요하다")
    elif note:
        rep.note(f"{label}: {len(values)}개 (최소 {minimum})")


def check_names(data, rep: Report) -> None:
    if not isinstance(data, dict):
        rep.error(f"최상위는 객체여야 한다 — 지금은 {type(data).__name__}")
        return
    unknown = sorted(set(data) - {"last", "first"})
    if unknown:
        rep.error(f"허용되지 않은 키: {', '.join(unknown)} (last, first만 쓴다)")
    for key, minimum in (("last", MIN_LAST), ("first", MIN_FIRST)):
        if key not in data:
            rep.error(f"'{key}' 키가 없다")
            continue
        check_str_list(data[key], key, minimum, rep)


def check_schools(data, rep: Report) -> None:
    if not isinstance(data, list):
        rep.error(f"최상위는 배열이어야 한다 — 지금은 {type(data).__name__}")
        return
    seen: dict[str, int] = {}
    major_counts: list[int] = []
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            rep.error(f"[{i}]: 객체여야 하는데 {type(item).__name__}이다")
            continue
        unknown = sorted(set(item) - {"school", "majors"})
        if unknown:
            rep.error(f"[{i}]: 허용되지 않은 키 {', '.join(unknown)}")
        school = item.get("school")
        if not isinstance(school, str) or not school.strip():
            rep.error(f"[{i}]: 'school'이 비어 있거나 문자열이 아니다")
        elif school in seen:
            rep.error(f"[{i}] {school!r}: {seen[school]}번과 중복이다")
        else:
            seen[school] = i
        label = f"[{i}].majors" if not isinstance(school, str) else f"{school}.majors"
        majors = item.get("majors", [])
        check_str_list(majors, label, 1, rep, note=False)
        if isinstance(majors, list):
            major_counts.append(len(majors))
    if len(data) < MIN_SCHOOLS:
        rep.error(f"학교 {len(data)}개 — 최소 {MIN_SCHOOLS}개가 필요하다")
    else:
        rep.note(f"학교 {len(data)}개 (최소 {MIN_SCHOOLS})")
    if major_counts:
        rep.note(f"전공 총 {sum(major_counts)}개 · 학교당 {min(major_counts)}~{max(major_counts)}개")


def check_skill_patterns(data, rep: Report) -> None:
    if not isinstance(data, list):
        rep.error(f"최상위는 배열이어야 한다 — 지금은 {type(data).__name__}")
        return
    seen: dict[str, int] = {}
    skill_counts: list[int] = []
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            rep.error(f"[{i}]: 객체여야 하는데 {type(item).__name__}이다")
            continue
        unknown = sorted(set(item) - {"track", "skills"})
        if unknown:
            rep.error(f"[{i}]: 허용되지 않은 키 {', '.join(unknown)}")
        track = item.get("track")
        if not isinstance(track, str) or not track.strip():
            rep.error(f"[{i}]: 'track'이 비어 있거나 문자열이 아니다")
        elif track in seen:
            rep.error(f"[{i}] {track!r}: {seen[track]}번과 중복이다")
        else:
            seen[track] = i
        label = f"[{i}].skills" if not isinstance(track, str) else f"{track}.skills"
        skills = item.get("skills", [])
        check_str_list(skills, label, 1, rep, note=False)
        if isinstance(skills, list):
            skill_counts.append(len(skills))
    if len(data) < MIN_SKILL_PATTERNS:
        rep.error(f"직군 패턴 {len(data)}개 — 최소 {MIN_SKILL_PATTERNS}개가 필요하다")
    else:
        rep.note(f"직군 패턴 {len(data)}개 (최소 {MIN_SKILL_PATTERNS})")
    if skill_counts:
        rep.note(f"기술 총 {sum(skill_counts)}개 · 패턴당 {min(skill_counts)}~{max(skill_counts)}개")


def check_sentence_item(i: int, item, rep: Report) -> str | None:
    """문장 한 건을 검사하고 text를 돌려준다. 검사 불가면 None."""
    if not isinstance(item, dict):
        rep.error(f"[{i}]: 객체여야 하는데 {type(item).__name__}이다")
        return None

    unknown = sorted(set(item) - {"text", "vars"})
    if unknown:
        rep.error(f"[{i}]: 허용되지 않은 키 {', '.join(unknown)} (text, vars만 쓴다)")

    text = item.get("text")
    if not isinstance(text, str) or not text.strip():
        rep.error(f"[{i}]: 'text'가 비어 있거나 문자열이 아니다")
        return None

    length = len(text)
    if not LEN_MIN <= length <= LEN_MAX:
        rep.error(f"[{i}]: 길이 {length}자 — {LEN_MIN}~{LEN_MAX}자를 벗어난다 | {text}")

    used = VAR_RE.findall(text)
    bad = [v for v in used if v not in ALLOWED_VARS]
    if bad:
        rep.error(f"[{i}]: 허용되지 않은 변수 {{{{{'}}, {{'.join(sorted(set(bad)))}}}}} | {text}")

    # 짝이 안 맞는 중괄호 — {{...}}를 걷어낸 뒤 남으면 오타다
    if "{" in VAR_RE.sub("", text) or "}" in VAR_RE.sub("", text):
        rep.error(f"[{i}]: 중괄호 짝이 맞지 않는다 | {text}")

    declared = item.get("vars")
    if not isinstance(declared, list) or not all(isinstance(v, str) for v in declared):
        rep.error(f"[{i}]: 'vars'는 문자열 배열이어야 한다")
    else:
        if len(declared) != len(set(declared)):
            rep.error(f"[{i}]: 'vars' 안에 중복이 있다 — {declared}")
        if set(declared) != set(used):
            only_declared = sorted(set(declared) - set(used))
            only_used = sorted(set(used) - set(declared))
            parts = []
            if only_declared:
                parts.append(f"선언만 됨 {only_declared}")
            if only_used:
                parts.append(f"본문에만 있음 {only_used}")
            rep.error(f"[{i}]: 'vars'가 본문과 다르다 — {' / '.join(parts)} | {text}")

    if not POLITE_RE.search(text.rstrip()):
        rep.warn(f"[{i}]: 존댓말 종결어미로 끝나지 않는 것 같다 | {text}")

    return text


def check_duplicates(texts: dict[int, str], rep: Report) -> None:
    """같은 파일 안 중복 — 완전 일치 + 공백 제거 후 일치."""
    exact: dict[str, int] = {}
    squashed: dict[str, int] = {}
    for i, text in texts.items():
        if text in exact:
            rep.error(f"[{i}]: {exact[text]}번과 완전히 같다 | {text}")
        else:
            exact[text] = i
            key = norm(text)
            if key in squashed:
                rep.error(f"[{i}]: {squashed[key]}번과 공백만 다르다 | {text}")
            else:
                squashed[key] = i


def similar_pairs(items: list[tuple[str, str]], rep: Report, label: str) -> None:
    """유사문 경고. quick_ratio로 먼저 걸러 비용을 줄인다."""
    matcher = SequenceMatcher(autojunk=False)
    for idx, (a_id, a_text) in enumerate(items):
        a_norm = norm(a_text)
        matcher.set_seq2(a_norm)
        for b_id, b_text in items[idx + 1 :]:
            b_norm = norm(b_text)
            if abs(len(a_norm) - len(b_norm)) > len(a_norm) * (1 - SIMILAR_RATIO) * 2:
                continue
            matcher.set_seq1(b_norm)
            if matcher.real_quick_ratio() < SIMILAR_RATIO:
                continue
            if matcher.quick_ratio() < SIMILAR_RATIO:
                continue
            ratio = matcher.ratio()
            if ratio >= SIMILAR_RATIO:
                rep.warn(f"{label} {a_id} ↔ {b_id}: {ratio:.0%} 유사하다\n    {a_text}\n    {b_text}")


def check_siblings(path: Path, category: str, texts: dict[int, str], rep: Report) -> list[tuple[str, str]]:
    """같은 카테고리의 다른 배치 파일과 겹치는지 본다.

    지시서 배치 005·007·009·011·013이 "다른 배치 파일과 겹치지 않게"를 요구하므로 함께 검사한다.
    다른 파일을 읽기만 하고 고치지 않는다.
    """
    others: list[tuple[str, str]] = []
    siblings = sorted(p for p in path.parent.glob(f"{category}-*.json") if p.resolve() != path.resolve())
    if not siblings:
        rep.note(f"같은 카테고리의 다른 배치 파일: 없음")
        return others

    mine_exact = {t: i for i, t in texts.items()}
    mine_squashed = {norm(t): i for i, t in texts.items()}
    for sib in siblings:
        try:
            data = json.loads(sib.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            rep.warn(f"{sib.name}을 읽지 못해 교차 검사를 건너뛴다 — {exc}")
            continue
        if not isinstance(data, list):
            rep.warn(f"{sib.name}의 최상위가 배열이 아니라 교차 검사를 건너뛴다")
            continue
        count = 0
        for j, item in enumerate(data):
            if not isinstance(item, dict):
                continue
            text = item.get("text")
            if not isinstance(text, str):
                continue
            count += 1
            others.append((f"{sib.name}[{j}]", text))
            if text in mine_exact:
                rep.error(f"[{mine_exact[text]}]: {sib.name}[{j}]와 완전히 같다 | {text}")
            elif norm(text) in mine_squashed:
                rep.error(f"[{mine_squashed[norm(text)]}]: {sib.name}[{j}]와 공백만 다르다 | {text}")
        rep.note(f"교차 검사: {sib.name} {count}건")
    return others


def check_sentences(path: Path, data, category: str, rep: Report) -> None:
    if not isinstance(data, list):
        rep.error(f"최상위는 배열이어야 한다 — 지금은 {type(data).__name__}")
        return

    if len(data) != SENTENCE_COUNT:
        rep.error(f"{len(data)}건 — {SENTENCE_COUNT}건이어야 한다")
    else:
        rep.note(f"{len(data)}건")

    texts: dict[int, str] = {}
    for i, item in enumerate(data):
        text = check_sentence_item(i, item, rep)
        if text is not None:
            texts[i] = text

    check_duplicates(texts, rep)

    mine = [(f"[{i}]", t) for i, t in sorted(texts.items())]
    similar_pairs(mine, rep, "유사")

    others = check_siblings(path, category, texts, rep)
    if others:
        matcher = SequenceMatcher(autojunk=False)
        for a_id, a_text in mine:
            a_norm = norm(a_text)
            matcher.set_seq2(a_norm)
            for b_id, b_text in others:
                b_norm = norm(b_text)
                if abs(len(a_norm) - len(b_norm)) > len(a_norm) * (1 - SIMILAR_RATIO) * 2:
                    continue
                matcher.set_seq1(b_norm)
                if matcher.real_quick_ratio() < SIMILAR_RATIO or matcher.quick_ratio() < SIMILAR_RATIO:
                    continue
                ratio = matcher.ratio()
                if ratio >= SIMILAR_RATIO:
                    rep.warn(f"유사(교차) {a_id} ↔ {b_id}: {ratio:.0%} 유사하다\n    {a_text}\n    {b_text}")

    lengths = [len(t) for t in texts.values()]
    if lengths:
        rep.note(f"길이 {min(lengths)}~{max(lengths)}자 (평균 {sum(lengths) / len(lengths):.0f})")
    var_count = sum(1 for t in texts.values() if VAR_RE.search(t))
    rep.note(f"변수를 쓴 문장 {var_count}건 / {len(texts)}건")


def classify(path: Path) -> tuple[str, str | None]:
    """파일 종류와 (문장이면) 카테고리를 돌려준다."""
    name = path.name
    parent = path.parent.name
    if name == "names.json":
        return "names", None
    if name == "schools.json":
        return "schools", None
    if name == "skill-patterns.json":
        return "skill-patterns", None
    if parent == "sentences" or re.fullmatch(r"[a-z]+-\d{2}\.json", name):
        stem = path.stem
        m = re.fullmatch(r"([a-z]+)-(\d{2})", stem)
        if not m:
            return "unknown", None
        category = m.group(1)
        return "sentences", category
    return "unknown", None


def print_list(items: list[str], marker: str, limit: int | None) -> None:
    shown = items if limit is None else items[:limit]
    for x in shown:
        print(f"  {marker} {x}")
    if limit is not None and len(items) > limit:
        print(f"  {marker} … 외 {len(items) - limit}건 — 전체를 보려면 --all")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="J7 파트 A 배치 파일을 규격에 맞는지 검사한다.",
    )
    parser.add_argument("file", type=Path, help="검사할 JSON 파일 하나")
    parser.add_argument(
        "--all",
        action="store_true",
        help=f"오류·경고를 {MAX_LISTED}건까지만 줄여 찍지 않고 전부 찍는다",
    )
    args = parser.parse_args(argv)

    path: Path = args.file
    rep = Report()

    kind, category = classify(path)
    labels = {
        "names": "재료 사전 — 성·이름 풀",
        "schools": "재료 사전 — 학교·전공",
        "skill-patterns": "재료 사전 — 직군별 기술 조합",
        "sentences": f"문장 은행 — {category}",
    }

    print(f"J7 배치 검증 — {path}")
    print(f"종류: {labels.get(kind, '판별 실패')}")

    if kind == "unknown":
        print()
        print("규격에 있는 파일명이 아니다. 다음 중 하나여야 한다:")
        print("  materials/names.json · materials/schools.json · materials/skill-patterns.json")
        print(f"  sentences/<카테고리>-NN.json  (카테고리: {', '.join(CATEGORIES)})")
        return 2

    if kind == "sentences" and category not in CATEGORIES:
        rep.error(f"'{category}'는 규격에 없는 카테고리다 — {', '.join(CATEGORIES)} 중 하나여야 한다")

    data = load_json(path, rep)
    if data is not None:
        if kind == "names":
            check_names(data, rep)
        elif kind == "schools":
            check_schools(data, rep)
        elif kind == "skill-patterns":
            check_skill_patterns(data, rep)
        elif kind == "sentences":
            check_sentences(path, data, category or "", rep)

    if rep.notes:
        print()
        for note in rep.notes:
            print(f"  · {note}")

    limit = None if args.all else MAX_LISTED

    if rep.warnings:
        print()
        print(f"경고 {len(rep.warnings)}건 — 통과를 막지는 않는다")
        print_list(rep.warnings, "!", limit)

    if rep.errors:
        print()
        print(f"오류 {len(rep.errors)}건")
        print_list(rep.errors, "x", limit)

    print()
    if rep.ok:
        print(f"통과 — 오류 0건, 경고 {len(rep.warnings)}건")
        return 0
    print(f"실패 — 오류 {len(rep.errors)}건, 경고 {len(rep.warnings)}건")
    return 1


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
