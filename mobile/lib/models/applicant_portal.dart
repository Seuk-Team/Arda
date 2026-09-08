/// 지원자가 자기 것으로 보는 것들 — 지원 현황과 면접 (2026-09-08).
///
/// **담당자 모델과 섞지 않는다.** 서버가 지원자에게 주는 것은 담당자용 응답을
/// 줄인 것이 아니라 아예 다른 모양이다: 평가·메모·담당자 이름이 없고,
/// 단계도 내부값(`applied`·`rejected`)이 아니라 **사람이 읽을 말**로 온다
/// (`stage_label`). 특히 `rejected` 는 "불합격" 으로 내려오지 않는다 —
/// 담당자가 통보하기 전에 화면이 먼저 말하면 안 되기 때문이다
/// (backend/app/api/portal.py).
///
/// 그래서 [Stage] 로 되돌리려 하지 않는다. 서버가 준 문장을 그대로 그린다.
library;

/// 링크 하나로 보는 지원 한 건. `PortalStatusOut`.
class PortalStatus {
  const PortalStatus({
    required this.token,
    required this.applicantName,
    required this.postingTitle,
    required this.stageLabel,
    required this.submittedAt,
  });

  /// 이 현황을 연 링크의 토큰. 앱이 다시 물어보려면 들고 있어야 한다
  final String token;

  final String applicantName;
  final String postingTitle;

  /// 사람이 읽을 단계 — "접수 완료" · "서류 검토 중" 같은 말이 그대로 온다
  final String stageLabel;

  final DateTime submittedAt;
}

extension PortalStatusJson on PortalStatus {
  static PortalStatus fromJson(
    Map<String, dynamic> json, {
    required String token,
  }) => PortalStatus(
    token: token,
    applicantName: json['applicant_name'] as String? ?? '',
    postingTitle: json['posting_title'] as String? ?? '',
    stageLabel: json['stage_label'] as String? ?? '확인 중',
    submittedAt:
        DateTime.tryParse(json['submitted_at'] as String? ?? '') ??
        DateTime.now(),
  );
}

/// 면접이 어디쯤인지. `InterviewPublicOut.status`.
enum InterviewStatus {
  /// 아직 시작 전 — 동의가 필요할 수도 있다
  pending('pending'),

  /// 진행 중 — 답할 질문이 있다
  inProgress('in_progress'),

  /// 끝났다
  done('done'),

  /// 링크 유효 기간이 지났다
  expired('expired');

  const InterviewStatus(this.value);

  final String value;

  /// 모르는 값이 오면 [pending] 으로 두지 않고 [expired] 로 둔다 —
  /// 없는 상태를 "지금 하면 된다" 로 읽으면 지원자가 시작 버튼을 눌렀다가
  /// 서버에서 거절당한다. 못 여는 쪽이 덜 나쁘다
  static InterviewStatus parse(String? value) =>
      InterviewStatus.values.firstWhere(
        (s) => s.value == value,
        orElse: () => InterviewStatus.expired,
      );
}

/// 지원자가 보는 면접 한 건. `InterviewPublicOut`.
class InterviewPublic {
  const InterviewPublic({
    required this.token,
    required this.status,
    required this.applicantName,
    required this.postingTitle,
    required this.consentRequired,
    this.currentQuestion,
    this.questionSeq,
    this.expiresAt,
    this.pacing,
  });

  /// 이 면접을 연 링크의 토큰
  final String token;

  final InterviewStatus status;
  final String applicantName;
  final String postingTitle;

  /// 아직 동의를 안 했다. 동의 없이는 시작할 수 없다
  final bool consentRequired;

  /// 지금 답할 질문. 진행 중이 아니면 null
  final String? currentQuestion;

  /// 몇 번째 질문인지. **전체가 몇 개인지는 서버가 주지 않는다** —
  /// `InterviewPublicOut` 에 총 문항 수가 없어서 "3문항 중 2번째" 를 못 그린다.
  /// 백엔드에 요청해 둔 값이고, 오면 여기 붙인다
  final int? questionSeq;

  final DateTime? expiresAt;

  /// 답변 직후에만 온다. **서버가 저장하지 않아** 다시 조회하면 사라진다 —
  /// 그래서 답변 응답을 그대로 화면 상태로 써야 한다(웹 Interview.tsx 와 같다)
  final String? pacing;

  bool get canStart => status == InterviewStatus.pending && !consentRequired;
}

extension InterviewPublicJson on InterviewPublic {
  static InterviewPublic fromJson(
    Map<String, dynamic> json, {
    required String token,
  }) => InterviewPublic(
    token: token,
    status: InterviewStatus.parse(json['status'] as String?),
    applicantName: json['applicant_name'] as String? ?? '',
    postingTitle: json['posting_title'] as String? ?? '',
    consentRequired: json['consent_required'] as bool? ?? false,
    currentQuestion: json['current_question'] as String?,
    questionSeq: json['question_seq'] as int?,
    expiresAt: switch (json['expires_at']) {
      final String s => DateTime.tryParse(s),
      _ => null,
    },
    pacing: switch (json['pacing']) {
      final Map<String, dynamic> m => m['message'] as String?,
      _ => null,
    },
  );
}
