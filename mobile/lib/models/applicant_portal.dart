/// 지원자가 보는 면접 한 건 — `InterviewPublicOut` (2026-09-08).
///
/// **담당자 모델과 섞지 않는다.** 서버가 지원자에게 주는 것은 담당자용 응답을
/// 줄인 것이 아니라 아예 다른 모양이다: 평가·메모·담당자 이름이 없다.
///
/// 인적성·일정은 [models/applicant_extra.dart], 로그인해서 받는 자기 지원
/// 목록은 [models/applicant_me.dart] 에 있다.
library;

/// 면접이 어디쯤인지.
///
/// **AI 면접인지 실시간 면접인지는 이 값으로 못 가린다** — 세션 테이블에 종류
/// 컬럼이 없고 두 방식이 같은 세션·같은 토큰을 공유한다(백엔드 확인,
/// 2026-09-08). 앱은 AI 면접만 붙이므로 늘 `/public/interview/{token}` 으로
/// 가고, 이 값으로는 "동의부터인지 이어서인지" 만 고른다.
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

  /// 아직 동의를 안 했다. **동의 없이는 `/start` 가 422 로 막는다** —
  /// 지원 폼의 개인정보 동의와 별개다(그때는 녹음이 없었다)
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
