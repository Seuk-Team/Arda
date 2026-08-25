"""S3 presigned URL 발급 (F1·F2).

**파일 본문은 이 서버를 지나가지 않는다.** 브라우저가 S3 로 직접 올리고 내린다.
서버가 하는 일은 "이 키에 올려도 된다 / 내려도 된다"는 서명을 만드는 것뿐이다.
`UploadFile` 을 받는 엔드포인트를 만들면 이 설계가 무의미해진다.

자격증명은 표준 AWS 체인(환경변수·프로필·IAM 역할)으로만 읽는다. 코드에 키를 쓰지 않는다.
"""

import os
from functools import lru_cache

import boto3

BUCKET = os.getenv("S3_BUCKET", "")
REGION = os.getenv("AWS_REGION", "ap-northeast-2")

# presigned URL 의 수명. 짧을수록 새어 나갔을 때 위험이 줄고, 길수록 느린 회선에서
# 업로드가 끊긴다. 이력서 몇 MB 기준으로 5분이면 충분하다.
EXPIRES_IN = 300


@lru_cache(maxsize=1)
def _client():
    """클라이언트를 임포트 시점이 아니라 첫 사용 시점에 만든다.

    모듈 최상단에서 만들면 AWS 설정이 없는 환경(테스트·CI)에서 임포트만 해도
    터진다. 서명 발급은 네트워크를 타지 않으므로 재사용해도 안전하다.
    """
    return boto3.client("s3", region_name=REGION)


def presign_put(
    key: str, content_type: str, size_bytes: int, expires: int = EXPIRES_IN
) -> str:
    """업로드용 서명.

    content_type 과 size_bytes 를 서명에 넣는다. 서명에 들어간 값과 다르게 올리면
    S3 가 거부한다 — 서버가 받은 `size_bytes` 는 클라이언트가 보낸 숫자일 뿐이라
    그것만 믿으면 100MB 를 10MB 라고 신고하고 올릴 수 있다. S3 단에서 한 번 더 막는다.
    """
    return _client().generate_presigned_url(
        "put_object",
        Params={
            "Bucket": BUCKET,
            "Key": key,
            "ContentType": content_type,
            "ContentLength": size_bytes,
        },
        ExpiresIn=expires,
    )


def presign_get(key: str, expires: int = EXPIRES_IN) -> str:
    """다운로드용 서명."""
    return _client().generate_presigned_url(
        "get_object",
        Params={"Bucket": BUCKET, "Key": key},
        ExpiresIn=expires,
    )
