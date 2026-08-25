"""프롬프트 파일 로더.

프롬프트는 코드에 문자열로 흩어놓지 않고 이 폴더의 파일로 관리한다
(ADR-0011 §4 기록·재현성).

파일명 규칙
    <이름>.v<번호>.md      예: summarize.v1.md

내용을 고치면 번호를 올리고 이전 파일을 지우지 않는다.
`applications.ai_summary_model` 과 함께 "어느 프롬프트로 만든 요약인지" 를 남기기 위함이다.

변수는 `{{이름}}` 자리표시자로 쓴다. LLM 출력 예시에 중괄호(JSON)가 섞이므로
str.format 은 쓰지 않는다.
"""

from __future__ import annotations

import re
from pathlib import Path

PROMPT_DIR = Path(__file__).parent
_FILENAME = re.compile(r"^(?P<name>[a-z0-9_]+)\.v(?P<version>\d+)\.md$")
_PLACEHOLDER = re.compile(r"\{\{\s*(\w+)\s*\}\}")


class PromptNotFound(LookupError):
    pass


class MissingVariable(KeyError):
    pass


def available() -> dict[str, list[int]]:
    """{프롬프트 이름: [버전, ...]} — 버전은 오름차순."""
    found: dict[str, list[int]] = {}
    for path in PROMPT_DIR.glob("*.md"):
        matched = _FILENAME.match(path.name)
        if matched:
            found.setdefault(matched["name"], []).append(int(matched["version"]))
    return {name: sorted(versions) for name, versions in sorted(found.items())}


def resolve(name: str, version: int | None = None) -> tuple[Path, int]:
    """프롬프트 파일 경로와 버전. version 을 생략하면 최신 버전."""
    versions = available().get(name)
    if not versions:
        raise PromptNotFound(f"프롬프트 없음: {name} (있는 것: {sorted(available())})")
    if version is None:
        version = versions[-1]
    elif version not in versions:
        raise PromptNotFound(f"{name} v{version} 없음 (있는 버전: {versions})")
    return PROMPT_DIR / f"{name}.v{version}.md", version


def load(name: str, version: int | None = None) -> tuple[str, str]:
    """원문과 버전 태그를 돌려준다. 버전 태그는 로그·DB 기록용."""
    path, resolved = resolve(name, version)
    return path.read_text(encoding="utf-8"), f"{name}.v{resolved}"


def variables(name: str, version: int | None = None) -> set[str]:
    text, _ = load(name, version)
    return set(_PLACEHOLDER.findall(text))


def render(name: str, version: int | None = None, **values: object) -> tuple[str, str]:
    """자리표시자를 채운 프롬프트와 버전 태그.

    빈 값을 조용히 넘기면 "요건 없음" 같은 문장이 통째로 사라진 프롬프트가 나가므로,
    채우지 못한 자리표시자는 실패로 처리한다.
    """
    text, tag = load(name, version)
    needed = set(_PLACEHOLDER.findall(text))
    missing = needed - set(values)
    if missing:
        raise MissingVariable(f"{tag} 에 필요한 변수 누락: {sorted(missing)}")

    def replace(match: re.Match[str]) -> str:
        return str(values[match.group(1)])

    return _PLACEHOLDER.sub(replace, text), tag
