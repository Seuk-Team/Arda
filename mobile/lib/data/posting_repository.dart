/// 공고 — 서버에서 받아 온다 (큐 8, 2026-09-02).
///
/// 화면은 이 클래스만 부른다. 경로·JSON 모양은 화면이 알 필요가 없고,
/// 목데이터로 되돌리거나 캐시를 얹더라도 화면은 그대로여야 한다.
///
/// **단계별 인원(퍼널)은 목록 응답에 없다.** `GET /postings` 는 총 지원자 수
/// (`application_count`)만 준다. 웹은 공고마다 단계별로 4번씩 더 부르는데
/// (`/applications?stage=&posting_id=&limit=1&with_total=true`) 폰에서 공고 3개면
/// 요청이 12개다. 앱은 **공고당 한 번**만 부르고 클라이언트에서 센다 —
/// 목록이 크지 않고(한 공고에 수십 명), 왕복 수가 줄어드는 쪽이 폰에서 낫다.
library;

import '../api/api_client.dart';
import '../api/endpoints.dart';
import '../models/applicant.dart';
import '../models/job_posting.dart';
import '../models/stage.dart';

/// 공고 하나 + 그 공고의 단계별 인원.
///
/// 카드가 둘 다 필요해서 묶어 나른다 — 화면이 두 목록을 짝지어 들고 있으면
/// 하나만 늦게 와서 어긋나는 순간이 생긴다.
class PostingWithCounts {
  const PostingWithCounts({
    required this.posting,
    required this.counts,
    this.applicants = const [],
  });

  final JobPosting posting;

  /// 단계별 인원. **불합격까지 포함한다** — 퍼널 범례 합이 총원과 같아야 한다.
  /// 4단계만 세면 사람이 조용히 사라진다(2026-09-01 실기기에서 잡은 것)
  final Map<Stage, int> counts;

  /// 그 공고의 지원자들. **인원을 세려고 어차피 다 받아 온다** — 버리지 않고
  /// 들고 있으면 대시보드가 이름을 쓰는 데 요청이 하나도 더 안 든다
  /// (큐 8 4단계, 2026-09-03)
  final List<Applicant> applicants;

  int get total => counts.values.fold(0, (a, b) => a + b);
}

class PostingRepository {
  const PostingRepository(this._client);

  final ApiClient _client;

  /// 공고 목록 + 각 공고의 단계별 인원.
  ///
  /// 인원 요청은 병렬로 보낸다. 순서대로 기다리면 공고 수만큼 왕복이 쌓인다.
  Future<List<PostingWithCounts>> list() async {
    final raw = await _client.getList(Endpoints.postings);
    final postings = [
      for (final item in raw)
        JobPostingJson.fromJson(item as Map<String, dynamic>),
    ];

    return Future.wait(postings.map(_withCounts));
  }

  /// 한 공고 + 그 공고의 지원자·단계별 인원. 목록을 받아 클라이언트에서 센다.
  Future<PostingWithCounts> _withCounts(JobPosting posting) async {
    final raw = await _client.getList(
      Endpoints.postingApplications(posting.id),
    );

    final applicants = [
      for (final item in raw)
        ApplicantJson.fromListJson(
          item as Map<String, dynamic>,
          jobPostingId: posting.id,
        ),
    ];

    final counts = {for (final s in Stage.values) s: 0};
    for (final a in applicants) {
      counts[a.currentStage] = counts[a.currentStage]! + 1;
    }

    return PostingWithCounts(
      posting: posting,
      counts: counts,
      applicants: applicants,
    );
  }

  /// 공고를 만든다 — `POST /postings` (큐 8 3단계, 2026-09-03).
  ///
  /// **웹에는 아직 없는 동작이다.** `Postings.tsx` 의 `[+]` 는 아직 아무 데도
  /// 연결돼 있지 않다(핸들러 없음). 앱이 먼저 붙인다.
  ///
  /// `description` 은 보내지 않는다. 서버 스키마에는 있지만 시안·웹 어디에도
  /// 입력칸이 없다 — 없는 칸을 앱이 혼자 만들지 않는다.
  Future<JobPosting> create({
    required String title,
    required PostingStatus status,
    DateTime? deadline,
  }) async {
    final json = await _client.post(
      Endpoints.postings,
      body: {
        'title': title,
        'status': status.value,
        // 비우면 열쇠를 아예 안 보낸다 — `null` 을 보내는 것과 같지만
        // 서버 기본값(상시)을 그대로 쓰는 편이 뜻이 분명하다
        if (deadline != null) 'deadline': _apiDate(deadline),
      },
    );
    return JobPostingJson.fromJson(json);
  }

  /// 공고를 고친다 — `PATCH /postings/{id}` (2026-09-03).
  ///
  /// **마감일은 바뀌었을 때만 보낸다** ([changeDeadline]). 서버는 보낸 열쇠만
  /// 검사하는데(`exclude_unset`), 마감일 검사가 *지난 날짜를 거절*한다
  /// (`_reject_past`, backend/app/schemas/posting.py). 그래서 이미 마감이 지난
  /// 공고의 마감일을 그대로 되보내면 **제목만 고치려 해도 422 로 막힌다.**
  /// 안 건드렸으면 안 보내는 것이 맞다.
  ///
  /// 지운 경우(`changeDeadline: true, deadline: null`)는 `null` 을 명시해
  /// 보낸다 — 상시로 바꾸라는 뜻이고 서버가 그건 막지 않는다.
  ///
  /// `description` 은 여기서도 안 보낸다 — 앱에 입력칸이 없다. 안 보내면
  /// 서버가 건드리지 않으므로 웹에서 적은 것이 지워지지 않는다.
  Future<JobPosting> update(
    int id, {
    required String title,
    required PostingStatus status,
    required bool changeDeadline,
    DateTime? deadline,
  }) async {
    final json = await _client.patch(
      Endpoints.posting(id),
      body: {
        'title': title,
        'status': status.value,
        if (changeDeadline)
          'deadline': deadline == null ? null : _apiDate(deadline),
      },
    );
    return JobPostingJson.fromJson(json);
  }

  /// `2026-09-17` — 서버가 `format: date` 로 받는다. 화면 표기(`2026.09.17`,
  /// [formatDate])와 다르므로 섞어 쓰지 않는다
  static String _apiDate(DateTime d) =>
      '${d.year.toString().padLeft(4, '0')}-'
      '${d.month.toString().padLeft(2, '0')}-'
      '${d.day.toString().padLeft(2, '0')}';
}
