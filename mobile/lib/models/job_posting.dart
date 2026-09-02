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

    final days = DateTime(
      d.year,
      d.month,
      d.day,
    ).difference(DateTime(today.year, today.month, today.day)).inDays;

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

/// 서버 응답 → 모델. `PostingOut`(backend/app/schemas/posting.py).
///
/// 서버는 `application_count`(총 지원자)와 `d_day`(계산값)도 주지만 담지 않는다 —
/// 총원은 [postingCounts] 합으로 이미 나오고, D-day 는 [deadlineLabel] 이
/// 오늘 날짜로 다시 계산한다. 서버가 준 d_day 를 들고 있으면 앱을 켜 둔 채
/// 날이 바뀌었을 때 어제 값이 남는다.
extension JobPostingJson on JobPosting {
  static JobPosting fromJson(Map<String, dynamic> json) => JobPosting(
    id: json['id'] as int,
    title: json['title'] as String,
    status: _status(json['status'] as String?),
    // `deadline` 은 date 라 "2026-09-09" 로 온다. NULL 이면 상시 접수
    deadline: switch (json['deadline']) {
      final String s => DateTime.parse(s),
      _ => null,
    },
  );

  /// 모르는 상태가 오면 `작성 중` 으로 둔다 — 진행중으로 넘겨짚으면
  /// 지원 링크가 열려 있는 것처럼 보인다
  static PostingStatus _status(String? value) => PostingStatus.values
      .firstWhere((s) => s.value == value, orElse: () => PostingStatus.draft);

  /// 서버가 준 총 지원자 수. 퍼널을 아직 못 받았을 때 카드가 쓸 값이다
  static int countOf(Map<String, dynamic> json) =>
      json['application_count'] as int? ?? 0;
}
