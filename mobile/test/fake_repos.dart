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
import 'package:arda/models/team_member.dart';
import 'package:arda/models/mail_template.dart';
import 'package:arda/models/interview.dart';
import 'package:arda/models/availability.dart';
import 'package:arda/data/settings_repository.dart';
import 'package:arda/data/schedule_repository.dart';
import 'package:arda/models/stage.dart';
import 'package:arda/data/dashboard_repository.dart';
import 'package:arda/data/agent_repository.dart';

class FakePostingRepository implements PostingRepository {
  FakePostingRepository({
    this.postings,
    this.error,
    this.delay = Duration.zero,
    this.createError,
    this.createDelay = Duration.zero,
    this.deleteError,
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

  /// 삭제로 보낸 id (2026-09-03). null 이면 삭제를 안 불렀다 —
  /// 확인 시트를 취소했을 때 이게 null 인지로 본다
  int? deletedId;

  /// 주면 삭제가 이걸로 실패한다 — 지원자 있는 공고의 409
  final Object? deleteError;

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
  Future<void> delete(int id) async {
    deletedId = id;

    if (createDelay > Duration.zero) await Future<void>.delayed(createDelay);
    if (deleteError != null) throw deleteError!;
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
    this.fileUrl,
    this.fileError,
    this.searchResults,
    this.searchTotal,
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

  /// 첨부 열기가 돌려줄 주소. 안 주면 기본값 (2026-09-03)
  final String? fileUrl;

  /// 주면 첨부 주소 받기만 이걸로 실패한다 — 상세는 정상인 상황
  final Object? fileError;

  /// 통합 검색이 돌려줄 것. 안 주면 목데이터를 조건대로 거른다 (큐 8 4단계)
  final List<Applicant>? searchResults;
  final int? searchTotal;

  /// 검색으로 들어온 조건 — 서버로 뭘 보냈는지 본다
  String? searchedQuery;
  Stage? searchedStage;
  int? searchedPostingId;
  int? searchedOffset;
  int searchCalls = 0;

  /// 어느 파일의 주소를 물었는지
  int? askedFileId;

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
  Future<({List<Applicant> items, int? total})> search({
    String? query,
    Stage? stage,
    int? postingId,
    int limit = 30,
    int offset = 0,
  }) async {
    searchCalls++;
    searchedQuery = query;
    searchedStage = stage;
    searchedPostingId = postingId;
    searchedOffset = offset;

    if (delay > Duration.zero) await Future<void>.delayed(delay);
    if (error != null) throw error!;

    if (searchResults != null) {
      final page = searchResults!.skip(offset).take(limit).toList();
      return (items: page, total: searchTotal ?? searchResults!.length);
    }

    // 목데이터를 서버처럼 거른다 — 이름·이메일을 보고 단계로 좁힌다
    final q = (query ?? '').trim().toLowerCase();
    final all = (applicants ?? mockApplicants).where((a) {
      if (stage != null && a.currentStage != stage) return false;
      if (postingId != null && a.jobPostingId != postingId) return false;
      if (q.isEmpty) return true;
      return a.name.toLowerCase().contains(q) ||
          a.email.toLowerCase().contains(q);
    }).toList();

    return (items: all.skip(offset).take(limit).toList(), total: all.length);
  }

  @override
  Future<({String url, String filename})> fileDownloadUrl(int fileId) async {
    askedFileId = fileId;
    if (delay > Duration.zero) await Future<void>.delayed(delay);
    // 상세는 정상인데 첨부 주소만 실패하는 경우를 따로 만든다
    if (fileError != null) throw fileError!;
    if (error != null) throw error!;

    return (
      url: fileUrl ?? 'https://example.com/signed/$fileId.pdf',
      filename: 'x.pdf',
    );
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
      emails: mockEmailLogs[id] ?? const [],
      files: mockFiles[id] ?? const [],
      avgScore: mockEvaluations[id]?.avgScore,
    );
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

/// 면접 일정 — 목데이터를 그대로 돌려준다 (큐 8 4단계, 2026-09-03).
class FakeScheduleRepository implements ScheduleRepository {
  FakeScheduleRepository({this.items, this.error, this.delay = Duration.zero});

  /// 안 주면 목데이터에서 그 주를 뽑아 준다
  final List<Interview>? items;
  final Object? error;
  final Duration delay;

  @override
  Future<List<Interview>> between(DateTime from, DateTime to) async {
    if (delay > Duration.zero) await Future<void>.delayed(delay);
    if (error != null) throw error!;

    if (items != null) return items!;
    // 목데이터의 주간 묶음을 한 줄로 편다 — 서버가 주는 모양과 같다
    return [for (final list in mockInterviewsInWeek(from).values) ...list];
  }

  @override
  Future<List<Interview>> week(DateTime anchor) => between(anchor, anchor);

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

/// 설정 세 탭이 읽는 것들 — 목데이터 그대로.
class FakeSettingsRepository implements SettingsRepository {
  FakeSettingsRepository({
    this.members,
    this.mailTemplates,
    this.slots,
    this.error,
  });

  final List<TeamMember>? members;
  final List<MailTemplate>? mailTemplates;
  final List<Availability>? slots;
  final Object? error;

  @override
  Future<List<TeamMember>> users() async {
    if (error != null) throw error!;
    return members ?? mockTeam;
  }

  @override
  Future<List<MailTemplate>> templates() async {
    if (error != null) throw error!;
    return mailTemplates ??
        const [
          MailTemplate(
            stage: 'applied',
            subject: '[아르다] 지원서가 접수되었습니다',
            body: '홍길동 님, 안녕하세요.',
            isDefault: true,
          ),
          MailTemplate(
            stage: 'interview',
            subject: '[아르다] 면접 안내',
            body: '면접 일시: …',
            isDefault: false,
            updatedByName: '김채용',
          ),
        ];
  }

  @override
  Future<List<Availability>> availability(int userId) async {
    if (error != null) throw error!;
    return slots ?? const [];
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

/// 대시보드 — 목데이터로 같은 모양을 만들어 준다 (큐 8 4단계, 2026-09-03).
class FakeDashboardRepository implements DashboardRepository {
  FakeDashboardRepository({
    this.data,
    this.error,
    this.delay = Duration.zero,
    this.assigned,
  });

  final DashboardData? data;
  final Object? error;
  final Duration delay;

  /// 평가 대기 큐가 받는 배정 id 들. 안 주면 목데이터의 대기 인원
  final List<int>? assigned;

  @override
  Future<DashboardData> load({required int userId, DateTime? today}) async {
    if (delay > Duration.zero) await Future<void>.delayed(delay);
    if (error != null) throw error!;
    if (data != null) return data!;

    final day = today ?? DateTime.now();
    final open = [
      for (final p in mockPostings)
        if (p.status == PostingStatus.open)
          PostingWithCounts(
            posting: p,
            counts: postingCounts(p.id),
            applicants: mockApplicants
                .where((a) => a.jobPostingId == p.id)
                .toList(),
          ),
    ];

    return DashboardData(
      todayInterviews: mockInterviewsOn(day),
      reviewWaiting: mockReviewQueueCount,
      openPostings: open,
      stageCounts: mockOpenStageCounts,
      applicantsByStage: {
        for (final s in Stage.values)
          s: [
            for (final p in open)
              ...p.applicants.where((a) => a.currentStage == s),
          ],
      },
      scheduleStatus: {
        for (final e in mockScheduleStatus.entries)
          e.key: ScheduleChip(
            e.value,
            // 목데이터의 확정은 그날 면접 시각을 쓴다 — 서버의
            // `confirmed_slot` 자리다
            confirmedAt: e.value == ScheduleStatus.confirmed
                ? mockInterviewFor(e.key, day)?.startAt
                : null,
          ),
      },
    );
  }

  @override
  Future<List<int>> assignedIds(int userId) async {
    if (error != null) throw error!;
    return assigned ??
        [
          for (final a in mockApplicants)
            if ((a.currentStage == Stage.screening ||
                    a.currentStage == Stage.interview) &&
                !mockEvaluations.containsKey(a.id))
              a.id,
        ];
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

/// 아르 — 정해 준 답을 돌려준다 (큐 8 5단계, 2026-09-03).
class FakeAgentRepository implements AgentRepository {
  FakeAgentRepository({
    this.reply,
    this.error,
    this.confirmOk = true,
    this.delay = Duration.zero,
  });

  final ArReply? reply;
  final Object? error;
  final bool confirmOk;
  final Duration delay;

  /// 서버로 보낸 것 — 이력이 쌓여 가는지 이걸로 본다
  String? sentMessage;
  List<ArHistoryEntry> sentHistory = const [];
  ArPendingAction? confirmed;
  int chatCalls = 0;

  @override
  Future<ArReply> chat(String message, List<ArHistoryEntry> history) async {
    chatCalls++;
    sentMessage = message;
    // 화면이 들고 있는 목록을 그대로 넘기므로 복사해 둔다
    sentHistory = [...history];

    if (delay > Duration.zero) await Future<void>.delayed(delay);
    if (error != null) throw error!;

    return reply ?? const ArReply(text: '면접 단계에 2명 있습니다.');
  }

  @override
  Future<bool> confirm(ArPendingAction action) async {
    confirmed = action;
    if (delay > Duration.zero) await Future<void>.delayed(delay);
    if (error != null) throw error!;
    return confirmOk;
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}
