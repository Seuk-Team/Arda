/// 지원서 — 01-erd.md `applications` 테이블(★핵심)을 옮긴 모델.
///
/// **필드명은 ERD 컬럼명을 그대로 쓴다.** 목데이터 단계에서 이름을 맞춰 두면
/// 큐 8번에서 실제 API 로 갈아끼울 때 화면 코드를 고칠 일이 없다.
///
/// 아직 안 넣은 컬럼: `self_intro` · `privacy_agreed_at` · `source`.
/// 화면에 필요해질 때 그 조각에서 추가한다.
library;

import 'stage.dart';

class Applicant {
  const Applicant({
    required this.id,
    required this.jobPostingId,
    required this.name,
    required this.email,
    this.education,
    this.careerYears,
    this.skills = const [],
    this.phone,
    this.aiSummary,
    this.aiSummaryAt,
    this.aiSummaryModel,
    required this.currentStage,
    required this.createdAt,
  });

  /// `applications.id`
  final int id;

  /// `applications.job_posting_id`
  final int jobPostingId;

  /// `applications.phone` — 상세의 연락처 줄
  final String? phone;

  /// `applications.ai_summary` — 담당자용 AI 요약. **NULL = 미생성.**
  ///
  /// 05-design §1(2026-09-01 팀장 확정): 읽기만 하는 AI 산출물이라 앰버가
  /// 아니라 정보 블록으로 그린다. 앰버는 사람의 확정을 기다리는 것에만 쓴다.
  final String? aiSummary;

  /// `applications.ai_summary_at` — 생성 시각
  final DateTime? aiSummaryAt;

  /// `applications.ai_summary_model` — 생성 모델 + 프롬프트 태그.
  /// 발표 때 근거로 쓰는 값이라 화면에도 남긴다
  final String? aiSummaryModel;

  /// `applications.name`
  final String name;

  /// `applications.email`
  final String email;

  /// `applications.education` — 최종 학력
  final String? education;

  /// `applications.career_years` — 경력 연차. **신입 = 0** (null 은 미입력)
  final int? careerYears;

  /// `applications.skills` — 기술 태그
  final List<String> skills;

  /// `applications.current_stage`
  final Stage currentStage;

  /// `applications.created_at` — 지원일
  final DateTime createdAt;

  /// 목업 카드의 보조 줄: `2년 · OO대 컴퓨터공학 · Python · FastAPI`
  ///
  /// 05-design §7: 넘치면 한 줄 ellipsis 로 자른다(자르는 것은 화면 쪽 책임).
  /// 카드 한 줄. **목록 API 가 주는 것만 쓴다** (2026-09-02).
  ///
  /// `GET /postings/{id}/applications` 와 `GET /applications` 는
  /// `id · name · email · current_stage · career_years · created_at` 만 준다 —
  /// 학력·기술은 상세(`GET /applications/{id}`)에만 있다. 응답을 가볍게 두려는
  /// 서버 판단이다.
  ///
  /// 그래서 목록 카드는 **경력만** 적는다. 예전엔 학력·기술도 붙였는데
  /// 목데이터라 가능했던 것이고, 서버 데이터로는 늘 비어 있게 된다.
  /// 서버가 목록에 학력·기술을 주게 되면 여기 다시 넣는다.
  String get summaryLine => careerLabel;

  /// 상세 화면용 — 학력·기술까지 있는 긴 줄. 상세는 다 받아 온다
  String get detailSummaryLine => [
    careerLabel,
    if (education != null && education!.isNotEmpty) education!,
    ...skills,
  ].join(' · ');

  /// `신입` / `2년`
  String get careerLabel => switch (careerYears) {
    null => '경력 미입력',
    0 => '신입',
    final y => '$y년',
  };
}

/// 서버 응답 → 모델. **목록과 상세가 다른 모양**이라 둘로 나눈다.
extension ApplicantJson on Applicant {
  /// 목록 항목 — `ApplicationListItem`.
  /// `id · name · email · current_stage · career_years · created_at` 뿐이다.
  ///
  /// [jobPostingId] 를 밖에서 받는 이유: `GET /postings/{id}/applications` 는
  /// 어느 공고인지를 응답에 담지 않는다(경로에 이미 있으니까). 상세로 넘어갈 때
  /// 필요해서 부르는 쪽이 채워 준다.
  static Applicant fromListJson(
    Map<String, dynamic> json, {
    required int jobPostingId,
  }) => Applicant(
    id: json['id'] as int,
    jobPostingId: json['job_posting_id'] as int? ?? jobPostingId,
    name: json['name'] as String,
    email: json['email'] as String? ?? '',
    careerYears: json['career_years'] as int?,
    currentStage: _stage(json['current_stage'] as String?),
    createdAt: DateTime.parse(json['created_at'] as String),
  );

  /// 상세 — `ApplicationDetail`. 학력·기술·연락처·요약까지 다 온다.
  ///
  /// **`ai_summary_model` 은 서버가 주지 않는다.** ERD 에는 컬럼이 있지만
  /// 응답 스키마에 없어서 화면의 "생성 · 모델명" 에서 모델은 빠진다.
  static Applicant fromDetailJson(Map<String, dynamic> json) => Applicant(
    id: json['id'] as int,
    jobPostingId: json['job_posting_id'] as int,
    name: json['name'] as String,
    email: json['email'] as String? ?? '',
    phone: json['phone'] as String?,
    education: json['education'] as String?,
    careerYears: json['career_years'] as int?,
    skills: [
      for (final s in (json['skills'] as List? ?? const [])) s as String,
    ],
    aiSummary: json['ai_summary'] as String?,
    aiSummaryAt: switch (json['ai_summary_at']) {
      final String s => DateTime.parse(s),
      _ => null,
    },
    currentStage: _stage(json['current_stage'] as String?),
    createdAt: DateTime.parse(json['created_at'] as String),
  );

  /// 모르는 단계가 오면 접수로 둔다 — 없는 칸에 넣으면 화면이 거짓말을 한다
  static Stage _stage(String? value) => Stage.values.firstWhere(
    (s) => s.value == value,
    orElse: () => Stage.applied,
  );
}
