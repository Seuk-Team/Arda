# backend — FastAPI 서버

> 모델(테이블 정의)까지 있음. 라우터·서비스는 아직 없다.

```bash
uv sync
```

- `app/models.py` — [../docs/00_overview/01-erd.md](../docs/00_overview/01-erd.md)를 그대로 옮긴 테이블 9개. **문서가 기준이고, 어긋나면 문서를 고친 뒤 여기를 맞춘다.**
- `app/db.py` — 엔진·세션·`Base`. 스키마가 굳기 전까지는 마이그레이션을 쌓지 않고 `create_all`로 만들고 지운다.
- DB 접속 정보는 `.env`(git 제외)에 넣는다. 키 이름은 `.env.example` 참고.

- Python 3.12 · uv · FastAPI · SQLAlchemy · PostgreSQL
- API 목록: [../docs/00_overview/02-api.md](../docs/00_overview/02-api.md) / 문서는 Swagger(`/docs`) 자동 생성
- 예정 구조: `app/`(도메인별 라우터·서비스·모델) · `scripts/`(더미 생성기 등) · `tests/`
- 담당 경계는 [../docs/00_overview/04-team.md](../docs/00_overview/04-team.md) 참고
