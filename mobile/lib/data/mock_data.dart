/// 목데이터 — `frontend/mockups/mockup-mobile.html` 의 지원자 6명을 그대로 옮긴 것.
///
/// **여기 있는 사람과 값은 목업에서 왔다. 새로 지어내지 않았다.**
/// 목업과 나란히 놓고 같은 제품으로 보이는지 확인하는 것이 큐 6번 완료 기준이라,
/// 임의로 늘리거나 바꾸면 대조가 안 된다.
///
/// 실제 API 연동은 큐 8번이다. 그때 이 파일을 걷어내고 같은 모델을 API 응답으로 채운다.
library;

import '../models/app_user.dart';
import '../models/ar_message.dart';
import '../models/applicant.dart';
import '../models/job_posting.dart';
import '../models/evaluation.dart';
import '../models/interview.dart';
import '../models/stage.dart';
import '../models/stage_history.dart';

/// 목업 상단의 공고 + 시안 5번의 공고 리스트 3건.
///
/// 마감일은 고정 날짜라 D-day 표기는 실제 오늘 날짜에 따라 달라진다.
/// 시안의 `D-12` 를 그대로 박아 두면 계산이 맞는지 확인할 수 없어 날짜로 뒀다.
final mockPostings = <JobPosting>[
  JobPosting(
    id: 1,
    title: '백엔드 개발자 (신입)',
    status: PostingStatus.open,
    deadline: DateTime(2026, 9, 9),
  ),

  // 05-design §7 극단값 — 긴 공고명이 두 줄로 잘리는지 보는 카드다 (시안 5번)
  JobPosting(
    id: 2,
    title: '글로벌 커머스 플랫폼 백엔드 시스템 아키텍처 설계 및 대규모 트래픽 처리 담당자',
    status: PostingStatus.open,
    deadline: DateTime(2026, 9, 18),
  ),

  JobPosting(
    id: 3,
    title: '데이터 엔지니어',
    status: PostingStatus.closed,
    deadline: DateTime(2026, 2, 10),
  ),
];

/// 지원자 화면이 쓰는 기본 공고 (공고 리스트에서 고르기 전까지)
final mockPosting = mockPostings.first;

/// 목업 카드 6장. **순서도 목업 그대로**(최신 지원일 → 오래된 순).
final mockApplicants = <Applicant>[
  Applicant(
    id: 1,
    jobPostingId: 1,
    name: '김도현',
    email: 'dohyun.kim@example.com',
    education: 'OO대학교 컴퓨터공학과',
    careerYears: 2,
    skills: ['Python', 'FastAPI'],
    currentStage: Stage.interview,
    createdAt: DateTime(2026, 3, 12),
  ),

  // 05-design §7 극단값 — 긴 이름·태그 다수가 레이아웃을 깨뜨리는지 보는 카드다.
  // 목업이 일부러 넣어 둔 것이므로 지우지 말 것.
  Applicant(
    id: 2,
    jobPostingId: 1,
    name: '크리스토퍼 알렉산더 요한 반 데 베르그 주니어 3세',
    email: 'christopher.vandeberg@example.com',
    education: 'OO대학원 컴퓨터공학 석사',
    careerYears: 12,
    skills: ['Python', 'FastAPI', 'PostgreSQL', 'Docker', 'AWS', 'Kubernetes'],
    currentStage: Stage.interview,
    createdAt: DateTime(2026, 3, 12),
  ),

  Applicant(
    id: 3,
    jobPostingId: 1,
    name: '박지훈',
    email: 'jihoon.park@example.com',
    education: 'OO대학교 컴퓨터공학과 졸업',
    careerYears: 0,
    skills: ['Python', 'FastAPI'],
    currentStage: Stage.applied,
    createdAt: DateTime(2026, 3, 11),
  ),

  Applicant(
    id: 4,
    jobPostingId: 1,
    name: '정우진',
    email: 'woojin.jung@example.com',
    education: 'OO대학교 소프트웨어학과',
    careerYears: 1,
    skills: ['Python', 'AWS', 'Docker'],
    currentStage: Stage.screening,
    createdAt: DateTime(2026, 3, 11),
  ),

  Applicant(
    id: 5,
    jobPostingId: 1,
    name: '윤하늘',
    email: 'haneul.yoon@example.com',
    education: '부트캠프 수료',
    careerYears: 1,
    skills: ['FastAPI', 'PostgreSQL'],
    currentStage: Stage.accepted,
    createdAt: DateTime(2026, 3, 10),
  ),

  Applicant(
    id: 6,
    jobPostingId: 1,
    name: '강민수',
    email: 'minsu.kang@example.com',
    education: 'OO대학교 전자공학과',
    careerYears: 0,
    skills: ['PHP'],
    currentStage: Stage.rejected,
    createdAt: DateTime(2026, 3, 9),
  ),
];

/// 단계별 인원 — 퍼널 바가 쓴다 (mockup.html `.funnel`).
Map<Stage, int> stageCounts(List<Applicant> applicants) {
  return {
    for (final stage in Stage.values)
      stage: applicants.where((a) => a.currentStage == stage).length,
  };
}

/// 공고별 단계 인원 — 공고 리스트 카드의 퍼널 막대가 쓴다.
///
/// 1번 공고는 실제 목데이터(6명)에서 세고, 나머지 둘은 시안 5번의 숫자를 옮겼다.
/// 지원자 목데이터는 1번 공고 것만 있다.
Map<Stage, int> postingCounts(int jobPostingId) => switch (jobPostingId) {
  1 => stageCounts(mockApplicants.where((a) => a.jobPostingId == 1).toList()),
  2 => const {
    Stage.applied: 9,
    Stage.screening: 7,
    Stage.interview: 4,
    Stage.accepted: 1,
    Stage.rejected: 1,
  },
  _ => const {
    Stage.applied: 120,
    Stage.screening: 210,
    Stage.interview: 340,
    Stage.accepted: 97,
    Stage.rejected: 130,
  },
};

/// 단계 이력 — 시안(2026-08-28) 2번의 김도현 예시를 그대로 옮겼다.
/// **최신이 위**로 오도록 정렬해 둔다.
final mockStageHistory = <int, List<StageHistory>>{
  1: [
    StageHistory(
      id: 4,
      applicationId: 1,
      fromStage: Stage.interview,
      toStage: Stage.accepted,
      changedByName: '김채용',
      mailQueued: true,
      createdAt: DateTime(2026, 8, 27, 14, 20),
    ),
    StageHistory(
      id: 3,
      applicationId: 1,
      fromStage: Stage.screening,
      toStage: Stage.interview,
      changedByName: '김채용',
      mailQueued: true,
      createdAt: DateTime(2026, 8, 24, 10, 5),
    ),
    StageHistory(
      id: 2,
      applicationId: 1,
      fromStage: Stage.applied,
      toStage: Stage.screening,
      changedByName: '이서연',
      mailQueued: false,
      createdAt: DateTime(2026, 8, 21, 9, 12),
    ),
    // from_stage 가 NULL — 최초 접수. changed_by 도 NULL(시스템)이다
    StageHistory(
      id: 1,
      applicationId: 1,
      toStage: Stage.applied,
      mailQueued: false,
      createdAt: DateTime(2026, 8, 20, 22, 41),
    ),
  ],
};

/// 평가 — 시안 3번의 김도현 예시(3명, 평균 4.3)를 그대로 옮겼다.
final mockEvaluations = <int, EvaluationSummary>{
  1: EvaluationSummary(
    items: [
      Evaluation(
        id: 1,
        applicationId: 1,
        evaluatorName: '이지훈',
        score: 5,
        comment:
            '문제 정의 → 측정 → 개선 순으로 설명이 또렷했습니다. '
            '대용량 처리 경험도 수치로 답변.',
        createdAt: DateTime(2026, 8, 24),
      ),
      Evaluation(
        id: 2,
        applicationId: 1,
        evaluatorName: '한소미',
        score: 4,
        comment:
            '기술 스택은 요건과 일치. 팀 협업 사례가 한 가지뿐이라 '
            '2차에서 더 볼 필요가 있습니다.',
        createdAt: DateTime(2026, 8, 24),
      ),
      Evaluation(
        id: 3,
        applicationId: 1,
        evaluatorName: '김채용',
        score: 4,
        comment: '서류 기준 적합. 면접에서 아키텍처 설계 경험을 확인하면 좋겠습니다.',
        createdAt: DateTime(2026, 8, 23),
      ),
    ],
  ),
};

/// 확정된 면접 — `GET /schedules` (status=confirmed) 가 줄 모양 그대로.
///
/// 대시보드 "오늘 면접"이 오늘 날짜를 기준으로 묻기 때문에 고정 날짜를 박지 않고
/// 받은 날에 얹는다. 시각(14:00 · 16:30)만 고정이다 — 날짜를 박아 두면 내일
/// 열었을 때 카드가 비어 버려 화면을 확인할 수 없다.
///
/// 사람은 [mockApplicants] 중 면접 단계인 둘을 그대로 쓴다. 둘째는 긴 이름
/// 스트레스 케이스라 한 줄 말줄임이 실제로 도는지 여기서 같이 보인다.
/// 목데이터에서 "나". 캘린더의 "내 면접만" 필터가 이 이름으로 거른다 —
/// API 연동(큐 8) 때 로그인한 사용자 id 기준으로 바뀐다.
const mockMyName = '김민아';

List<Interview> mockInterviewsOn(DateTime day) {
  Interview at(
    int hour,
    int minute,
    Applicant who, {
    required int proposalId,
    String interviewer = mockMyName,
  }) {
    final start = DateTime(day.year, day.month, day.day, hour, minute);
    return Interview(
      proposalId: proposalId,
      applicationId: who.id,
      applicantName: who.name,
      postingTitle: mockPostings
          .firstWhere((p) => p.id == who.jobPostingId)
          .title,
      interviewerId: interviewer == mockMyName ? 1 : 2,
      interviewerName: interviewer,
      startAt: start,
      // 슬롯 기본 길이 60분 (ProposalCreate.slot_minutes 기본값)
      endAt: start.add(const Duration(minutes: 60)),
    );
  }

  final interviewees = mockApplicants
      .where((a) => a.currentStage == Stage.interview)
      .toList();

  // 요일마다 다르게 잡아 둔다 — 매일 같은 건수면 주간 스트립이 밋밋해서
  // 건수 표기가 실제로 도는지 확인이 안 된다. 주말은 비운다.
  return switch (day.weekday) {
    DateTime.tuesday => [
      at(14, 0, interviewees[0], proposalId: 1),
      at(16, 30, interviewees[1], proposalId: 2),
    ],
    // 남의 면접 — 캘린더 "내 면접만" 이 실제로 무언가를 거르는지 화면에서
    // 확인하려면 내 것이 아닌 건이 있어야 한다. 전부 내 것이면 토글이
    // 아무 일도 안 해서 고장으로 보인다
    DateTime.thursday => [
      at(11, 0, interviewees[0], proposalId: 3, interviewer: '진수택'),
    ],
    DateTime.friday => [
      at(10, 0, interviewees[1], proposalId: 4),
      // 같은 시각 두 건 — 05-design 캘린더 절의 "같은 시간대는 슬롯으로 묶는다"
      at(15, 0, interviewees[0], proposalId: 5),
      at(15, 0, interviewees[1], proposalId: 6, interviewer: '진수택'),
    ],
    _ => const [],
  };
}

/// 그 날이 든 한 주의 일요일 0시. 주간 스트립이 일요일부터 그린다.
DateTime startOfWeek(DateTime day) {
  final date = DateTime(day.year, day.month, day.day);
  // DateTime.weekday 는 월=1…일=7 이다. 일요일을 0 으로 돌린다
  return date.subtract(Duration(days: date.weekday % 7));
}

/// 그 주 7일의 확정 면접 — 주간 스트립이 날짜별 건수를 여기서 센다.
Map<DateTime, List<Interview>> mockInterviewsInWeek(DateTime anyDayInWeek) {
  final sunday = startOfWeek(anyDayInWeek);
  return {
    for (var i = 0; i < 7; i++)
      sunday.add(Duration(days: i)): mockInterviewsOn(
        sunday.add(Duration(days: i)),
      ),
  };
}

/// 내 리뷰 대기 — 평가 기록이 아직 없는 서류·면접 단계 지원자 수.
///
/// 숫자를 새로 지어내지 않고 [mockApplicants] 와 [mockEvaluations] 에서 센다.
/// 실제로는 "나에게 배정된" 것만 세야 하지만(E3 배정), 목데이터에 배정이 없어
/// 단계로 대신한다 — API 연동(큐 8) 때 배정 기준으로 바뀐다.
int get mockReviewQueueCount => mockApplicants
    .where(
      (a) =>
          (a.currentStage == Stage.screening ||
              a.currentStage == Stage.interview) &&
          !mockEvaluations.containsKey(a.id),
    )
    .length;

/// 진행중인 공고만.
List<JobPosting> get mockOpenPostings =>
    mockPostings.where((p) => p.status == PostingStatus.open).toList();

/// 대시보드 전형 현황 레일 — **진행중 공고의** 단계별 인원 합.
///
/// 마감된 공고까지 더하면 끝난 채용이 레일을 다 먹는다. 대시보드가 답하는 질문은
/// "지금 어떻게 돌아가고 있나"라서 진행중만 센다.
Map<Stage, int> get mockOpenStageCounts {
  final totals = {for (final stage in Stage.values) stage: 0};
  for (final posting in mockOpenPostings) {
    postingCounts(
      posting.id,
    ).forEach((stage, n) => totals[stage] = totals[stage]! + n);
  }
  return totals;
}

/// 로그인한 사용자 — 목데이터. API 연동(큐 7 JWT) 때 토큰의 주인으로 바뀐다.
const mockUser = AppUser(
  id: 1,
  email: 'minah@arda.team',
  name: '김민아',
  role: UserRole.member,
);

/// 아르 대화 목데이터 — 화면 확인용. 실제 `POST /agent/chat` 연동은 큐 8이다.
///
/// **사람과 숫자를 지어내지 않았다.** 제안 대상은 [mockApplicants] 에서 서류 검토
/// 단계인 사람을 그대로 집어 온다 — 화면에 뜬 이름이 다른 화면의 목록과 어긋나면
/// 데모에서 바로 들킨다.
final mockArThread = <ArMessage>[
  // 배포판(2026-09-01)의 첫 인사 그대로. 앱이 다른 말을 하면 같은 아르로 안 읽힌다
  const ArMessage(
    speaker: ArSpeaker.ar,
    text: '안녕하세요! 저는 아르예요.\n지원자 검색, 단계 변경, 면접 일정 같은 채용 업무를 도와드려요.',
  ),
  const ArMessage(speaker: ArSpeaker.me, text: '백엔드 공고에서 면접 볼 만한 사람 골라줘'),
  ArMessage(
    speaker: ArSpeaker.ar,
    text:
        '서류 검토 단계에서 ${_screeningApplicants.length}명을 찾았어요. '
        '면접으로 옮길까요?',
    pendingAction: PendingAction(
      // 실제 도구 이름은 backend/app/agent/tools/write.py 를 따른다
      toolName: 'change_stage',
      description: '아래 지원자를 면접 단계로 옮깁니다. 안내 메일이 나갑니다.',
      confirmLabel: '면접으로 옮기기',
      targets: [
        for (final a in _screeningApplicants)
          PendingTarget(
            name: a.name,
            stageLabel: a.currentStage.label,
            meta: a.careerLabel,
          ),
      ],
    ),
  ),
];

List<Applicant> get _screeningApplicants =>
    mockApplicants.where((a) => a.currentStage == Stage.screening).toList();

/// 대시보드 지원자 현황이 쓰는 단계별 목록 — **진행중 공고의** 지원자만.
///
/// 05-design §0.5 는 대시보드를 진행 상황을 보는 자리로 정의한다. 마감된 공고까지
/// 넣으면 끝난 채용이 목록을 다 먹는다. [mockOpenStageCounts] 와 같은 기준이다.
///
/// 목데이터에 지원자가 있는 공고는 1번뿐이라 2번 공고의 인원은 숫자만 있고
/// 사람이 없다 — 그래서 카운트는 [mockOpenStageCounts] 를, 이름은 여기를 쓴다.
List<Applicant> mockApplicantsIn(Stage stage) => mockApplicants
    .where(
      (a) =>
          a.currentStage == stage &&
          mockOpenPostings.any((p) => p.id == a.jobPostingId),
    )
    .toList();

/// 그 지원자의 확정 면접 — 면접 단계 행의 시각 칩이 쓴다.
/// 없으면 null 이고, 화면은 "일정 없음" 으로 적는다(웹과 같은 문구).
Interview? mockInterviewFor(int applicationId, DateTime around) {
  for (final items in mockInterviewsInWeek(around).values) {
    for (final interview in items) {
      if (interview.applicationId == applicationId) return interview;
    }
  }
  return null;
}

/// 설정 · 사용자·권한 탭이 쓰는 팀 목록.
///
/// 배포판 웹의 목록(`frontend/app/src/pages/Settings.tsx`)을 그대로 옮겼다 —
/// 앱이 다른 사람을 보여 주면 같은 시스템으로 안 읽힌다.
class TeamMember {
  const TeamMember({
    required this.name,
    required this.email,
    required this.role,
    required this.active,
  });

  final String name;
  final String email;
  final UserRole role;

  /// `users` 에 활성 플래그가 없어 화면 표시용으로만 둔다 — API 연동 때 정리한다
  final bool active;
}

const mockTeam = <TeamMember>[
  TeamMember(name: '김채용', email: 'admin@arda.com', role: UserRole.admin, active: true),
  TeamMember(name: '이서연', email: 'recruiter1@arda.com', role: UserRole.member, active: true),
  TeamMember(name: '박정호', email: 'reviewer1@arda.com', role: UserRole.member, active: true),
  TeamMember(name: '최민지', email: 'recruiter2@arda.com', role: UserRole.member, active: true),
  TeamMember(name: '한도윤', email: 'reviewer2@arda.com', role: UserRole.member, active: false),
];
