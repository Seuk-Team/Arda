-- 역할 2종화 데이터 이행 (ADR-0017) — 2026-08-31, 1회성.
--
-- 기존 역할 3종(admin·recruiter·interviewer)을 2종(admin·member)으로 접는다.
-- admin 은 그대로 두고, recruiter·interviewer 를 전부 member 로 바꾼다.
--
-- 이 저장소에는 alembic 이 없다 (app/db.py 주석 참고 — create_all 로 만들고
-- 스키마가 바뀌면 다시 만든다). 이미 데이터가 있는 DB 만 이 파일이 필요하다.
--
-- 실행:
--     psql "$DATABASE_URL" -f backend/scripts/migrate_roles_to_member.sql
--
-- 주의: 체크 제약(ck_users_role)을 새 값으로 갈아끼우므로, 배포한 코드가
-- ROLES = ("admin", "member") 인 상태에서 돌려야 한다. 트랜잭션 하나로 묶여
-- 있어 중간에 실패하면 전부 되돌아간다.

BEGIN;

-- 1) 기존 제약을 먼저 떼어낸다 — 안 떼면 UPDATE 가 옛 제약에 걸린다.
--    IF EXISTS: create_all 로 갓 만든 DB 에는 이름이 다를 수 있다.
ALTER TABLE users DROP CONSTRAINT IF EXISTS ck_users_role;

-- 2) 값 이행. admin 은 건드리지 않는다.
UPDATE users SET role = 'member' WHERE role IN ('recruiter', 'interviewer');

-- 3) 이행 뒤에도 남은 값이 있으면 멈춘다 — 모르는 역할을 조용히 통과시키지 않는다.
DO $$
DECLARE
    leftover text;
BEGIN
    SELECT string_agg(DISTINCT role, ', ') INTO leftover
    FROM users WHERE role NOT IN ('admin', 'member');

    IF leftover IS NOT NULL THEN
        RAISE EXCEPTION '알 수 없는 역할이 남아 있습니다: %', leftover;
    END IF;
END $$;

-- 4) 새 제약을 건다.
ALTER TABLE users ADD CONSTRAINT ck_users_role CHECK (role IN ('admin', 'member'));

COMMIT;

-- 확인용 (실행 후 수동으로):
--     SELECT role, count(*) FROM users GROUP BY role;
