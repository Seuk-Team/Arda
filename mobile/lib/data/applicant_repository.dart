/// 지원자 — 서버에서 받아 온다 (큐 8, 2026-09-02).
///
/// 목록과 상세가 **다른 모양**이라는 것이 이 층의 핵심이다:
/// - 목록은 가볍다 (`이름·이메일·단계·경력·지원일`)
/// - 상세는 한 번에 다 온다 (`GET /applications/{id}` 가 단계 이력·평가·메모·
///   첨부·평균 점수까지 같이 준다) — 상세 화면은 요청 하나면 된다
library;

import '../api/api_client.dart';
import '../api/endpoints.dart';
import '../models/applicant.dart';
import '../models/application_note.dart';
import '../models/applicant_file.dart';
import '../models/evaluation.dart';
import '../models/stage_history.dart';

/// 상세 화면이 한 번에 받는 것 전부.
class ApplicantDetail {
  const ApplicantDetail({
    required this.applicant,
    required this.stageHistory,
    required this.evaluations,
    required this.notes,
    required this.files,
    this.avgScore,
  });

  final Applicant applicant;

  /// **최신이 위**로 뒤집어 둔다 — 서버는 오래된 순으로 준다
  final List<StageHistory> stageHistory;

  final List<Evaluation> evaluations;
  final List<ApplicationNote> notes;
  final List<ApplicantFile> files;

  /// 평가 평균. 평가가 없으면 null — **0.0 이 아니다**(D1 지시서).
  /// "0.0" 은 나쁜 평가를 받은 것처럼 읽힌다
  final double? avgScore;
}

class ApplicantRepository {
  const ApplicantRepository(this._client);

  final ApiClient _client;

  /// 한 공고의 지원자. 단계 필터는 화면이 한다 — 목록이 수십 건이라
  /// 단계마다 다시 부르는 것보다 한 번 받아 거르는 쪽이 왕복이 적다
  Future<List<Applicant>> byPosting(int postingId) async {
    final raw = await _client.getList(Endpoints.postingApplications(postingId));
    return [
      for (final item in raw)
        ApplicantJson.fromListJson(
          item as Map<String, dynamic>,
          jobPostingId: postingId,
        ),
    ];
  }

  /// 상세 — 화면 하나에 **요청 둘**이다.
  ///
  /// `GET /applications/{id}` 하나로 상세·이력·평가·메모·첨부가 다 오지만,
  /// 거기 박혀 오는 **메모에는 작성자 이름이 없다**(`author_id` 뿐). 전용
  /// 엔드포인트는 `author_name` 을 주므로 메모만 한 번 더 받는다 —
  /// "이서연 · 08.21" 과 "알 수 없음 · 08.21" 은 쓸모가 다르다.
  ///
  /// 평가·이력도 이름이 없지만 **전용 엔드포인트도 마찬가지**라 더 부를 이유가
  /// 없다. 그쪽은 이름 없이 그린다 (2026-09-02 실측).
  Future<ApplicantDetail> detail(int id) async {
    final json = await _client.get(Endpoints.application(id));

    // 메모는 이름 때문에 따로 받는다. 실패해도 상세는 보여 준다 —
    // 메모 하나 때문에 화면 전체가 오류가 되면 안 된다
    var notes = <ApplicationNote>[];
    try {
      final raw = await _client.getList(Endpoints.applicationNotes(id));
      notes = [
        for (final n in raw)
          ApplicationNoteJson.fromJson(n as Map<String, dynamic>),
      ];
    } on Exception {
      notes = const [];
    }

    List<T> children<T>(String key, T Function(Map<String, dynamic>) parse) => [
      for (final item in (json[key] as List? ?? const []))
        parse(item as Map<String, dynamic>),
    ];

    return ApplicantDetail(
      applicant: ApplicantJson.fromDetailJson(json),
      // 서버는 오래된 순으로 준다. 화면은 **최신이 위**다
      stageHistory: children(
        'stage_history',
        (m) => StageHistoryJson.fromJson(m, applicationId: id),
      ).reversed.toList(),
      evaluations: children(
        'evaluations',
        (m) => EvaluationJson.fromJson(m, applicationId: id),
      ),
      notes: notes,
      files: children(
        'files',
        (m) => ApplicantFileJson.fromJson(m, applicationId: id),
      ),
      avgScore: (json['avg_score'] as num?)?.toDouble(),
    );
  }
}
