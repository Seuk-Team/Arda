#!/usr/bin/env python
"""더미 데이터 생성기 — 공고 10개 + 지원서 100,000건.

재료 (materials/*, sentences/*)를 조합해 자기소개서 전원 상이하게 생성.
단계 분포: 접수 50% / 서류 25% / 면접 15% / 합격 4% / 불합격 6%
"""

import argparse
import json
import os
import random
import re
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import func, select, text

# 경로 설정
SCRIPT_DIR = Path(__file__).parent
BACKEND_DIR = SCRIPT_DIR.parent
SEED_DIR = SCRIPT_DIR / "seed"
MATERIALS_DIR = SEED_DIR / "materials"
SENTENCES_DIR = SEED_DIR / "sentences"

sys.path.insert(0, str(BACKEND_DIR))


def load_dotenv(path: Path) -> None:
    """.env 를 환경변수로 올린다. 이미 설정된 값은 덮어쓰지 않는다.

    app.db 가 임포트 시점에 DATABASE_URL 을 읽으므로 그 전에 불러야 한다.
    """
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


load_dotenv(BACKEND_DIR / ".env")

from app.db import Base, SessionLocal, engine  # noqa: E402
from app.models import STAGES, Application, JobPosting, StageHistory  # noqa: E402


def load_materials():
    """재료 JSON 파일 로드."""
    with open(MATERIALS_DIR / "names.json", encoding="utf-8") as f:
        names = json.load(f)
    with open(MATERIALS_DIR / "schools.json", encoding="utf-8") as f:
        schools = json.load(f)
    with open(MATERIALS_DIR / "skill-patterns.json", encoding="utf-8") as f:
        skill_patterns = json.load(f)
    return names, schools, skill_patterns


def load_sentences():
    """문장 은행 로드 (5 카테고리 × 2 배치)."""
    sentences_by_category = {}
    categories = ["motivation", "growth", "strength", "experience", "goal"]

    for category in categories:
        sentences_by_category[category] = []
        for batch in ["01", "02"]:
            filepath = SENTENCES_DIR / f"{category}-{batch}.json"
            if filepath.exists():
                with open(filepath, encoding="utf-8") as f:
                    sentences_by_category[category].extend(json.load(f))

    return sentences_by_category


# ── 한글 처리 ────────────────────────────────────────────────────────
# 문장 은행(파트 A)의 조사는 템플릿 작성 시점의 한 가지 경우로 고정돼 있다.
# 변수를 치환하면 앞말의 받침이 달라져 "학과을" 같은 비문이 생기므로 여기서 보정한다.
# 재료 파일은 파트 A 산출물이라 고치지 않는다.

_HANGUL_BASE = 0xAC00
_HANGUL_LAST = 0xD7A3
# 받침 없이 끝나도 'ㄹ' 받침처럼 취급되는 영문·숫자는 없다고 보고 모음 취급한다.
_NO_CODA_ALNUM = set("aeiouAEIOU0123456789")

# (받침 있을 때, 받침 없을 때)
_PARTICLES = [("은", "는"), ("이", "가"), ("을", "를"), ("과", "와"), ("으로", "로")]
_PARTICLE_RE = re.compile(
    r"(?<=\S)(" + "|".join(p for pair in _PARTICLES for p in pair) + r")(?=\s|$|[,.!?])"
)


def _has_coda(word: str) -> bool | None:
    """마지막 글자에 받침이 있으면 True, 없으면 False, 판정 불가면 None."""
    if not word:
        return None
    ch = word[-1]
    code = ord(ch)
    if _HANGUL_BASE <= code <= _HANGUL_LAST:
        return (code - _HANGUL_BASE) % 28 != 0
    if ch.isalnum():
        # 영문·숫자로 끝나면 표기상 발음의 끝소리로 판단한다.
        return ch not in _NO_CODA_ALNUM
    return None


def fix_particles(sentence: str) -> str:
    """치환 후 남은 조사를 앞말의 받침에 맞춰 교정한다."""

    def repl(m: re.Match) -> str:
        particle = m.group(1)
        coda = _has_coda(sentence[: m.start()].rstrip())
        if coda is None:
            return particle
        for with_coda, without_coda in _PARTICLES:
            if particle in (with_coda, without_coda):
                return with_coda if coda else without_coda
        return particle

    return _PARTICLE_RE.sub(repl, sentence)


# 이메일 로컬파트용 로마자 변환 — 한글 이메일은 현실성이 없고 H1 검색 테스트에도 부적합하다.
# 초성 19 / 중성 21 / 종성 28. 순서는 유니코드 한글 음절 조합 순서를 따른다.
_ROMAN_CHO = "g,kk,n,d,tt,r,m,b,pp,s,ss,,j,jj,ch,k,t,p,h".split(",")
_ROMAN_JUNG = "a,ae,ya,yae,eo,e,yeo,ye,o,wa,wae,oe,yo,u,wo,we,wi,yu,eu,ui,i".split(",")
# 받침 없음 + ㄱㄲㄳ ㄴㄵㄶ ㄷ ㄹㄺㄻㄼㄽㄾㄿㅀ ㅁㅂㅄ ㅅㅆ ㅇ ㅈㅊㅋㅌㅍㅎ = 28개.
_ROMAN_JONG = ",k,k,k,n,n,n,t,l,k,m,p,t,t,p,l,m,p,p,t,t,ng,t,t,k,t,p,t".split(",")

# 성씨는 표기법이 아니라 관용을 따른다. 표기법 자체가 "성의 표기는 따로 정한다"고
# 예외를 두고 있고, 실제로 아무도 김을 Gim, 이를 I 로 쓰지 않는다. 더미의 목적이
# 현실적인 검색 테스트 데이터이므로 굳어진 표기를 쓴다.
_SURNAME_ROMAN = {
    "김": "kim", "이": "lee", "박": "park", "최": "choi", "정": "jung",
    "강": "kang", "조": "cho", "윤": "yoon", "장": "jang", "임": "lim",
    "오": "oh", "한": "han", "신": "shin", "서": "seo", "권": "kwon",
    "황": "hwang", "안": "ahn", "송": "song", "전": "jeon", "홍": "hong",
    "유": "yoo", "고": "ko", "문": "moon", "양": "yang", "손": "son",
    "배": "bae", "백": "baek", "허": "heo", "남": "nam", "심": "shim",
    "노": "noh", "하": "ha", "곽": "kwak", "성": "sung", "차": "cha",
    "주": "joo", "우": "woo", "구": "koo", "나": "na", "민": "min",
    "진": "jin", "지": "ji", "엄": "eom", "채": "chae", "원": "won",
    "천": "chun", "방": "bang", "공": "kong", "현": "hyun", "함": "ham",
    "편": "pyun", "여": "yeo", "추": "chu", "도": "do", "소": "so",
    "설": "seol", "선": "sun", "마": "ma", "위": "wi", "표": "pyo",
    "명": "myung", "기": "ki", "반": "ban", "옹": "ong", "좌": "jwa",
}


def _romanize_syllable(ch: str) -> str:
    code = ord(ch)
    if not (_HANGUL_BASE <= code <= _HANGUL_LAST):
        return ch.lower() if ch.isalnum() else ""
    idx = code - _HANGUL_BASE
    return (
        _ROMAN_CHO[idx // 588]
        + _ROMAN_JUNG[(idx % 588) // 28]
        + _ROMAN_JONG[idx % 28]
    )


def romanize_name(last: str, first: str) -> str:
    """이메일 로컬파트용. 성은 관용 표기, 이름은 표기법 근사치."""
    surname = _SURNAME_ROMAN.get(last) or _romanize_syllable(last)
    return surname + "".join(_romanize_syllable(c) for c in first)


def substitute_variables(text: str, vars_dict: dict) -> str:
    """문장의 {{변수}}를 값으로 치환하고 조사를 보정한다."""
    result = text
    for var_name, value in vars_dict.items():
        result = result.replace(f"{{{{{var_name}}}}}", str(value))
    return fix_particles(result)


def generate_self_intro(sentences_by_category: dict, context: dict) -> str:
    """5 카테고리에서 1~2문장씩 뽑아 자기소개서 생성."""
    intro_parts = []
    categories = ["motivation", "growth", "strength", "experience", "goal"]

    # 변수 매핑 (문장 템플릿의 {{변수}}에 값 할당)
    var_map = {
        "학교": context["school"],
        "전공": context["major"],
        "기술": context["skills"][0] if context["skills"] else "Python",
        "경력": f"{context['career_years']}년",
        "직무": context["job_title"],
        "회사명": "Arda",
    }

    # 문장 은행의 한 항목은 "앞문장 + 뒷문장" 쌍이라, 같은 카테고리에서 둘을 뽑으면
    # 뒷문장이 겹칠 수 있다. 한 자소서 안에서 같은 문장이 두 번 나오지 않게 거른다.
    used = set()

    for category in categories:
        sentences = sentences_by_category.get(category)
        if not sentences:
            continue

        for sentence_obj in random.sample(sentences, random.randint(1, min(2, len(sentences)))):
            for part in re.split(r"(?<=다\.)\s+", sentence_obj["text"].strip()):
                part = part.strip()
                if part and part not in used:
                    used.add(part)
                    intro_parts.append(substitute_variables(part, var_map))

    return " ".join(intro_parts) if intro_parts else "열정적인 개발자입니다."


# skill-patterns.json 의 track → 공고 제목·자소서의 {{직무}}
TRACK_TO_JOB = {
    "backend": "백엔드 엔지니어",
    "frontend": "프론트엔드 엔지니어",
    "mobile-android": "안드로이드 개발자",
    "mobile-ios": "iOS 개발자",
    "devops": "DevOps 엔지니어",
    "data-engineer": "데이터 엔지니어",
    "data-scientist": "데이터 사이언티스트",
    "qa": "QA 엔지니어",
    "security": "보안 엔지니어",
    "pm": "프로덕트 매니저",
    "designer-ui": "UI 디자이너",
    "embedded": "임베디드 개발자",
    "game": "게임 클라이언트 개발자",
    "network": "네트워크 엔지니어",
}

# 단계 분포 — 완료 조건에 명시된 비율
STAGE_DISTRIBUTION = {
    "applied": 0.50,
    "screening": 0.25,
    "interview": 0.15,
    "accepted": 0.04,
    "rejected": 0.06,
}

# rejected 는 어느 단계에서든 진입 가능하다 (01-erd.md). 그 외 전진은 순서대로.
STAGE_ORDER = ["applied", "screening", "interview", "accepted"]


def generate_applications(
    count: int,
    names: dict,
    schools: list,
    pattern: dict,
    sentences_by_category: dict,
) -> list:
    """공고 하나에 붙을 지원서를 만든다. 지원자 직군은 그 공고의 직군을 따른다."""
    applications = []

    # 단계별 개수 계산 — 나머지는 applied 에 몰아준다
    stage_counts = {
        stage: int(count * pct) for stage, pct in STAGE_DISTRIBUTION.items()
    }
    stage_counts["applied"] += count - sum(stage_counts.values())

    track = pattern["track"]
    job_title = TRACK_TO_JOB[track]

    for stage, stage_count in stage_counts.items():
        for _ in range(stage_count):
            # 이름
            last_name = random.choice(names["last"])
            first_name = random.choice(names["first"])
            full_name = last_name + first_name

            # 이메일 — 한글 이름을 로마자로 (H1 이름·이메일 검색 테스트용)
            email = (
                f"{romanize_name(last_name, first_name)}"
                f"{random.randint(1000, 999999)}@example.com"
            )

            # 학력 — 학교와 전공을 함께 담는다 (education varchar(100))
            school_obj = random.choice(schools)
            school = school_obj["school"]
            major = random.choice(school_obj["majors"])

            # 기술 — 공고 직군의 패턴에서
            skills = random.sample(
                pattern["skills"], k=min(len(pattern["skills"]), random.randint(2, 4))
            )

            # 경력 연차
            career_years = random.randint(0, 10)

            # 자기소개서 생성
            context = {
                "school": school,
                "major": major,
                "skills": skills,
                "career_years": career_years,
                "job_title": job_title,
            }
            intro = generate_self_intro(sentences_by_category, context)

            # 접수 시각 — 최근 90일 안에서. 동의 시각도 같게 본다(폼 제출 시점).
            applied_at = datetime.now(UTC) - timedelta(
                days=random.randint(1, 90), minutes=random.randint(0, 1439)
            )

            app = Application(
                job_posting_id=0,  # 공고 배정 후 채운다
                name=full_name,
                email=email,
                phone=f"010-{random.randint(1000, 9999)}-{random.randint(1000, 9999)}",
                education=f"{school} {major}",
                career_years=career_years,
                skills=skills,
                self_intro=intro,
                current_stage=stage,
                privacy_agreed_at=applied_at,
                created_at=applied_at,
                updated_at=applied_at,
                source="form",
            )
            applications.append(app)

    return applications


def build_stage_history(app: Application) -> list[StageHistory]:
    """현재 단계까지 거쳐온 이력을 만든다.

    D5 이력 조회가 이 더미로 검증되므로 접수 한 건만 남기면 실제와 어긋난다.
    rejected 는 어느 단계에서든 빠질 수 있어 중간 지점에서 이탈시킨다.
    """
    if app.current_stage == "rejected":
        # applied ~ interview 중 한 지점까지 진행하다 탈락
        cut = random.randint(1, len(STAGE_ORDER) - 1)
        path = STAGE_ORDER[:cut] + ["rejected"]
    else:
        path = STAGE_ORDER[: STAGE_ORDER.index(app.current_stage) + 1]

    rows = []
    at = app.created_at
    for i, to_stage in enumerate(path):
        rows.append(
            StageHistory(
                application_id=app.id,
                from_stage=path[i - 1] if i else None,
                # 최초 접수는 시스템(외부 지원)이라 changed_by 가 NULL 이다
                changed_by=None,
                to_stage=to_stage,
                created_at=at,
            )
        )
        at = at + timedelta(days=random.randint(1, 7))
    return rows


def create_seed_data(count: int, append: bool = False):
    """더미 데이터 생성 및 DB 삽입."""
    print(f"📥 재료 로드 중...")
    names, schools, skill_patterns = load_materials()
    sentences_by_category = load_sentences()

    print(f"🔌 DB 연결 중...")
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()

    try:
        if not append:
            print("🗑️  기존 더미 삭제 중...")
            # FK 순서대로. TRUNCATE 는 시퀀스까지 되돌린다.
            db.execute(
                text(
                    "TRUNCATE stage_history, applications, job_postings "
                    "RESTART IDENTITY CASCADE"
                )
            )
            db.commit()

        start_time = time.time()

        # 공고 — 직군 패턴에서 10개를 뽑는다. 지원자 기술이 공고 직군을 따르게 하려면
        # 공고도 같은 재료에서 나와야 한다.
        postings = db.query(JobPosting).order_by(JobPosting.id).all()
        if postings:
            print(f"📌 기존 공고 {len(postings)}개 재사용")
            patterns_by_title = {TRACK_TO_JOB[p["track"]]: p for p in skill_patterns}
            posting_patterns = [patterns_by_title[p.title] for p in postings]
        else:
            chosen = random.sample(skill_patterns, k=min(10, len(skill_patterns)))
            print(f"📌 공고 {len(chosen)}개 생성 중...")
            postings, posting_patterns = [], []
            for pattern in chosen:
                title = TRACK_TO_JOB[pattern["track"]]
                postings.append(
                    JobPosting(
                        title=title,
                        description=(
                            f"{title} 채용. 주요 기술: "
                            + ", ".join(pattern["skills"])
                            + "."
                        ),
                        status="open",
                        created_by=None,
                    )
                )
                posting_patterns.append(pattern)
            db.add_all(postings)
            db.flush()  # id 부여

        # 지원서 — 공고 단위로 생성·삽입한다. 10만 건을 한꺼번에 메모리에 들지 않고,
        # UNIQUE(job_posting_id, email) 도 공고 안에서만 보면 되므로 중복 처리가 단순해진다.
        print(f"📝 지원서 {count:,}건 생성 중...")
        per_posting = count // len(postings)
        remainder = count % len(postings)
        inserted = 0

        for idx, (posting, pattern) in enumerate(zip(postings, posting_patterns)):
            n = per_posting + (1 if idx < remainder else 0)
            if n == 0:
                continue

            apps = generate_applications(
                n, names, schools, pattern, sentences_by_category
            )

            # 같은 공고 안에서 이메일이 겹치면 겹친 쪽만 새 주소를 받는다.
            # (예전 구현은 충돌 시 원본을 덮어써서 행이 조용히 사라졌다)
            seen = set(
                e
                for (e,) in db.query(Application.email)
                .filter(Application.job_posting_id == posting.id)
                .all()
            )
            for app in apps:
                app.job_posting_id = posting.id
                while app.email in seen:
                    local, domain = app.email.split("@")
                    app.email = f"{local}x{random.randint(0, 9999)}@{domain}"
                seen.add(app.email)

            db.add_all(apps)
            db.flush()  # 이력에 쓸 id 확보

            histories = []
            for app in apps:
                histories.extend(build_stage_history(app))
            db.add_all(histories)

            db.commit()
            inserted += len(apps)
            print(
                f"  [{idx + 1}/{len(postings)}] {posting.title} "
                f"— {len(apps):,}건 (누적 {inserted:,}, {time.time() - start_time:.1f}초)"
            )

        elapsed = time.time() - start_time

        # 검증 — 스크립트가 만든 값이 아니라 DB 에 물어본다
        print("\n✅ 검증:")
        total = db.scalar(select(func.count()).select_from(Application))
        distinct_intro = db.scalar(
            select(func.count(func.distinct(Application.self_intro)))
        )
        history_rows = db.scalar(select(func.count()).select_from(StageHistory))

        print(f"  공고: {db.scalar(select(func.count()).select_from(JobPosting)):,}개")
        print(f"  이번에 넣은 지원서: {inserted:,}건 (요청 {count:,}건)")
        print(f"  전체 지원서: {total:,}건")
        for stage in STAGES:
            n = db.scalar(
                select(func.count())
                .select_from(Application)
                .where(Application.current_stage == stage)
            )
            print(f"    - {stage}: {n:,} ({n / total * 100:.1f}%)")
        print(f"  서로 다른 자기소개서: {distinct_intro:,} / {total:,}")
        print(f"  단계 이력: {history_rows:,}행")

        print(f"\n⏱️  {elapsed:.1f}초 ({inserted / elapsed:,.0f}건/초)")

    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(
        description="Arda 더미 데이터 생성기 (공고 10개 + 지원서 N건)"
    )
    parser.add_argument(
        "--count", type=int, default=100000, help="지원서 개수 (기본 100000)"
    )
    parser.add_argument(
        "--append",
        action="store_true",
        help="기존 데이터 유지하고 추가 생성 (기본은 삭제 후 재생성)",
    )

    args = parser.parse_args()

    create_seed_data(count=args.count, append=args.append)


if __name__ == "__main__":
    main()
