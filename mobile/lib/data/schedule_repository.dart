/// 면접 일정 — 서버에서 받아 온다 (큐 8 4단계, 2026-09-03).
///
/// **확정된 제안만 온다**(05-design 캘린더 절 · ADR-0016). 앱에서 등록·수정·
/// 삭제는 없다 — 조회 전용이다.
///
/// `GET /schedules` 는 `InterviewOut` 을 주는데 **지원자명·공고명·면접관명이
/// 다 들어 있다.** 평가나 단계 이력과 달리 이름을 더 받으러 갈 일이 없다.
library;

import '../api/api_client.dart';
import '../api/endpoints.dart';
import '../models/interview.dart';

class ScheduleRepository {
  const ScheduleRepository(this._client);

  final ApiClient _client;

  /// [from]~[to] 사이의 확정 면접. 날짜만 쓰므로 시각은 버린다.
  ///
  /// `mine` 은 서버에도 있지만 쓰지 않는다 — 한 주를 통째로 받아 두고 화면에서
  /// 거른다. "내 것만" 을 껐다 켤 때마다 다시 부르면 왕복이 두 배가 된다.
  Future<List<Interview>> between(DateTime from, DateTime to) async {
    final json = await _client.get(Endpoints.schedules(from, to));
    return [
      for (final item in (json['items'] as List? ?? const []))
        InterviewJson.fromJson(item as Map<String, dynamic>),
    ];
  }

  /// 그 주(일요일~토요일) 전체. 캘린더의 주간 스트립이 쓰는 단위다.
  Future<List<Interview>> week(DateTime anchor) {
    final sunday = DateTime(
      anchor.year,
      anchor.month,
      anchor.day,
    ).subtract(Duration(days: anchor.weekday % 7));
    return between(sunday, sunday.add(const Duration(days: 6)));
  }
}

/// 서버 응답 → 모델. `InterviewOut`(backend/app/schemas/schedule.py).
extension InterviewJson on Interview {
  static Interview fromJson(Map<String, dynamic> json) => Interview(
    proposalId: json['proposal_id'] as int,
    applicationId: json['application_id'] as int,
    applicantName: json['applicant_name'] as String? ?? '',
    postingTitle: json['posting_title'] as String? ?? '',
    interviewerId: json['interviewer_id'] as int? ?? 0,
    interviewerName: json['interviewer_name'] as String? ?? '',
    // 서버는 UTC 로 준다. `toLocal()` 을 빼면 9시간 어긋난 시각이 화면에 뜬다
    startAt: DateTime.parse(json['start_at'] as String).toLocal(),
    endAt: DateTime.parse(json['end_at'] as String).toLocal(),
  );
}
