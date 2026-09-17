# backend — FastAPI 서버

> 2026-09-17 갱신: 이 머리말은 08 월 뼈대 시점에 쓰였다. 지금은 라우터·서비스가 컨텍스트별 폴더(`application`·`hiring`·`interview`·`talent`·`shared`, ADR-0035)에 있다.

```bash
uv sync
```

- `app/models/` — [../docs/00_overview/01-erd.md](../docs/00_overview/01-erd.md)의 표를 옮긴 모델(표 28개, 컨텍스트별 파일). **문서가 기준이고, 어긋나면 문서를 고친 뒤 여기를 맞춘다.**
- `app/db.py` — 엔진·세션·`Base`. 스키마 변경은 alembic 리비전으로 쌓는다 ([alembic/README.md](alembic/README.md)).
- DB 접속 정보는 `.env`(git 제외)에 넣는다. 키 이름은 `.env.example` 참고.

- Python 3.12 · uv · FastAPI · SQLAlchemy · PostgreSQL
- API 목록: [../docs/00_overview/02-api.md](../docs/00_overview/02-api.md) / 문서는 Swagger(`/docs`) 자동 생성
- 예정 구조: `app/`(도메인별 라우터·서비스·모델) · `scripts/`(더미 생성기 등) · `tests/`
- 담당 경계는 [../docs/00_overview/04-team.md](../docs/00_overview/04-team.md) 참고
