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
import '../models/job_posting.dart';
import '../models/stage.dart';

/// 공고 하나 + 그 공고의 단계별 인원.
///
/// 카드가 둘 다 필요해서 묶어 나른다 — 화면이 두 목록을 짝지어 들고 있으면
/// 하나만 늦게 와서 어긋나는 순간이 생긴다.
class PostingWithCounts {
  const PostingWithCounts({required this.posting, required this.counts});

  final JobPosting posting;

  /// 단계별 인원. **불합격까지 포함한다** — 퍼널 범례 합이 총원과 같아야 한다.
  /// 4단계만 세면 사람이 조용히 사라진다(2026-09-01 실기기에서 잡은 것)
  final Map<Stage, int> counts;

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

    final counts = await Future.wait(postings.map(_countsFor));

    return [
      for (var i = 0; i < postings.length; i++)
        PostingWithCounts(posting: postings[i], counts: counts[i]),
    ];
  }

  /// 한 공고의 단계별 인원. 목록을 받아 클라이언트에서 센다.
  Future<Map<Stage, int>> _countsFor(JobPosting posting) async {
    final raw = await _client.getList(
      Endpoints.postingApplications(posting.id),
    );

    final counts = {for (final s in Stage.values) s: 0};
    for (final item in raw) {
      final value = (item as Map<String, dynamic>)['current_stage'] as String?;
      // 모르는 단계가 오면 세지 않는다 — 총원이 틀리는 편이 낫다고 볼 수도
      // 있지만, 없는 칸에 넣으면 어느 단계인지 화면이 거짓말을 한다
      final stage = Stage.values.where((s) => s.value == value).firstOrNull;
      if (stage != null) counts[stage] = counts[stage]! + 1;
    }
    return counts;
  }
}
