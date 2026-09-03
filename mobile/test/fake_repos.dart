// 테스트용 가짜 저장소 — 네트워크를 타지 않는다.
//
// 큐 8 로 화면이 서버에서 받아 오기 시작했다. 화면 테스트가 그대로면 매번
// 실서버에 붙으려 한다. 여기서 **기존 목데이터를 그대로 돌려주어**, 화면
// 테스트가 큐 8 전과 같은 값을 보게 한다 — 화면 규칙을 보는 테스트가
// 데이터가 바뀌었다고 깨질 이유가 없다.

import 'package:arda/data/mock_data.dart';
import 'package:arda/data/applicant_repository.dart';
import 'package:arda/data/posting_repository.dart';
import 'package:arda/models/applicant.dart';
import 'package:arda/models/evaluation.dart';
import 'package:arda/models/job_posting.dart';

class FakePostingRepository implements PostingRepository {
  FakePostingRepository({
    this.postings,
    this.error,
    this.delay = Duration.zero,
    this.createError,
    this.createDelay = Duration.zero,
  });

  /// 안 주면 목데이터 그대로
  final List<JobPosting>? postings;

  /// 주면 목록 요청이 이걸로 실패한다 — 오류 상태를 볼 때
  final Object? error;

  /// 로딩 상태를 볼 수 있게 늦춘다
  final Duration delay;

  /// 주면 등록이 이걸로 실패한다
  final Object? createError;

  /// 보내는 중 잠금을 볼 수 있게 늦춘다
  final Duration createDelay;

  /// 몇 번 받아 왔는지 — 등록 뒤 목록이 새로 오는지 이걸로 본다
  int listCalls = 0;

  /// 등록으로 보낸 값 (큐 8 3단계)
  String? createdTitle;
  PostingStatus? createdStatus;
  DateTime? createdDeadline;

  /// 수정으로 보낸 값 (2026-09-03)
  int? updatedId;
  String? updatedTitle;
  PostingStatus? updatedStatus;
  DateTime? updatedDeadline;

  /// 마감일을 실제로 보냈는가 — 안 보내는 것과 `null` 을 보내는 것이 다르다
  bool? updatedChangeDeadline;

  @override
  Future<List<PostingWithCounts>> list() async {
    listCalls++;
    if (delay > Duration.zero) await Future<void>.delayed(delay);
    if (error != null) throw error!;

    final items = postings ?? mockPostings;
    return [
      for (final p in items)
        PostingWithCounts(posting: p, counts: postingCounts(p.id)),
    ];
  }

  @override
  Future<JobPosting> create({
    required String title,
    required PostingStatus status,
    DateTime? deadline,
  }) async {
    createdTitle = title;
    createdStatus = status;
    createdDeadline = deadline;

    if (createDelay > Duration.zero) await Future<void>.delayed(createDelay);
    if (createError != null) throw createError!;

    // 서버가 돌려주는 것과 같은 모양 — id 는 서버가 매긴다
    return JobPosting(
      id: 900,
      title: title,
      status: status,
      deadline: deadline,
    );
  }

  @override
  Future<JobPosting> update(
    int id, {
    required String title,
    required PostingStatus status,
    required bool changeDeadline,
    DateTime? deadline,
  }) async {
    updatedId = id;
    updatedTitle = title;
    updatedStatus = status;
    updatedChangeDeadline = changeDeadline;
    updatedDeadline = deadline;

    if (createDelay > Duration.zero) await Future<void>.delayed(createDelay);
    if (createError != null) throw createError!;

    return JobPosting(
      id: id,
      title: title,
      status: status,
      // 안 보냈으면 서버는 원래 값을 그대로 둔다 — 원본에서 찾아 돌려준다
      deadline: changeDeadline
          ? deadline
          : (postings ?? mockPostings)
                .where((p) => p.id == id)
                .firstOrNull
                ?.deadline,
    );
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

/// 지원자 목록 — 목데이터를 그대로 돌려준다.
class FakeApplicantRepository implements ApplicantRepository {
  FakeApplicantRepository({
    this.applicants,
    this.error,
    this.delay = Duration.zero,
    this.evaluationSummary,
    this.writeError,
    this.mailPreviewText,
  });

  final List<Applicant>? applicants;
  final Object? error;
  final Duration delay;

  /// 평가 목록을 직접 주고 싶을 때. 안 주면 목데이터 (2026-09-03)
  final EvaluationSummary? evaluationSummary;

  /// 주면 평가 쓰기·고치기·메일 발송이 이걸로 실패한다
  final Object? writeError;

  /// 메일 프리필로 돌려줄 (제목, 본문). 안 주면 기본값 (2026-09-03)
  final (String, String)? mailPreviewText;

  /// 메일 발송으로 보낸 값 — **받는 사람은 안 보낸다**(서버가 고정한다)
  String? sentSubject;
  String? sentBody;
  int mailsSent = 0;

  /// 평가 쓰기로 보낸 값
  int? addedScore;
  String? addedComment;

  /// 평가 고치기로 보낸 값 — **id 가 들어오면 새로 만들지 않았다는 뜻**
  int? updatedEvaluationId;
  int? updatedScore;
  String? updatedComment;

  @override
  Future<EvaluationSummary> evaluations(int id) async {
    if (delay > Duration.zero) await Future<void>.delayed(delay);
    if (error != null) throw error!;

    return evaluationSummary ??
        mockEvaluations[id] ??
        const EvaluationSummary(items: []);
  }

  @override
  Future<void> addEvaluation(
    int id, {
    required int score,
    String? comment,
  }) async {
    addedScore = score;
    addedComment = comment;
    if (writeError != null) throw writeError!;
  }

  @override
  Future<void> updateEvaluation(
    int evaluationId, {
    required int score,
    String? comment,
  }) async {
    updatedEvaluationId = evaluationId;
    updatedScore = score;
    updatedComment = comment;
    if (writeError != null) throw writeError!;
  }

  @override
  Future<({String subject, String body})> mailPreview(
    int id,
    String stage,
  ) async {
    if (delay > Duration.zero) await Future<void>.delayed(delay);
    if (error != null) throw error!;

    final t = mailPreviewText;
    return t == null
        ? (subject: '[아르다] 지원서가 접수되었습니다', body: '홍길동 님, 안녕하세요.')
        : (subject: t.$1, body: t.$2);
  }

  @override
  Future<void> sendMail(
    int id, {
    required String subject,
    required String body,
  }) async {
    mailsSent++;
    sentSubject = subject;
    sentBody = body;
    if (writeError != null) throw writeError!;
  }

  @override
  Future<List<Applicant>> byPosting(int postingId) async {
    if (delay > Duration.zero) await Future<void>.delayed(delay);
    if (error != null) throw error!;

    return applicants ??
        mockApplicants.where((a) => a.jobPostingId == postingId).toList();
  }

  /// 상세 — 목데이터를 조립해 돌려준다. 서버가 한 번에 주는 것과 같은 모양이다
  @override
  Future<ApplicantDetail> detail(int id) async {
    if (delay > Duration.zero) await Future<void>.delayed(delay);
    if (error != null) throw error!;

    final a = (applicants ?? mockApplicants).firstWhere((x) => x.id == id);
    return ApplicantDetail(
      applicant: a,
      stageHistory: mockStageHistory[id] ?? const [],
      evaluations: mockEvaluations[id]?.items ?? const [],
      notes: mockNotes[id] ?? const [],
      files: mockFiles[id] ?? const [],
      avgScore: mockEvaluations[id]?.avgScore,
    );
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}
