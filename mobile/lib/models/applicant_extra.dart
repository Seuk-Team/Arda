/// 지원자가 보는 나머지 둘 — 인적성 검사와 면접 시간 조율 (2026-09-08).
///
/// 지원 현황·면접은 [models/applicant_portal.dart] 에 있다. 여기와 저기 모두
/// **담당자 응답을 줄인 것이 아니라 아예 다른 모양**이다: 면접관도, 평가도,
/// 다른 지원자도 안 온다.
library;

/// 인적성 검사가 어디쯤인지.
enum AptitudeStatus {
  /// 아직 안 냈다 — 문항이 같이 온다
  pending('pending'),

  /// 제출했다. **다시 낼 수 없다** (서버가 막는다)
  submitted('submitted'),

  /// 링크 유효 기간이 지났다
  expired('expired');

  const AptitudeStatus(this.value);

  final String value;

  /// 모르는 값은 [expired] 로 둔다 — 없는 상태를 "지금 하면 된다" 로 읽으면
  /// 다 풀고 나서 서버에 거절당한다
  static AptitudeStatus parse(String? value) =>
      AptitudeStatus.values.firstWhere(
        (s) => s.value == value,
        orElse: () => AptitudeStatus.expired,
      );
}

class AptitudeQuestion {
  const AptitudeQuestion({required this.key, required this.text});

  final String key;
  final String text;
}

class AptitudePublic {
  const AptitudePublic({
    required this.token,
    required this.status,
    required this.applicantName,
    required this.postingTitle,
    this.questions = const [],
    this.likertLabels = const {},
    this.expiresAt,
  });

  final String token;
  final AptitudeStatus status;
  final String applicantName;
  final String postingTitle;

  /// **아직 안 냈을 때만 온다.** 제출 뒤에는 빈 목록이다
  final List<AptitudeQuestion> questions;

  /// 1~5 에 붙는 말. 서버가 정한다 — 앱이 지어내지 않는다
  final Map<int, String> likertLabels;

  final DateTime? expiresAt;
}

extension AptitudePublicJson on AptitudePublic {
  static AptitudePublic fromJson(
    Map<String, dynamic> json, {
    required String token,
  }) => AptitudePublic(
    token: token,
    status: AptitudeStatus.parse(json['status'] as String?),
    applicantName: json['applicant_name'] as String? ?? '',
    postingTitle: json['posting_title'] as String? ?? '',
    questions: [
      for (final q in (json['questions'] as List? ?? const []))
        AptitudeQuestion(
          key: (q as Map<String, dynamic>)['key'] as String,
          text: q['text'] as String? ?? '',
        ),
    ],
    likertLabels: {
      for (final e in (json['likert_labels'] as Map? ?? const {}).entries)
        ?int.tryParse('${e.key}'): '${e.value}',
    },
    expiresAt: switch (json['expires_at']) {
      final String s => DateTime.tryParse(s),
      _ => null,
    },
  );
}

/// 면접 시간 제안이 어디쯤인지.
enum ScheduleStatus {
  /// 후보 시간이 와 있다 — 고르면 그 자리에서 확정된다
  proposed('proposed'),

  /// 확정됐다
  confirmed('confirmed'),

  /// 선택 기한이 지났다
  expired('expired');

  const ScheduleStatus(this.value);

  final String value;

  static ScheduleStatus parse(String? value) =>
      ScheduleStatus.values.firstWhere(
        (s) => s.value == value,
        orElse: () => ScheduleStatus.expired,
      );
}

/// 후보 시간 한 칸. **면접관이 누구인지는 안 온다** — 지원자에게 줄 정보가 아니다
class ScheduleSlot {
  const ScheduleSlot({
    required this.id,
    required this.startAt,
    required this.endAt,
  });

  final int id;
  final DateTime startAt;
  final DateTime endAt;
}

class SchedulePublic {
  const SchedulePublic({
    required this.token,
    required this.status,
    required this.applicantName,
    required this.postingTitle,
    required this.currentStage,
    this.slots = const [],
    this.confirmedSlot,
    this.expiresAt,
  });

  final String token;
  final ScheduleStatus status;
  final String applicantName;
  final String postingTitle;

  /// 전형 현황 — 링크 하나로 일정과 같이 확인하라고 서버가 같이 준다.
  /// **내부 단계값**(`applied`·`screening`…)이 그대로 온다
  final String currentStage;

  final List<ScheduleSlot> slots;

  /// 확정됐을 때만 값이 있다
  final ScheduleSlot? confirmedSlot;

  final DateTime? expiresAt;
}

extension SchedulePublicJson on SchedulePublic {
  static ScheduleSlot _slot(Map<String, dynamic> json) => ScheduleSlot(
    id: json['id'] as int,
    startAt: DateTime.parse(json['start_at'] as String).toLocal(),
    endAt: DateTime.parse(json['end_at'] as String).toLocal(),
  );

  static SchedulePublic fromJson(
    Map<String, dynamic> json, {
    required String token,
  }) => SchedulePublic(
    token: token,
    status: ScheduleStatus.parse(json['status'] as String?),
    applicantName: json['applicant_name'] as String? ?? '',
    postingTitle: json['posting_title'] as String? ?? '',
    currentStage: json['current_stage'] as String? ?? '',
    slots: [
      for (final s in (json['slots'] as List? ?? const []))
        _slot(s as Map<String, dynamic>),
    ],
    confirmedSlot: switch (json['confirmed_slot']) {
      final Map<String, dynamic> m => _slot(m),
      _ => null,
    },
    expiresAt: switch (json['expires_at']) {
      final String s => DateTime.tryParse(s),
      _ => null,
    },
  );
}
