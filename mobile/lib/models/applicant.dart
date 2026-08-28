/// 지원서 — 01-erd.md `applications` 테이블(★핵심)을 옮긴 모델.
///
/// **필드명은 ERD 컬럼명을 그대로 쓴다.** 목데이터 단계에서 이름을 맞춰 두면
/// 큐 8번에서 실제 API 로 갈아끼울 때 화면 코드를 고칠 일이 없다.
///
/// 지금 화면이 쓰지 않는 컬럼(`self_intro` · `ai_summary` · `phone` 등)은
/// 아직 넣지 않았다. 화면에 필요해질 때 그 조각에서 추가한다.
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
    required this.currentStage,
    required this.createdAt,
  });

  /// `applications.id`
  final int id;

  /// `applications.job_posting_id`
  final int jobPostingId;

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
