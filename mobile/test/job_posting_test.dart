// 마감 D-day 표기 — 오늘 날짜에 따라 값이 달라지므로 날짜를 고정해 확인한다.
// 목업 표기: `마감 D-12` (mockup-mobile.html .head-meta)

import 'package:arda/models/job_posting.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  JobPosting withDeadline(DateTime? d) => JobPosting(
    id: 1,
    title: '백엔드 개발자 (신입)',
    status: PostingStatus.open,
    deadline: d,
  );

  test('마감 12일 전이면 D-12', () {
    final p = withDeadline(DateTime(2026, 9, 9));
    expect(p.deadlineLabel(DateTime(2026, 8, 28)), '마감 D-12');
  });

  test('마감 당일이면 D-day', () {
    final p = withDeadline(DateTime(2026, 9, 9));
    expect(p.deadlineLabel(DateTime(2026, 9, 9)), '마감 D-day');
  });

  test('마감일이 지나면 마감', () {
    final p = withDeadline(DateTime(2026, 9, 9));
    expect(p.deadlineLabel(DateTime(2026, 9, 10)), '마감');
  });

  test('시각이 달라도 날짜만 본다 — 같은 날이면 D-day', () {
    final p = withDeadline(DateTime(2026, 9, 9));
    expect(p.deadlineLabel(DateTime(2026, 9, 9, 23, 59)), '마감 D-day');
  });

  test('마감일이 없으면(상시 접수) 표기하지 않는다', () {
    expect(withDeadline(null).deadlineLabel(DateTime(2026, 8, 28)), isNull);
  });
}
