"""엔티티 해석 레이어 (W4 — STT 전처리).

Whisper 전사 결과의 노이즈를 정규화한 뒤 에이전트에 전달한다.
- 한글 수사 → 숫자 변환
- 기술 용어 음차 정규화
- 지원자 이름 유사도 매칭 (DB 조회 기반)
"""

from __future__ import annotations

import re
import unicodedata

# ── 한글 수사 → 숫자 ──────────────────────────────────────

_SINO_UNITS: dict[str, int] = {
    "영": 0, "일": 1, "이": 2, "삼": 3, "사": 4,
    "오": 5, "육": 6, "칠": 7, "팔": 8, "구": 9,
}

_SINO_SCALES: dict[str, int] = {
    "십": 10, "백": 100, "천": 1_000,
    "만": 10_000, "억": 100_000_000,
}

_NATIVE_NUMS: dict[str, int] = {
    "한": 1, "두": 2, "세": 3, "네": 4, "다섯": 5,
    "여섯": 6, "일곱": 7, "여덟": 8, "아홉": 9, "열": 10,
    "스물": 20, "서른": 30, "마흔": 40, "쉰": 50,
}

_COUNTERS = r"(?=\s*(?:년|개|명|건|번|회|일|월|주|시간|살|원|점|배|권|장|벌|채|대|마리|그루|자루|켤레|쌍|통|병|잔|그릇|줄|칸|층|평|퍼센트|%))"

_SINO_COMPOUND = re.compile(
    r"(?:" + "|".join(sorted(_SINO_SCALES.keys(), key=len, reverse=True)) + r")"
)

_SINO_PATTERN = re.compile(
    r"(?:" + "|".join(sorted(_SINO_UNITS.keys() | _SINO_SCALES.keys(), key=len, reverse=True)) + r"){2,}"
    r"|"
    r"(?:" + "|".join(sorted(_SINO_UNITS.keys(), key=len, reverse=True)) + r")" + _COUNTERS
)

_NATIVE_PATTERN = re.compile(
    r"(?:" + "|".join(sorted(_NATIVE_NUMS, key=len, reverse=True)) + r")+"
    + _COUNTERS
)


def _parse_sino(text: str) -> int | None:
    """한자어 수사 문자열을 정수로 변환. '삼백이십오' → 325"""
    if not text:
        return None
    result = 0
    group = 0
    temp = 0
    for ch in text:
        if ch in _SINO_UNITS:
            temp = _SINO_UNITS[ch]
        elif ch in _SINO_SCALES:
            scale = _SINO_SCALES[ch]
            if scale >= 10_000:
                result += (group + max(temp, 1)) * scale
                group = 0
                temp = 0
            else:
                group += max(temp, 1) * scale
                temp = 0
    result += group + temp
    return result if result > 0 else None


def _parse_native(text: str) -> int | None:
    """고유어 수사 문자열을 정수로 변환. '스물세' → 23"""
    if not text:
        return None
    total = 0
    remaining = text
    for word in sorted(_NATIVE_NUMS, key=len, reverse=True):
        if word in remaining:
            total += _NATIVE_NUMS[word]
            remaining = remaining.replace(word, "", 1)
    return total if total > 0 else None


def normalize_numbers(text: str) -> str:
    """텍스트 속 한글 수사를 아라비아 숫자로 변환.

    '경력 이년 이상' → '경력 2년 이상'
    '삼백이십오 명'  → '325 명'
    """
    def _replace_sino(m: re.Match) -> str:
        v = _parse_sino(m.group())
        return str(v) if v is not None else m.group()

    def _replace_native(m: re.Match) -> str:
        v = _parse_native(m.group())
        return str(v) if v is not None else m.group()

    text = _SINO_PATTERN.sub(_replace_sino, text)
    text = _NATIVE_PATTERN.sub(_replace_native, text)
    return text


# ── 기술 용어 음차 정규화 ────────────────────────────────

_TECH_ALIASES: dict[str, str] = {
    "패스트에이피아이": "FastAPI",
    "패스트 에이피아이": "FastAPI",
    "패스트api": "FastAPI",
    "리액트": "React",
    "리엑트": "React",
    "리액트네이티브": "React Native",
    "넥스트제이에스": "Next.js",
    "넥스트js": "Next.js",
    "넥스트 제이에스": "Next.js",
    "뷰제이에스": "Vue.js",
    "뷰js": "Vue.js",
    "앵귤러": "Angular",
    "타입스크립트": "TypeScript",
    "자바스크립트": "JavaScript",
    "파이썬": "Python",
    "파이선": "Python",
    "장고": "Django",
    "플라스크": "Flask",
    "플러터": "Flutter",
    "코틀린": "Kotlin",
    "스위프트": "Swift",
    "도커": "Docker",
    "쿠버네티스": "Kubernetes",
    "쿠버네틱스": "Kubernetes",
    "포스트그레스": "PostgreSQL",
    "포스트그래스": "PostgreSQL",
    "포스그래스": "PostgreSQL",
    "마이에스큐엘": "MySQL",
    "몽고디비": "MongoDB",
    "레디스": "Redis",
    "엘라스틱서치": "Elasticsearch",
    "깃허브": "GitHub",
    "깃헙": "GitHub",
    "깃랩": "GitLab",
    "에이더블유에스": "AWS",
    "아마존웹서비스": "AWS",
    "노드제이에스": "Node.js",
    "노드js": "Node.js",
    "스프링": "Spring",
    "스프링부트": "Spring Boot",
    "텐서플로": "TensorFlow",
    "텐서플로우": "TensorFlow",
    "파이토치": "PyTorch",
    "씨플플": "C++",
    "씨샵": "C#",
    "씨쁠쁠": "C++",
    "고랭": "Go",
    "러스트": "Rust",
    "루비": "Ruby",
    "스칼라": "Scala",
    "그래프큐엘": "GraphQL",
}

_TECH_PATTERN = re.compile(
    "|".join(re.escape(k) for k in sorted(_TECH_ALIASES, key=len, reverse=True)),
    re.IGNORECASE,
)


def normalize_tech_terms(text: str) -> str:
    """음차 표기된 기술 용어를 정식 영문명으로 변환."""
    return _TECH_PATTERN.sub(lambda m: _TECH_ALIASES[m.group().lower()], text)


# ── 이름 유사도 매칭 ─────────────────────────────────────

_CHO = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"
_JUNG = "ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ"
_JONG = ("", "ㄱ", "ㄲ", "ㄳ", "ㄴ", "ㄵ", "ㄶ", "ㄷ", "ㄹ",
         "ㄺ", "ㄻ", "ㄼ", "ㄽ", "ㄾ", "ㄿ", "ㅀ", "ㅁ", "ㅂ",
         "ㅄ", "ㅅ", "ㅆ", "ㅇ", "ㅈ", "ㅊ", "ㅋ", "ㅌ", "ㅍ", "ㅎ")


def _decompose_hangul(char: str) -> tuple[str, ...]:
    """한글 한 글자를 초·중·종성으로 분해."""
    code = ord(char) - 0xAC00
    if code < 0 or code > 11171:
        return (char,)
    cho = code // (21 * 28)
    jung = (code % (21 * 28)) // 28
    jong = code % 28
    parts = [_CHO[cho], _JUNG[jung]]
    if jong:
        parts.append(_JONG[jong])
    return tuple(parts)


def extract_chosung(text: str) -> str:
    """문자열에서 초성만 추출. '김도현' → 'ㄱㄷㅎ'"""
    result = []
    for ch in text:
        if "가" <= ch <= "힣":
            result.append(_decompose_hangul(ch)[0])
        else:
            result.append(ch)
    return "".join(result)


def edit_distance(a: str, b: str) -> int:
    """레벤슈타인 편집 거리."""
    if len(a) < len(b):
        a, b = b, a
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        curr = [i]
        for j, cb in enumerate(b, 1):
            cost = 0 if ca == cb else 1
            curr.append(min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + cost))
        prev = curr
    return prev[-1]


def _jamo_distance(a: str, b: str) -> int:
    """자모 분해 후 편집 거리. 음절 단위보다 세밀한 비교."""
    ja = []
    for ch in a:
        ja.extend(_decompose_hangul(ch))
    jb = []
    for ch in b:
        jb.extend(_decompose_hangul(ch))
    return edit_distance("".join(ja), "".join(jb))


def find_similar_names(
    query: str,
    candidates: list[str],
    *,
    max_distance: int = 2,
    chosung_match: bool = True,
) -> list[tuple[str, float]]:
    """후보 이름 목록에서 query와 유사한 이름을 찾는다.

    반환: [(이름, 유사도 점수)] — 점수가 높을수록 유사. 1.0 = 완전 일치.
    """
    query_clean = query.replace(" ", "").strip()
    query_cho = extract_chosung(query_clean)

    results: list[tuple[str, float]] = []
    for name in candidates:
        name_clean = name.replace(" ", "").strip()

        if query_clean == name_clean:
            results.append((name, 1.0))
            continue

        if chosung_match and extract_chosung(name_clean) == query_cho:
            results.append((name, 0.9))
            continue

        dist = _jamo_distance(query_clean, name_clean)
        max_len = max(len(query_clean), len(name_clean))
        if max_len == 0:
            continue

        jamo_a = []
        for ch in query_clean:
            jamo_a.extend(_decompose_hangul(ch))
        jamo_b = []
        for ch in name_clean:
            jamo_b.extend(_decompose_hangul(ch))
        max_jamo_len = max(len(jamo_a), len(jamo_b))

        if dist <= max_distance and max_jamo_len > 0:
            score = 1.0 - (dist / max_jamo_len)
            results.append((name, round(score, 3)))

    results.sort(key=lambda x: x[1], reverse=True)
    return results


# ── 통합 전처리 ──────────────────────────────────────────

def resolve_entities(text: str) -> str:
    """STT 전사 결과를 에이전트 입력에 맞게 전처리.

    1. 한글 수사 → 숫자
    2. 기술 용어 음차 → 정식 영문명
    3. 불필요한 조사 정리 ('씨', '님' 등)
    """
    text = normalize_tech_terms(text)
    text = normalize_numbers(text)
    text = re.sub(r"(\w)\s*(?:씨|님)\s", r"\1 ", text)
    return text.strip()
