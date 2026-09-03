/// 대시보드(홈 탭)가 한 번에 받아 오는 것 (큐 8 4단계, 2026-09-03).
///
/// 블록 넷이 소스가 다 달라서 **한 번에 병렬로** 부른다. 순서대로 기다리면
/// 홈 탭을 열 때마다 왕복이 줄줄이 쌓인다 — 웹 `Dashboard.tsx` 도 같다.
///
/// **전형 현황은 진행중 공고만 센다**(2026-09-03 결정). 마감된 공고 지원자가
/// 숫자를 먹으면 "지금 뭘 해야 하나" 가 안 읽힌다. 공고 목록이 이미 공고별
/// 단계 인원과 지원자를 주므로 **요청이 하나도 더 들지 않는다.**
library;

import '../api/api_client.dart';
import '../api/api_error.dart';
import '../api/endpoints.dart';
import '../models/applicant.dart';
import '../models/interview.dart';
import '../models/job_posting.dart';
import '../models/stage.dart';
import 'posting_repository.dart';
import 'schedule_repository.dart';

/// 대시보드 한 화면에 필요한 것 전부.
class DashboardData {
  const DashboardData({
    required this.todayInterviews,
    required this.reviewWaiting,
    required this.openPostings,
    required this.stageCounts,
    required this.applicantsByStage,
    required this.scheduleStatus,
  });

  /// 오늘 확정된 면접
  final List<Interview> todayInterviews;

  /// 내게 배정됐는데 아직 안 본 건수 — 이 앱을 켜는 가장 큰 이유
  final int reviewWaiting;

  /// 진행중 공고 + 그 공고의 단계별 인원
  final List<PostingWithCounts> openPostings;

  /// **진행중 공고만** 합친 단계별 인원
  final Map<Stage, int> stageCounts;

  /// 단계별 지원자 — 대시보드가 단계마다 앞 몇 명의 이름을 적는다
  final Map<Stage, List<Applicant>> applicantsByStage;

  /// 면접 단계 사람의 일정 제안 상태. **묻지 않은 사람은 아예 없다** —
  /// 화면에 이름이 뜨는 몇 명만 물어본다
  final Map<int, ScheduleChip> scheduleStatus;
}

/// 일정 칩 하나 — 상태 + (확정이면) 그 시각.
///
/// **상태만으로는 못 그린다.** 확정은 문구 대신 시각을 적는 규칙인데
/// (`ScheduleStatus.confirmed.label` 이 빈 문자열이다), 그 시각이 오늘이 아닐 수
/// 있다. 오늘 면접 목록에서만 찾으면 **다른 날로 확정된 사람의 칩이 빈 알약이
/// 된다**(2026-09-03 실기기에서 잡은 것). 서버가 `confirmed_slot` 을 같이 주므로
/// 그걸 들고 다닌다 — 웹 `Dashboard.tsx` 의 `scheduleChip` 과 같은 처리다.
class ScheduleChip {
  const ScheduleChip(this.status, {this.confirmedAt});

  final ScheduleStatus status;

  /// 확정된 면접 시각. 확정이 아니면 null
  final DateTime? confirmedAt;
}

class DashboardRepository {
  const DashboardRepository(this._client, this._postings, this._schedules);

  final ApiClient _client;
  final PostingRepository _postings;
  final ScheduleRepository _schedules;

  /// 대시보드에서 이름을 적는 인원 — 이 수만큼만 일정 상태를 묻는다.
  /// 웹은 5명이고 앱 화면은 3명이다(dashboard_screen.dart `_perStage`)
  static const namedPerStage = 3;

  Future<DashboardData> load({required int userId, DateTime? today}) async {
    final day = today ?? DateTime.now();

    // 셋을 동시에 던진다. 순서대로 기다릴 이유가 없다
    final (interviews, waiting, postings) = await (
      _schedules.between(day, day),
      _reviewWaitingCount(userId),
      _postings.list(),
    ).wait;

    final open = [
      for (final p in postings)
        if (p.posting.status == PostingStatus.open) p,
    ];

    // **진행중 공고만** 합친다 (2026-09-03 결정)
    final counts = {for (final s in Stage.values) s: 0};
    for (final p in open) {
      for (final entry in p.counts.entries) {
        counts[entry.key] = counts[entry.key]! + entry.value;
      }
    }

    final byStage = {
      for (final s in Stage.values)
        s: [
          for (final p in open)
            ...p.applicants.where((a) => a.currentStage == s),
        ],
    };

    return DashboardData(
      todayInterviews: interviews,
      reviewWaiting: waiting,
      openPostings: open,
      stageCounts: counts,
      applicantsByStage: byStage,
      scheduleStatus: await _scheduleStatuses(
        (byStage[Stage.interview] ?? const []).take(namedPerStage),
      ),
    );
  }

  /// 내게 배정된 건수 — `GET /interviewers/{id}/applications` 의 `count`.
  ///
  /// 대시보드는 숫자만 보여 주므로 목록을 안 쓴다. 이름이 필요한 평가 대기
  /// 큐는 [assignedIds] 로 id 를 받아 사람마다 상세를 더 받는다.
  Future<int> _reviewWaitingCount(int userId) async {
    final json = await _client.get(Endpoints.assignedApplications(userId));
    return json['count'] as int? ?? 0;
  }

  /// 내게 배정된 지원자 id — 평가 대기 큐가 쓴다.
  ///
  /// **응답에 이름도 공고명도 없다**(`AssignmentOut` 은 id 뿐). 화면을 그리려면
  /// 건마다 상세를 한 번 더 받아야 한다 — 웹 `Evaluations.tsx` 도 똑같이
  /// `Promise.all` 로 병렬로 받는다. 배정이 보통 몇 건이라 그게 낫다.
  Future<List<int>> assignedIds(int userId) async {
    final json = await _client.get(Endpoints.assignedApplications(userId));
    return [
      for (final a in (json['assignments'] as List? ?? const []))
        (a as Map<String, dynamic>)['application_id'] as int,
    ];
  }

  /// 일정 제안 상태 — **이름이 뜨는 몇 명만** 병렬로 묻는다.
  ///
  /// 면접 단계 전원에게 물으면 사람 수만큼 요청이 붙는다. 웹도 화면에 나오는
  /// 인원(최대 `GROUP_LIMIT`)만 묻는다.
  Future<Map<int, ScheduleChip>> _scheduleStatuses(
    Iterable<Applicant> applicants,
  ) async {
    final entries = await Future.wait(
      applicants.map((a) async => MapEntry(a.id, await _statusOf(a.id))),
    );
    return {
      for (final e in entries)
        if (e.value != null) e.key: e.value!,
    };
  }

  /// **404 는 오류가 아니다** — "아직 제안을 안 보냈다" 는 정상 상태다
  /// (웹 `Dashboard.tsx` 주석에도 그렇게 적혀 있다). 화면은 "일정 없음" 으로
  /// 그리므로 여기서 null 로 바꿔 돌려준다.
  Future<ScheduleChip?> _statusOf(int applicationId) async {
    try {
      final json = await _client.get(
        Endpoints.scheduleProposals(applicationId),
      );
      final status = switch (json['status'] as String?) {
        'proposed' => ScheduleStatus.proposed,
        'confirmed' => ScheduleStatus.confirmed,
        'expired' => ScheduleStatus.expired,
        _ => ScheduleStatus.none,
      };

      // 확정이면 그 시각까지 들고 온다 — 오늘이 아닐 수 있고, 그때 시각이
      // 없으면 칩이 빈 알약이 된다
      final slot = json['confirmed_slot'] as Map<String, dynamic>?;
      final startAt = slot?['start_at'] as String?;

      return ScheduleChip(
        status,
        confirmedAt: startAt == null ? null : DateTime.parse(startAt).toLocal(),
      );
    } on ServerError catch (e) {
      if (e.statusCode == 404) return null;
      // 그 밖의 실패는 칩만 비운다 — 일정 칩 하나 때문에 대시보드 전체가
      // 오류가 되면 안 된다
      return null;
    } on ApiError {
      return null;
    }
  }
}
