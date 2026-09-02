/// 담당자 메모 — 01-erd `application_notes` 를 옮긴 모델.
///
/// 평가(`evaluations`)와 분리돼 있다. 저쪽은 점수 1~5가 필수라 점수 없는
/// 서술형 기록이 섞이면 평가 목록·평균이 오염된다(ERD 비고).
///
/// **한 문서를 공동 편집하지 않고 각자 행을 추가하는 구조**라 화면도
/// "작성자 · 날짜 + 본문" 시간순 목록이다(05-design 지원자 화면 절).
/// 수정·삭제는 작성자 본인만 — 서버가 `author_id` 로 검사한다.
library;

class ApplicationNote {
  const ApplicationNote({
    required this.id,
    required this.applicationId,
    required this.authorName,
    required this.body,
    required this.createdAt,
  });

  final int id;
  final int applicationId;

  /// `users.name` — ERD 는 `author_id` 를 들고 있고 API 가 이름을 붙여 준다
  final String authorName;

  /// `application_notes.body` — 서술형
  final String body;

  final DateTime createdAt;
}

/// 서버 응답 → 모델.
///
/// **메모만 이름을 준다** — 상세에 박힌 것(`NoteOut`)에는 `author_id` 뿐이지만
/// 전용 엔드포인트(`GET /applications/{id}/notes`)는 `author_name` 을 준다.
/// 그래서 상세 화면은 메모만 한 번 더 부른다.
extension ApplicationNoteJson on ApplicationNote {
  static ApplicationNote fromJson(Map<String, dynamic> json) => ApplicationNote(
    id: json['id'] as int,
    applicationId: json['application_id'] as int,
    authorName: json['author_name'] as String? ?? '알 수 없음',
    body: json['body'] as String,
    createdAt: DateTime.parse(json['created_at'] as String),
  );
}
