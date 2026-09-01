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
  String get summaryLine => [
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
