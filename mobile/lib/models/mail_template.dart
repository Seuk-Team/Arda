/// 메일 문구 — 설정 `메일 템플릿` 탭 (큐 8 4단계, 2026-09-03).
///
/// **자동 발송도 이 문구를 쓴다.** 단계를 바꾸면 서버가 여기 저장된 것으로
/// 메일을 만들어 보내므로, 고치면 이후 모든 지원자에게 나가는 글이 바뀐다.
/// 앱은 그래서 읽기만 한다.
library;

class MailTemplate {
  const MailTemplate({
    required this.stage,
    required this.subject,
    required this.body,
    required this.isDefault,
    this.updatedByName,
  });

  /// `applied` · `interview` · `accepted` · `rejected`
  final String stage;

  final String subject;
  final String body;

  /// 아무도 안 고친 기본 문구인가. 고친 것이면 누가 고쳤는지가 [updatedByName]
  final bool isDefault;

  final String? updatedByName;

  /// 화면에 쓰는 이름 — 메일 프리셋과 같은 문구다
  String get label => switch (stage) {
    'applied' => '접수 확인',
    'interview' => '면접 안내',
    'accepted' => '최종 합격',
    'rejected' => '불합격',
    _ => stage,
  };
}

/// 서버 응답 → 모델. `TemplateOut`(backend/app/schemas/email.py).
extension MailTemplateJson on MailTemplate {
  static MailTemplate fromJson(Map<String, dynamic> json) => MailTemplate(
    stage: json['stage'] as String? ?? '',
    subject: json['subject'] as String? ?? '',
    body: json['body'] as String? ?? '',
    // `source` 는 'default' 아니면 'custom' 이다
    isDefault: json['source'] != 'custom',
    updatedByName: json['updated_by_name'] as String?,
  );
}
