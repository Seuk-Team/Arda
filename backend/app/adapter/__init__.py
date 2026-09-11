"""Adapters — 밖과 안을 잇는 구현.

- `outbound/` : 도메인이 밖에 요구한 계약을 실제 붙이는 곳 (Repository·LLM·Mail·S3).
- `inbound/`  : 미리 만들지 않는다 (ADR-0035 §2). 기존 `api/` 유지. WS/worker 는
                실제 흡수 시점에 그때 만든다.

파일 명명: `<name>_<backend>_<kind>.py`.
예) `application_pg_repository.py`, `mail_ses_adapter.py`.
"""
