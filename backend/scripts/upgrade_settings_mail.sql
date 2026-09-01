-- 설정 실동작 + 메일 발송(G4·A4) 스키마 이행 — 2026-09-01, 1회성.
--
-- 이 저장소에는 alembic 이 없다 (app/db.py 주석 — create_all 로 만든다).
-- create_all 은 **없는 테이블만** 만든다. 이미 있는 테이블에 컬럼을 붙이지도,
-- 체크 제약을 갈아끼우지도 못한다. 그래서 users·email_logs 는 이 파일이 필요하다.
-- email_templates(신규 테이블)는 create_all 이 만들므로 여기 없다.
--
-- 실행:
--     psql "$DATABASE_URL" -f backend/scripts/upgrade_settings_mail.sql
--   서버:
--     docker compose -f docker-compose.prod.yml exec -T db \
--       psql -U postgres -d arda -v ON_ERROR_STOP=1 -f - < backend/scripts/upgrade_settings_mail.sql
--
-- ⚠ 순서가 역할 이행(migrate_roles_to_member.sql)과 **반대다: 이 SQL 이 먼저,
--   재배포가 나중.** 새 코드의 ORM 이 users.is_active 를 SELECT 에 실으므로
--   컬럼 없이 새 코드가 뜨면 전 요청이 죽는다. 구 코드는 새 컬럼이 있어도 무해하다.
--
-- 멱등하다 — 다시 돌려도 안전하다. 트랜잭션 하나라 중간에 실패하면 전부 되돌아간다.

BEGIN;

-- 1) users.is_active — 비활성 계정(A4). 삭제 대신 쓴다.
ALTER TABLE users ADD COLUMN IF NOT EXISTS is_active boolean NOT NULL DEFAULT true;

-- 2) email_logs — 확정 제목·본문(수동·에이전트 발송)과 발송 주체.
ALTER TABLE email_logs ADD COLUMN IF NOT EXISTS subject text;
ALTER TABLE email_logs ADD COLUMN IF NOT EXISTS body text;
ALTER TABLE email_logs
    ADD COLUMN IF NOT EXISTS actor_kind varchar(10) NOT NULL DEFAULT 'system';
ALTER TABLE email_logs ADD COLUMN IF NOT EXISTS actor_id bigint;

-- FK 는 IF NOT EXISTS 가 없다. 이름으로 존재를 확인하고 없을 때만 건다.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'email_logs_actor_id_fkey'
    ) THEN
        ALTER TABLE email_logs
            ADD CONSTRAINT email_logs_actor_id_fkey
            FOREIGN KEY (actor_id) REFERENCES users(id);
    END IF;
END $$;

-- 3) stage 제약 교체 — 'custom'(수동·에이전트 발송)을 허용값에 넣는다.
--    STAGES 자체는 안 늘린다. applications.current_stage 는 그대로여야 한다.
ALTER TABLE email_logs DROP CONSTRAINT IF EXISTS ck_email_logs_stage;

-- 교체 전에 모르는 값이 있으면 멈춘다 — 조용히 통과시키지 않는다.
DO $$
DECLARE
    leftover text;
BEGIN
    SELECT string_agg(DISTINCT stage, ', ') INTO leftover
    FROM email_logs
    WHERE stage NOT IN ('applied', 'screening', 'interview', 'accepted', 'rejected', 'custom');

    IF leftover IS NOT NULL THEN
        RAISE EXCEPTION '알 수 없는 stage 가 email_logs 에 있습니다: %', leftover;
    END IF;
END $$;

ALTER TABLE email_logs ADD CONSTRAINT ck_email_logs_stage
    CHECK (stage IN ('applied', 'screening', 'interview', 'accepted', 'rejected', 'custom'));

-- 4) actor_kind 제약.
ALTER TABLE email_logs DROP CONSTRAINT IF EXISTS ck_email_logs_actor_kind;
ALTER TABLE email_logs ADD CONSTRAINT ck_email_logs_actor_kind
    CHECK (actor_kind IN ('human', 'agent', 'system'));

COMMIT;

-- 확인용 (실행 후 수동으로):
--     \d users
--     \d email_logs
--     SELECT actor_kind, count(*) FROM email_logs GROUP BY actor_kind;
