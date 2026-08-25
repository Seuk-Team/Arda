"""담당자 메모 (D7).

평가(`evaluations`)와 나뉘어 있다. 평가는 점수 1~5 가 필수라, "전화 안 받음" 같은
점수 없는 기록이 섞이면 평가 목록과 평균이 오염된다 (01-erd.md).
"""

from fastapi import APIRouter, Depends, HTTPException, status as http
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import assert_can_view_application, get_current_user
from app.models import Application, ApplicationNote, User
from app.schemas.note import NoteCreate, NoteOut, NoteUpdate

router = APIRouter(prefix="/api/v1", tags=["notes"])


def _to_out(note: ApplicationNote, author_name: str) -> NoteOut:
    return NoteOut(
        id=note.id,
        application_id=note.application_id,
        author_id=note.author_id,
        author_name=author_name,
        body=note.body,
        created_at=note.created_at,
        updated_at=note.updated_at,
    )


def _get_note_or_404(db: Session, note_id: int) -> ApplicationNote:
    note = db.get(ApplicationNote, note_id)
    if note is None:
        raise HTTPException(http.HTTP_404_NOT_FOUND, "메모를 찾을 수 없습니다")
    return note


def _assert_author(note: ApplicationNote, user: User) -> None:
    """수정·삭제는 작성자 본인만 (02-api.md · 01-erd.md).

    admin 도 예외로 두지 않는다. 메모는 그 사람이 그때 무엇을 봤는지의 기록이라,
    남이 고치면 기록으로서의 값이 사라진다.
    """
    if note.author_id != user.id:
        raise HTTPException(
            http.HTTP_403_FORBIDDEN, "본인이 쓴 메모만 수정·삭제할 수 있습니다"
        )


@router.get("/applications/{application_id}/notes", response_model=list[NoteOut])
def list_notes(
    application_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """메모 목록 (최신순). 그 지원자를 볼 수 있는 사람만 (A3)."""
    if db.get(Application, application_id) is None:
        raise HTTPException(http.HTTP_404_NOT_FOUND, "지원자를 찾을 수 없습니다")
    assert_can_view_application(db, user, application_id)

    # 작성자 이름을 함께 준다 — 목록에서 id 만 보면 누가 썼는지 알 수 없다.
    # 메모마다 사용자를 따로 조회하면 N+1 이므로 조인 한 번으로 끝낸다.
    rows = db.execute(
        select(ApplicationNote, User.name)
        .join(User, User.id == ApplicationNote.author_id)
        .where(ApplicationNote.application_id == application_id)
        .order_by(ApplicationNote.created_at.desc(), ApplicationNote.id.desc())
    ).all()
    return [_to_out(note, name) for note, name in rows]


@router.post(
    "/applications/{application_id}/notes",
    response_model=NoteOut,
    status_code=http.HTTP_201_CREATED,
)
def create_note(
    application_id: int,
    body: NoteCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """메모 작성. 작성자는 토큰의 사용자다."""
    if db.get(Application, application_id) is None:
        raise HTTPException(http.HTTP_404_NOT_FOUND, "지원자를 찾을 수 없습니다")
    assert_can_view_application(db, user, application_id)

    note = ApplicationNote(
        application_id=application_id, author_id=user.id, body=body.body
    )
    db.add(note)
    db.commit()
    db.refresh(note)
    return _to_out(note, user.name)


@router.patch("/notes/{note_id}", response_model=NoteOut)
def update_note(
    note_id: int,
    body: NoteUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """메모 수정. 작성자 본인만."""
    note = _get_note_or_404(db, note_id)
    _assert_author(note, user)

    # ADR-0005 — 한 문서를 실시간으로 함께 고치지는 않지만, 같은 사람이 두 탭·두 기기에서
    # 열어두고 각각 저장하면 나중 저장이 앞 저장을 조용히 지운다. 그것만 막는다.
    if body.updated_at != note.updated_at:
        raise HTTPException(
            http.HTTP_409_CONFLICT,
            "다른 곳에서 먼저 수정됐습니다. 새로고침 후 다시 시도하세요",
        )

    note.body = body.body
    db.commit()
    db.refresh(note)
    return _to_out(note, user.name)


@router.delete("/notes/{note_id}", status_code=http.HTTP_204_NO_CONTENT)
def delete_note(
    note_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """메모 삭제. 작성자 본인만."""
    note = _get_note_or_404(db, note_id)
    _assert_author(note, user)

    db.delete(note)
    db.commit()
