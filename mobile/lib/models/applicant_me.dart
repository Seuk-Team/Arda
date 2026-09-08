/// 지원자가 로그인해서 보는 자기 것 전부 — `GET /applicant/me` (2026-09-08).
///
/// **조회 인자를 받지 않는다.** 서버가 토큰의 이메일로만 찾는다 — 인자로 받으면
/// 남의 것을 넣어 보는 길이 생긴다(ADR-0031). 그래서 여기 오는 것은 늘 자기
/// 것이고, 담당자 이름·평가·메모·AI 요약·불합격 사유는 오지 않는다.
///
/// ## 아직 할 일이 남은 것만 온다
///
/// 서버가 미리 걸러 준다 — 들어가 봐야 막히는 문은 안 내려온다.
///
///   면접   `pending` · `in_progress`
///   인적성 `pending`
///   일정   `proposed` · **`confirmed`**
///
/// **일정만 확정된 것도 온다.** 확정된 뒤에도 "언제로 잡혔는지" 다시 볼 일이
/// 있어서다. 그래서 일정 탭은 확정 후에도 살아 있어야 한다.
library;

/// 지원자가 지금 들어갈 수 있는 문 하나. 면접·인적성·일정이 같은 모양이다
class TokenLink {
  const TokenLink({required this.token, required this.status, this.expiresAt});

  /// 공개 경로에 그대로 쓰는 값 — 메일 링크에 실리는 것과 같은 토큰이다
  final String token;

  /// 서버 상태값 그대로. 화면은 이걸 자기 열거형으로 옮겨 쓴다
  final String status;

  final DateTime? expiresAt;
}

TokenLink _link(Map<String, dynamic> json) => TokenLink(
  token: json['token'] as String,
  status: json['status'] as String? ?? '',
  expiresAt: switch (json['expires_at']) {
    final String s => DateTime.tryParse(s),
    _ => null,
  },
);

/// 지원 한 건.
class MyApplication {
  const MyApplication({
    required this.id,
    required this.postingTitle,
    required this.stageLabel,
    required this.appliedAt,
    this.interviews = const [],
    this.aptitudes = const [],
    this.schedules = const [],
  });

  final int id;
  final String postingTitle;

  /// 사람이 읽을 단계 — "접수 완료" · "서류 검토 중" 이 그대로 온다.
  ///
  /// **`rejected` 는 "불합격" 으로 오지 않는다.** 담당자가 통보하기 전에 앱이
  /// 먼저 말하면 사람이 전할 말을 화면이 앞지른다 — 포털과 같은 규칙이다.
  final String stageLabel;

  final DateTime appliedAt;

  final List<TokenLink> interviews;
  final List<TokenLink> aptitudes;
  final List<TokenLink> schedules;
}

/// 로그인한 지원자 자신.
class ApplicantMe {
  const ApplicantMe({
    required this.email,
    required this.name,
    this.applications = const [],
  });

  final String email;
  final String name;

  /// 최신 지원이 앞이다(서버가 `created_at desc` 로 준다).
  /// **여러 건일 수 있다** — 한 사람이 공고 여럿에 낸다
  final List<MyApplication> applications;

  /// 화면이 기본으로 여는 지원. 없으면 null
  MyApplication? get primary =>
      applications.isEmpty ? null : applications.first;
}

extension ApplicantMeJson on ApplicantMe {
  static ApplicantMe fromJson(Map<String, dynamic> json) => ApplicantMe(
    email: json['email'] as String? ?? '',
    name: json['name'] as String? ?? '',
    applications: [
      for (final a in (json['applications'] as List? ?? const []))
        _application(a as Map<String, dynamic>),
    ],
  );

  static MyApplication _application(Map<String, dynamic> json) => MyApplication(
    id: json['id'] as int,
    postingTitle: json['posting_title'] as String? ?? '',
    stageLabel: json['stage_label'] as String? ?? '확인 중',
    appliedAt:
        DateTime.tryParse(json['applied_at'] as String? ?? '') ??
        DateTime.now(),
    interviews: _links(json['interviews']),
    aptitudes: _links(json['aptitudes']),
    schedules: _links(json['schedules']),
  );

  static List<TokenLink> _links(Object? raw) => [
    for (final e in (raw as List? ?? const []))
      _link(e as Map<String, dynamic>),
  ];
}
