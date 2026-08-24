# [F1·F2] S3 presigned 업로드 · 다운로드

> 담당: 팀원1 · 역할 C(파일·알림) · 브랜치: `feat/f1-s3-presigned`
> **PR 단위**: 이 지시서 전체 = PR 1개

## 배경

이력서 파일이 API 서버를 거치면 서버 메모리와 대역폭을 먹고, 10MB 파일이 동시에 여러 개 올라오면 그대로 죽는다. **브라우저가 S3 로 직접 올린다.** 서버는 "이 경로에 올려도 된다"는 서명된 URL 만 발급한다.

**이 프로젝트에서 AWS 를 실제로 쓰는 자리다.** 발표에서 "파일 업로드가 왜 API 서버를 거치면 안 되는가"를 말할 근거가 여기서 나온다 ([04-team.md](../00_overview/04-team.md) C 역할).

## 선행 조건 — 없으면 중단

아래가 하나라도 아니면 **시작하지 말고 팀 채널에 알린다.** 없는 것을 상상해서 만들지 않는다.

- [ ] [J0 앱 뼈대](J0-앱-뼈대.md) PR이 머지돼 있다
- [ ] [docs/00_overview/01-erd.md](../00_overview/01-erd.md)가 확정 상태다
- [ ] **AWS 계정 · S3 버킷이 있고 접근 권한을 받았다** — 없으면 팀장에게 요청한다
- [ ] `backend/.env` 에 AWS 설정이 들어 있다 (`.env` 는 git 에 올리지 않는다)

## 가장 중요한 규칙

- **[backend/app/models.py](../../backend/app/models.py)를 수정하지 않는다.** 컬럼이 부족해 보여도 추가하지 않는다. 멈추고 팀 채널에 묻는다.
- **[docs/00_overview/01-erd.md](../00_overview/01-erd.md)·[docs/00_overview/02-api.md](../00_overview/02-api.md)를 수정하지 않는다.** 공용 문서다.
- **인증·권한 코드를 넣지 않는다.** 인증은 팀장 담당(A1~A3)이고 아직 없다. 토큰 검사를 흉내 내면 나중에 팀장 것과 충돌한다. 사용자 id 가 필요한 자리는 `# TODO(A1): 토큰의 사용자로 채운다` 주석만 남긴다.
- **`main.py` 는 `include_router` 한 줄만** 건드린다. 그 파일의 다른 부분은 손대지 않는다.
- **AWS 키를 코드·커밋·로그에 절대 남기지 않는다.** `os.getenv` 로만 읽고, `.env.example` 에는 키 **이름만** 적는다.
- **파일 본문이 서버를 통과하면 안 된다.** `UploadFile` 을 받는 엔드포인트를 만들면 이 작업의 의미가 사라진다.
- **`s3_key` 컬럼명은 아직 미결이다** ([01-erd.md](../00_overview/01-erd.md) 미결 항목). 지금은 그대로 쓰고, 바뀌면 팀장이 일괄 변경한다.

## 완료 조건

- [ ] `uv add boto3`
- [ ] `backend/app/s3.py` — boto3 클라이언트. 버킷·리전은 전부 환경변수
- [ ] `backend/app/api/files.py` — 라우터
- [ ] `POST /api/v1/public/files/presign-upload` — **공개**. 요청 `{filename, content_type, kind}` → 응답 `{upload_url, s3_key, expires_in}`
- [ ] `GET /api/v1/files/{id}/download-url` — presigned 다운로드 URL. 없는 id 는 404
- [ ] **`s3_key` 는 서버가 만든다.** 형식 `applications/{uuid4}/{kind}.{ext}` — 클라이언트가 보낸 경로를 쓰지 않는다
- [ ] `kind` 는 `resume` / `cover_letter` 만 허용 (`models.FILE_KINDS`)
- [ ] 만료는 **300초**
- [ ] `backend/.env.example` 에 `AWS_REGION` · `S3_BUCKET` **이름만** 추가
- [ ] `main.py` 에 `include_router` 한 줄

## 완성 예시

**이 형태를 그대로 따른다.**

```python
# backend/app/s3.py
import os

import boto3

BUCKET = os.getenv("S3_BUCKET", "")
REGION = os.getenv("AWS_REGION", "ap-northeast-2")

# 자격증명은 표준 AWS 체인(환경변수·프로필·IAM 역할)으로만 읽는다. 코드에 키를 쓰지 않는다
_client = boto3.client("s3", region_name=REGION)


def presign_put(key: str, content_type: str, expires: int = 300) -> str:
    return _client.generate_presigned_url(
        "put_object",
        Params={"Bucket": BUCKET, "Key": key, "ContentType": content_type},
        ExpiresIn=expires,
    )


def presign_get(key: str, expires: int = 300) -> str:
    return _client.generate_presigned_url(
        "get_object", Params={"Bucket": BUCKET, "Key": key}, ExpiresIn=expires
    )
```

```python
# backend/app/api/files.py (핵심만)
import uuid
from pathlib import Path

@router.post("/public/files/presign-upload")
def presign_upload(body: PresignRequest):
    ext = Path(body.filename).suffix.lower().lstrip(".")
    # 경로는 서버가 만든다. 클라이언트가 보낸 경로를 그대로 쓰면 남의 파일을 덮어쓸 수 있다
    key = f"applications/{uuid.uuid4()}/{body.kind}.{ext}"
    return {
        "upload_url": presign_put(key, body.content_type),
        "s3_key": key,
        "expires_in": 300,
    }
```

## 참고 문서

- [docs/00_overview/01-erd.md](../00_overview/01-erd.md) — `files` 표와 `s3_key` 미결 항목
- [docs/00_overview/02-api.md](../00_overview/02-api.md) — "지원 — 공개 (C)" 의 presign 행
- [infra/README.md](../../infra/README.md) — S3 사용 방침

## Claude에게 시키기

작업 폴더에서 Claude Code를 열고 **아래를 순서대로 하나씩** 붙여넣는다.

```
0단계.
backend/app/models.py 의 File 클래스와 FILE_KINDS, docs/00_overview/01-erd.md 의 files 표,
docs/00_overview/02-api.md 의 presign 관련 행, backend/.env.example 을 읽어라.

읽은 뒤 아래를 알려줘라. 아직 파일을 만들지 마라.
- presigned URL 방식에서 파일 본문이 어디를 지나가는지
- s3_key 를 클라이언트가 아니라 서버가 만들어야 하는 이유
```

```
1단계.
backend 에서 uv add boto3 를 실행해라.
backend/app/s3.py 를 만들어라. presign_put 과 presign_get 두 함수만 둔다.
버킷·리전은 os.getenv 로 읽는다. 키·버킷명을 코드에 하드코딩하지 마라.
```

```
2단계.
backend/app/api/files.py 에 라우터를 만들어라.
POST /api/v1/public/files/presign-upload — 요청은 filename, content_type, kind.
s3_key 는 서버가 applications/{uuid4}/{kind}.{확장자} 로 만든다.
클라이언트가 보낸 경로를 절대 쓰지 마라. kind 는 resume/cover_letter 만 허용한다.
GET /api/v1/files/{id}/download-url — files 행을 찾아 presign_get 으로 URL 을 준다. 없으면 404.
UploadFile 을 받는 엔드포인트를 만들지 마라 — 파일이 서버를 지나가면 안 된다.
```

```
3단계.
backend/.env.example 에 AWS_REGION 과 S3_BUCKET 을 키 이름만 추가해라. 값을 쓰지 마라.
main.py 에 include_router 한 줄을 추가하고, 아래 검증을 실행해 결과를 보여줘라.
```

```
마지막 단계 — 여기서 멈추지 마라.

위 작업을 끝내고 PR 을 올렸으면, 이어서 다음 할 일을 스스로 찾아 그대로 수행해라.

1. docs/00_overview/04-team.md 에서 내 도메인을 확인하고, docs/01_role/<내 도메인>.md 의 작업 큐를 읽어라.
   (작업 큐는 로드맵에만 있다. docs/00_overview/06-weekly.md 는 주 마감 게이트·도메인 간 일정용이다)
2. 큐에서 선행이 풀린 다음 작업을 찾아라. 큐가 비었거나 전부 막혀 있으면
   멈추고 무엇이 막혔는지 팀 채널에 알려라.
3. 찾은 작업의 지시서가 docs/02_tasks/ 에 링크돼 있으면 열고, 선행 조건을 먼저 확인해라.
   선행 조건이 안 채워졌으면 거기서 멈추고 무엇이 막혔는지 알려줘라.
4. 선행 조건이 채워졌으면 새 브랜치를 만들고 그 지시서의 "Claude에게 시키기" 를
   0단계부터 순서대로 수행해라. 지시서 하나 = PR 하나다.
5. 그 작업도 끝나면 1번으로 돌아가 반복해라.

지키는 것:
- 지시서가 있는 작업만 한다. 큐 항목에 지시서가 없으면 "지시서 없음 — 오너가 직접 쪼갤 것"
  이라고 말하고 멈춘다.
- 지시서에 적힌 산출 파일 밖을 고치지 않는다. 다른 도메인 파일과 공용 파일은 건드리지 않는다.
  (공용: frontend/mockups/mockup.html · docs/00_overview/01-erd.md · docs/00_overview/02-api.md · backend/app/models.py)
- 작업 사이마다 git status 를 확인해서 지시서에 없는 파일이 있으면 되돌린다.
```

## 검증 방법

```bash
cd backend && uv run uvicorn app.main:app --reload
URL=$(curl -s -X POST localhost:8000/api/v1/public/files/presign-upload -H 'content-type: application/json' -d '{"filename":"resume.pdf","content_type":"application/pdf","kind":"resume"}' | python -c 'import sys,json;print(json.load(sys.stdin)["upload_url"])')
echo hello > /tmp/t.pdf
curl -s -o /dev/null -w '업로드 %{http_code}\n' -X PUT -H 'content-type: application/pdf' --upload-file /tmp/t.pdf "$URL"
curl -s -o /dev/null -w 'kind 오류 %{http_code}\n' -X POST localhost:8000/api/v1/public/files/presign-upload -H 'content-type: application/json' -d '{"filename":"a.pdf","content_type":"application/pdf","kind":"이상한값"}'
git grep -nE 'AKIA|aws_secret|SecretAccessKey' -- backend/ || echo '시크릿 미노출 OK'
```

기대 결과:

- presign 응답에 `upload_url` · `s3_key` · `expires_in: 300`
- `s3_key` 가 `applications/<uuid>/resume.pdf` 형식이다
- 그 URL 로 PUT → **200** (S3 에 실제로 올라간다)
- `kind` 에 이상한 값 → **422**
- `git grep` 에 AWS 키 문자열이 **하나도 안 나온다**
- 서버 로그에 키가 찍히지 않는다

## 막히면 · 되돌리기

- **30분 넘게 막히면 혼자 붙들지 말고 팀 채널에 묻는다.**
- **결과가 이상해지면 고치려 들지 말고 버린다.**

```bash
git checkout -- .
```

그래도 이상하면 브랜치째 버리고 처음부터 다시 시작한다.

```bash
git checkout main && git branch -D feat/f1-s3-presigned
```

- **`git status`에 `models.py` · `docs/` · 다른 사람 파일이 떠 있으면 범위를 벗어난 것이다.** 되돌리고 팀 채널에 알린다.

## PR 체크리스트

- [ ] PR 본문에 위 검증 결과를 붙였다
- [ ] `models.py` · `docs/` · 다른 사람 파일을 **수정하지 않았다**
- [ ] 스키마 변경 없음
