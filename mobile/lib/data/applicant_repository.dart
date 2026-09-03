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
import '../models/stage.dart';
import '../models/application_note.dart';
import '../models/applicant_file.dart';
import '../models/email_log.dart';
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
    this.emails = const [],
    this.avgScore,
  });

  final Applicant applicant;

  /// **최신이 위**로 뒤집어 둔다 — 서버는 오래된 순으로 준다
  final List<StageHistory> stageHistory;

  final List<Evaluation> evaluations;
  final List<ApplicationNote> notes;
  final List<ApplicantFile> files;

  /// 메일 이력 — **상세 응답에 없다.** 따로 받아 붙인다 (큐 8 4단계)
  final List<EmailLog> emails;

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

  /// 상세 — 화면 하나에 **요청 셋**이다.
  ///
  /// `GET /applications/{id}` 하나로 상세·이력·평가·메모·첨부가 다 오지만,
  /// 거기 박혀 오는 **메모에는 작성자 이름이 없다**(`author_id` 뿐). 전용
  /// 엔드포인트는 `author_name` 을 주므로 메모만 한 번 더 받는다 —
  /// "이서연 · 08.21" 과 "알 수 없음 · 08.21" 은 쓸모가 다르다.
  ///
  /// **메일 이력은 상세 응답에 아예 없어** 세 번째 요청이 된다 (큐 8 4단계).
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

    // 메일 이력도 상세 응답에 없다(`ApplicationDetail` 에 emails 가 없다).
    // 같은 이유로 따로 받고 실패하면 비운다 — 이력 하나 때문에 화면 전체가
    // 오류가 되면 안 된다
    var emails = <EmailLog>[];
    try {
      final res = await _client.get(Endpoints.applicationEmails(id));
      emails = [
        for (final e in (res['items'] as List? ?? const []))
          EmailLogJson.fromJson(e as Map<String, dynamic>, applicationId: id),
      ];
    } on Exception {
      emails = const [];
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
      emails: emails,
      files: children(
        'files',
        (m) => ApplicantFileJson.fromJson(m, applicationId: id),
      ),
      avgScore: (json['avg_score'] as num?)?.toDouble(),
    );
  }

  /// 전 공고 통합 검색 — `GET /applications` (큐 8 4단계, 2026-09-03).
  ///
  /// **공고명이 안 온다**(`job_posting_id` 뿐). 화면이 공고 목록을 따로 받아
  /// `id → 제목` 표를 만들어 붙인다 — 웹 `Applicants.tsx` 의 `postingMap` 과 같다.
  ///
  /// **`q` 는 이름·이메일만 본다** (backend/app/api/search.py:120). 공고명으로
  /// 찾으려면 [postingId] 로 좁혀야 한다 — 웹도 공고 검색을 그렇게 처리한다.
  ///
  /// 커서(`next_cursor`)도 있지만 **`offset` 을 쓴다** — 웹과 같고, "더 보기" 로
  /// 이어 붙이기에도 이쪽이 단순하다.
  ///
  /// [total] 은 `with_total` 을 켜야 온다. 화면이 "48명" 을 적어야 해서 켠다.
  Future<({List<Applicant> items, int? total})> search({
    String? query,
    Stage? stage,
    int? postingId,
    int limit = 30,
    int offset = 0,
  }) async {
    final json = await _client.get(
      Endpoints.applicationSearch(
        query: query,
        stage: stage?.value,
        postingId: postingId,
        limit: limit,
        offset: offset,
      ),
    );

    return (
      items: [
        for (final item in (json['items'] as List? ?? const []))
          ApplicantJson.fromSearchJson(item as Map<String, dynamic>),
      ],
      total: json['total'] as int?,
    );
  }

  /// 단계 변경 — `PATCH /applications/{id}/stage` (D3).
  ///
  /// 서버가 한 트랜잭션에서 **단계 · 이력 · 메일 큐**를 함께 처리한다. 앱이
  /// 이력을 따로 만들 필요가 없고, 성공하면 상세를 다시 받아 늘어난 줄을 본다.
  ///
  /// [reason] 은 불합격일 때 **필수**다(D8). 서버가 사유 없는 불합격을 막지만
  /// 화면에서도 먼저 막는다 — 422 를 받고 나서 알려 주면 한 번 헛걸음이다.
  ///
  /// 권한으로 막지 않는다(ADR-0017) — 로그인했으면 누구나 바꾸고, 누가 바꿨는지는
  /// 이력에 남는다.
  Future<void> changeStage(int id, Stage to, {String? reason}) => _client.patch(
    Endpoints.applicationStage(id),
    body: {'to_stage': to.value, 'reason': ?reason},
  );

  /// 메모 쓰기 — `POST /applications/{id}/notes`.
  ///
  /// 서버가 작성자를 토큰에서 읽는다. 앱이 누구인지 보내지 않는다.
  /// 응답에 `author_name` 이 들어 있어 목록을 다시 받지 않고 바로 끼워 넣을 수
  /// 있지만, **다시 받는 쪽을 택했다** — 그 사이 남이 쓴 메모가 있으면
  /// 내 것만 늘고 남의 것은 안 보이는 화면이 된다.
  ///
  /// 빈 본문은 서버가 422 로 막는다. 화면에서도 먼저 막는다.
  Future<void> addNote(int id, String body) =>
      _client.post(Endpoints.applicationNotes(id), body: {'body': body});

  /// 한 지원자의 평가 목록 — `GET /applications/{id}/evaluations`.
  ///
  /// 상세(`detail`)도 평가를 함께 주지만 평가 화면은 이쪽을 따로 부른다:
  /// 평가를 쓰고 나서 **평가만** 다시 받으면 되는데, 상세를 통째로 다시 받으면
  /// 첨부·메모·이력까지 딸려 온다.
  Future<EvaluationSummary> evaluations(int id) async {
    final json = await _client.get(Endpoints.applicationEvaluations(id));
    final items = (json['items'] as List<dynamic>? ?? const []);
    return EvaluationSummary(
      items: [
        for (final item in items)
          EvaluationJson.fromJson(
            item as Map<String, dynamic>,
            applicationId: id,
          ),
      ],
    );
  }

  /// 평가 쓰기 — `POST /applications/{id}/evaluations`.
  ///
  /// 작성자는 서버가 토큰에서 읽는다. 점수는 1~5 고 서버도 다시 검사한다.
  /// **`member` 는 자기에게 배정된 지원자만 쓸 수 있다** — 아니면 403 이 온다
  /// (`assert_can_evaluate`, ADR-0017). admin 은 무제한.
  Future<void> addEvaluation(int id, {required int score, String? comment}) =>
      _client.post(
        Endpoints.applicationEvaluations(id),
        // 빈 코멘트는 `null` 로 보낸다 — 웹과 같다. 빈 문자열을 저장하면
        // "코멘트를 안 썼다" 와 "빈 줄을 썼다" 가 구별되지 않는다
        body: {'score': score, 'comment': comment},
      );

  /// 첨부 파일 열기용 주소 — `GET /files/{id}/presign-download`.
  ///
  /// S3 가 서명한 임시 URL 이라 **유효 시간이 있다**(`expires_in`). 미리 받아
  /// 두면 누를 때쯤 만료되므로 **누를 때마다 새로 받는다.**
  ///
  /// 앱은 이 주소를 브라우저로 넘기기만 한다 — 앱 안에서 보려면 PDF 렌더러가
  /// 또 필요하고 이미지·docx 는 각각 다르다. 웹도 그냥 연다.
  Future<({String url, String filename})> fileDownloadUrl(int fileId) async {
    final json = await _client.get(Endpoints.fileDownload(fileId));
    return (
      url: json['download_url'] as String,
      filename: json['filename'] as String? ?? '',
    );
  }

  /// 메일 프리필 — `GET /applications/{id}/emails/preview?stage=`.
  ///
  /// 제목·본문에 든 `{지원자명}` 같은 자리는 **서버가 채워서 준다.** 앱이
  /// 채우면 미리보기와 실제로 나가는 것이 갈린다.
  Future<({String subject, String body})> mailPreview(
    int id,
    String stage,
  ) async {
    final json = await _client.get(
      Endpoints.applicationEmailPreview(id, stage),
    );
    return (
      subject: json['subject'] as String? ?? '',
      body: json['body'] as String? ?? '',
    );
  }

  /// 메일 발송 — `POST /applications/{id}/emails`.
  ///
  /// **받는 사람을 보내지 않는다.** 서버가 `application.email` 로 고정하므로
  /// 주소를 잘못 넣어 엉뚱한 사람에게 갈 경로가 아예 없다.
  ///
  /// 큐에 쌓이는 것이 아니라 **SES 로 실제 발송된다**(`app/worker.py`).
  /// 이 앱에서 유일하게 되돌릴 수 없는 동작이라 화면이 확인을 한 번 더 받는다.
  Future<void> sendMail(
    int id, {
    required String subject,
    required String body,
  }) => _client.post(
    Endpoints.applicationEmails(id),
    body: {'subject': subject, 'body': body},
  );

  /// 내 평가 고치기 — `PATCH /evaluations/{id}`.
  ///
  /// **같은 사람이 또 평가하면 새로 만들지 않고 이걸 부른다**(2026-09-03 결정).
  /// 서버도 웹도 중복을 막지 않아 그냥 POST 하면 한 사람이 여러 줄을 남기고
  /// **평균과 "n명이 평가함" 이 둘 다 틀어진다**. 서버에 이미 "내가 쓴 것만
  /// 고칠 수 있다" 는 검사가 있는데(`evaluator_id != user.id`) 웹이 안 쓰고
  /// 있었다 — 앱이 먼저 쓴다.
  Future<void> updateEvaluation(
    int evaluationId, {
    required int score,
    String? comment,
  }) => _client.patch(
    Endpoints.evaluation(evaluationId),
    body: {'score': score, 'comment': comment},
  );
}
