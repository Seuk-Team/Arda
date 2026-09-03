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

/// 서버 응답 → 모델. `EmailLogOut`(backend/app/schemas/email.py).
///
/// `subject` 는 NULL 로 올 수 있다 — 단계 자동 발송은 보낼 때 렌더하므로
/// 큐에 있는 동안에는 제목이 아직 없다. 그때는 단계 이름으로 대신한다.
extension EmailLogJson on EmailLog {
  static EmailLog fromJson(
    Map<String, dynamic> json, {
    required int applicationId,
  }) => EmailLog(
    id: json['id'] as int,
    applicationId: applicationId,
    subject:
        json['subject'] as String? ?? _stageLabel(json['stage'] as String?),
    status: EmailStatus.values.firstWhere(
      (s) => s.value == json['status'],
      // 모르는 상태는 대기로 둔다 — 발송으로 넘겨짚으면 안 간 것이 간 것처럼 보인다
      orElse: () => EmailStatus.queued,
    ),
    actorKind: EmailActor.values.firstWhere(
      (a) => a.value == json['actor_kind'],
      orElse: () => EmailActor.system,
    ),
    createdAt: DateTime.parse(json['created_at'] as String).toLocal(),
  );

  /// 제목이 아직 없을 때 쓸 이름 — 메일 프리셋과 같은 문구다
  static String _stageLabel(String? stage) => switch (stage) {
    'applied' => '접수 확인',
    'interview' => '면접 안내',
    'accepted' => '최종 합격',
    'rejected' => '불합격',
    _ => '메일',
  };
}
