"""엔티티 해석 레이어 테스트."""

import pytest

from app.agent.entity_resolver import (
    edit_distance,
    extract_chosung,
    find_similar_names,
    normalize_numbers,
    normalize_tech_terms,
    resolve_entities,
)


# ── 한글 수사 → 숫자 ──────────────────────────────────────

class TestNormalizeNumbers:
    def test_sino_simple(self):
        assert normalize_numbers("경력 이년 이상") == "경력 2년 이상"

    def test_sino_compound(self):
        assert normalize_numbers("삼백이십오 명") == "325 명"

    def test_sino_with_scale(self):
        assert normalize_numbers("천이백 건") == "1200 건"

    def test_native_simple(self):
        assert normalize_numbers("한 명") == "1 명"

    def test_native_compound(self):
        assert normalize_numbers("스물세 살") == "23 살"

    def test_mixed_text(self):
        result = normalize_numbers("파이썬 삼년, 자바 이년 이상")
        assert "3년" in result
        assert "2년" in result

    def test_no_numbers(self):
        assert normalize_numbers("김도현 면접으로 옮겨줘") == "김도현 면접으로 옮겨줘"

    def test_arabic_untouched(self):
        assert normalize_numbers("경력 3년 이상") == "경력 3년 이상"

    def test_false_positive_이번(self):
        assert normalize_numbers("이번 면접에서 확인해주세요") == "이번 면접에서 확인해주세요"

    def test_false_positive_사건(self):
        assert normalize_numbers("해당 사건은 종료됐습니다") == "해당 사건은 종료됐습니다"

    def test_false_positive_이점(self):
        assert normalize_numbers("이 시스템의 이점을 설명해주세요") == "이 시스템의 이점을 설명해주세요"

    def test_false_positive_사회(self):
        assert normalize_numbers("사회 경험이 풍부합니다") == "사회 경험이 풍부합니다"

    def test_false_positive_사원(self):
        assert normalize_numbers("신입 사원 채용") == "신입 사원 채용"

    def test_false_positive_이대(self):
        assert normalize_numbers("이대 졸업") == "이대 졸업"

    def test_false_positive_사장(self):
        assert normalize_numbers("사장님과 면담") == "사장님과 면담"

    def test_false_positive_multi_unit_이사(self):
        assert normalize_numbers("이사회에서 결정") == "이사회에서 결정"

    def test_real_number_still_converts(self):
        assert normalize_numbers("경력 이년 이상") == "경력 2년 이상"

    def test_real_number_with_false_positive_mixed(self):
        result = normalize_numbers("이번 면접에서 삼년 경력자 찾아줘")
        assert "이번" in result
        assert "3년" in result


# ── 기술 용어 음차 정규화 ────────────────────────────────

class TestNormalizeTechTerms:
    def test_fastapi(self):
        assert normalize_tech_terms("패스트에이피아이 경험자") == "FastAPI 경험자"

    def test_fastapi_with_space(self):
        assert normalize_tech_terms("패스트 에이피아이") == "FastAPI"

    def test_react(self):
        assert normalize_tech_terms("리액트 개발자") == "React 개발자"

    def test_react_typo(self):
        assert normalize_tech_terms("리엑트 경험") == "React 경험"

    def test_python(self):
        assert normalize_tech_terms("파이썬 경력") == "Python 경력"

    def test_typescript(self):
        assert normalize_tech_terms("타입스크립트") == "TypeScript"

    def test_multiple_terms(self):
        result = normalize_tech_terms("파이썬이랑 리액트 경험자")
        assert "Python" in result
        assert "React" in result

    def test_docker(self):
        assert normalize_tech_terms("도커 경험") == "Docker 경험"

    def test_kubernetes(self):
        assert normalize_tech_terms("쿠버네티스") == "Kubernetes"

    def test_spring_boot(self):
        assert normalize_tech_terms("스프링부트") == "Spring Boot"

    def test_no_tech(self):
        assert normalize_tech_terms("김도현 면접") == "김도현 면접"


# ── 초성 추출 ────────────────────────────────────────────

class TestExtractChosung:
    def test_korean_name(self):
        assert extract_chosung("김도현") == "ㄱㄷㅎ"

    def test_mixed(self):
        assert extract_chosung("김AB") == "ㄱAB"

    def test_empty(self):
        assert extract_chosung("") == ""


# ── 편집 거리 ────────────────────────────────────────────

class TestEditDistance:
    def test_same(self):
        assert edit_distance("abc", "abc") == 0

    def test_one_insert(self):
        assert edit_distance("abc", "abcd") == 1

    def test_one_replace(self):
        assert edit_distance("abc", "axc") == 1

    def test_empty(self):
        assert edit_distance("", "abc") == 3


# ── 이름 유사도 매칭 ─────────────────────────────────────

class TestFindSimilarNames:
    def test_exact_match(self):
        results = find_similar_names("김도현", ["김도현", "박지민"])
        assert results[0] == ("김도현", 1.0)

    def test_chosung_match(self):
        results = find_similar_names("김도현", ["김동현", "박지민"])
        assert any(name == "김동현" for name, _ in results)

    def test_stt_space_error(self):
        """STT가 띄어쓰기를 잘못한 경우"""
        results = find_similar_names("김도 현", ["김도현", "박지민"])
        assert results[0][0] == "김도현"
        assert results[0][1] == 1.0

    def test_no_match(self):
        results = find_similar_names("최영수", ["김도현", "박지민"])
        assert len(results) == 0

    def test_similar_name(self):
        results = find_similar_names("김도헌", ["김도현", "박지민"])
        assert len(results) > 0
        assert results[0][0] == "김도현"

    def test_multiple_candidates(self):
        candidates = ["김도현", "김동현", "김도형", "박지민"]
        results = find_similar_names("김도현", candidates)
        assert results[0] == ("김도현", 1.0)
        assert len(results) >= 2


# ── 통합 전처리 ──────────────────────────────────────────

class TestResolveEntities:
    def test_full_pipeline(self):
        result = resolve_entities("김도현씨 파이썬 이년 이상 경력자")
        assert "김도현" in result
        assert "Python" in result
        assert "2년" in result
        assert "씨" not in result

    def test_honorific_removal(self):
        result = resolve_entities("김도현님 면접으로 옮겨줘")
        assert "님" not in result
        assert "김도현" in result

    def test_complex_command(self):
        result = resolve_entities("패스트에이피아이 삼년 이상 경력자 찾아줘")
        assert "FastAPI" in result
        assert "3년" in result
