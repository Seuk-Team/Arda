/// 채용 공고 — 01-erd.md `job_postings` 테이블에서 화면이 쓰는 부분만.
library;

class JobPosting {
  const JobPosting({
    required this.id,
    required this.title,
    this.deadline,
  });

  /// `job_postings.id`
  final int id;

  /// `job_postings.title`
  final String title;

  /// `job_postings.deadline` — **NULL = 상시 접수** (ERD 비고)
  final DateTime? deadline;

  /// 목업 표기: `마감 D-12` · 당일은 `마감 D-day` · 지나면 `마감`
  ///
  /// 상시 접수(마감일 없음)면 null 을 돌려주고, 화면은 아무것도 그리지 않는다.
  String? deadlineLabel(DateTime today) {
    final d = deadline;
    if (d == null) return null;

    final days = DateTime(d.year, d.month, d.day)
        .difference(DateTime(today.year, today.month, today.day))
        .inDays;

    if (days < 0) return '마감';
    if (days == 0) return '마감 D-day';
    return '마감 D-$days';
  }
}
