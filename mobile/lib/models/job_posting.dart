/// 채용 공고 — 01-erd.md `job_postings` 테이블에서 화면이 쓰는 부분만.
library;

/// `job_postings.status` — ERD 고정값.
enum PostingStatus {
  draft('draft', '작성 중'),
  open('open', '진행중'),
  closed('closed', '마감');

  const PostingStatus(this.value, this.label);

  /// DB 에 저장되는 값
  final String value;

  /// 화면에 보이는 이름. 시안 5번의 칩 문구를 따른다
  final String label;

  static PostingStatus fromValue(String value) =>
      PostingStatus.values.firstWhere((s) => s.value == value);
}

class JobPosting {
  const JobPosting({
    required this.id,
    required this.title,
    required this.status,
    this.deadline,
  });

  /// `job_postings.id`
  final int id;

  /// `job_postings.title`
  final String title;

  /// `job_postings.status`
  final PostingStatus status;

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

  /// 시안 5번: 마감된 공고는 D-day 대신 **마감일 날짜**를 적는다.
  /// "색을 못 봐도 마감 여부가 읽힌다"는 것이 시안의 이유다.
  String? deadlineOrDate(DateTime today) {
    final d = deadline;
    if (d == null) return null;
    if (status == PostingStatus.closed) {
      return '${d.year}.${d.month.toString().padLeft(2, '0')}'
          '.${d.day.toString().padLeft(2, '0')}';
    }
    return deadlineLabel(today);
  }
}
