# 이력서 텍스트 추출 PoC — 결과표

> 자동 생성: `uv run python -m app.agent.extract.run_poc`
> 샘플: `backend/app/agent/extract/samples` · 총 20건 · 성공 13건
> PDF 엔진: **pypdf** · 한글 본문 검증: **예**

## 형식별 요약

| 형식 | 건수 | 성공 | 판정 |
|---|---|---|---|
| docx | 5 | 5 | 전부 성공 기대 |
| hwp | 5 | 0 | 실패 예상 — 수동 폴백 |
| pdf | 10 | 8 | 텍스트 PDF는 전부 성공해야 한다 (스캔본 제외) |

## 파일별

| 파일 | 형식 | 엔진 | 결과 | 글자수 | 미리보기 / 사유 |
|---|---|---|---|---|---|
| `cover_01.docx` | docx | stdlib-zip | ✅ | 68 | 자기소개서 - 김도현. 백엔드 개발을 지원합니다. 주요 기술: Python FastAPI PostgreSQL. 경력 2년. |
| `cover_02.docx` | docx | stdlib-zip | ✅ | 64 | 자기소개서 - 이서연. 백엔드 개발을 지원합니다. 주요 기술: React TypeScript Vite. 경력 3년. |
| `cover_03.docx` | docx | stdlib-zip | ✅ | 59 | 자기소개서 - 박준호. 백엔드 개발을 지원합니다. 주요 기술: AWS Docker CI/CD. 경력 4년. |
| `cover_04.docx` | docx | stdlib-zip | ✅ | 68 | 자기소개서 - 최민지. 백엔드 개발을 지원합니다. 주요 기술: Python FastAPI PostgreSQL. 경력 5년. |
| `cover_05.docx` | docx | stdlib-zip | ✅ | 64 | 자기소개서 - 정우성. 백엔드 개발을 지원합니다. 주요 기술: React TypeScript Vite. 경력 6년. |
| `resume_01.hwp` | hwp | - | ❌ | 0 | HWP 자동 추출 미지원 → 담당자가 상세 폼에 수동 입력(폴백) |
| `resume_01.pdf` | pdf | pypdf | ✅ | 102 | 이력서 — 김도현 지원 직무: 백엔드 개발자 경력: 2년 기술: Python FastAPI PostgreSQL 자기소개서 대규모 트래픽을 다루는 서비스에서 API 성능을 개선했습니다. |
| `resume_02.hwp` | hwp | - | ❌ | 0 | HWP 자동 추출 미지원 → 담당자가 상세 폼에 수동 입력(폴백) |
| `resume_02.pdf` | pdf | pypdf | ✅ | 98 | 이력서 — 이서연 지원 직무: 백엔드 개발자 경력: 3년 기술: React TypeScript Vite 자기소개서 대규모 트래픽을 다루는 서비스에서 API 성능을 개선했습니다. |
| `resume_03.hwp` | hwp | - | ❌ | 0 | HWP 자동 추출 미지원 → 담당자가 상세 폼에 수동 입력(폴백) |
| `resume_03.pdf` | pdf | pypdf | ✅ | 93 | 이력서 — 박준호 지원 직무: 백엔드 개발자 경력: 4년 기술: AWS Docker CI/CD 자기소개서 대규모 트래픽을 다루는 서비스에서 API 성능을 개선했습니다. |
| `resume_04.hwp` | hwp | - | ❌ | 0 | HWP 자동 추출 미지원 → 담당자가 상세 폼에 수동 입력(폴백) |
| `resume_04.pdf` | pdf | pypdf | ✅ | 102 | 이력서 — 최민지 지원 직무: 백엔드 개발자 경력: 5년 기술: Python FastAPI PostgreSQL 자기소개서 대규모 트래픽을 다루는 서비스에서 API 성능을 개선했습니다. |
| `resume_05.hwp` | hwp | - | ❌ | 0 | HWP 자동 추출 미지원 → 담당자가 상세 폼에 수동 입력(폴백) |
| `resume_05.pdf` | pdf | pypdf | ✅ | 98 | 이력서 — 정우성 지원 직무: 백엔드 개발자 경력: 6년 기술: React TypeScript Vite 자기소개서 대규모 트래픽을 다루는 서비스에서 API 성능을 개선했습니다. |
| `resume_06.pdf` | pdf | pypdf | ✅ | 93 | 이력서 — 김도현 지원 직무: 백엔드 개발자 경력: 2년 기술: AWS Docker CI/CD 자기소개서 대규모 트래픽을 다루는 서비스에서 API 성능을 개선했습니다. |
| `resume_07.pdf` | pdf | pypdf | ✅ | 102 | 이력서 — 이서연 지원 직무: 백엔드 개발자 경력: 3년 기술: Python FastAPI PostgreSQL 자기소개서 대규모 트래픽을 다루는 서비스에서 API 성능을 개선했습니다. |
| `resume_08.pdf` | pdf | pypdf | ✅ | 98 | 이력서 — 박준호 지원 직무: 백엔드 개발자 경력: 4년 기술: React TypeScript Vite 자기소개서 대규모 트래픽을 다루는 서비스에서 API 성능을 개선했습니다. |
| `resume_09_scan.pdf` | pdf | pypdf | ❌ | 0 | 텍스트 없음(스캔본·빈 페이지 가능) |
| `resume_10_scan.pdf` | pdf | pypdf | ❌ | 0 | 텍스트 없음(스캔본·빈 페이지 가능) |

## 폴백 규칙

- **HWP**: 자동 추출 미지원 → 담당자가 상세 폼에 수동 입력. 접수는 막지 않는다.
- **스캔본 PDF**: 텍스트 0글자 → 실패로 표시하고 같은 수동 폴백.
- 추출 실패는 `ai_summary`를 NULL로 두고, 화면에는 '요약 없음'으로만 보인다.

## 의존성 — 백엔드 오너 협의 필요

- **`pypdf` (런타임)**: 한글 PDF 추출에 필요하다. 없으면 stdlib 폴백으로 내려가고 폰트를 심은 PDF에서 텍스트를 얻지 못한다 — 즉 실이력서에서 실패한다.
- **`fpdf2` (개발 전용)**: 한글 샘플 생성에만 쓴다. 런타임에는 필요 없다.
- `backend/pyproject.toml`은 백엔드 도메인 파일이라 이 PoC에서 고치지 않았다. 추가는 백엔드 오너와 인터페이스 PR로 합의한다.

## 비용

이 PoC는 **LLM을 호출하지 않는다.** 요약 생성(W3)에서만 호출하고, 더미 10만 건에는 절대 돌리지 않는다.
