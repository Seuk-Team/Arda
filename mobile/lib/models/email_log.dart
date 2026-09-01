/// 메일 발송 기록 — 01-erd `email_logs` 를 옮긴 모델.
///
/// 지원자 상세의 "시스템" 줄이 이걸 읽는다. **실패를 놓치면 지원자가 연락을
/// 받지 못한다** — 그래서 화면에서 실패만 적갈로 띄운다(05-design §1 종료 신호).
library;

/// `email_logs.status`
enum EmailStatus {
  queued('queued', '대기'),
  sent('sent', '발송'),
  failed('failed', '실패');

  const EmailStatus(this.value, this.label);

  final String value;
  final String label;
}

/// `email_logs.actor_kind` — 서명과 회신 주소가 이 값으로 갈린다 (G4).
enum EmailActor {
  /// 사람이 화면에서 트리거·작성
  human('human'),

  /// 아르가 문안 작성. **책임 주체는 도구를 승인한 사람**이다
  agent('agent'),

  /// 지원자 본인의 행동이 트리거 — 접수 확인·일정 확정
  system('system');

  const EmailActor(this.value);

  final String value;
}

class EmailLog {
  const EmailLog({
    required this.id,
    required this.applicationId,
    required this.subject,
    required this.status,
    required this.actorKind,
    required this.createdAt,
  });

  final int id;
  final int applicationId;

  /// `email_logs.subject` — NULL 이면 발송 시점 렌더(단계 자동 발송)라
  /// 서버가 렌더한 제목을 내려 준다
  final String subject;

  final EmailStatus status;
  final EmailActor actorKind;
  final DateTime createdAt;
}
