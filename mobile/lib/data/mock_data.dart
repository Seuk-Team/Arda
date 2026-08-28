/// 목데이터 — `frontend/mockups/mockup-mobile.html` 의 지원자 6명을 그대로 옮긴 것.
///
/// **여기 있는 사람과 값은 목업에서 왔다. 새로 지어내지 않았다.**
/// 목업과 나란히 놓고 같은 제품으로 보이는지 확인하는 것이 큐 6번 완료 기준이라,
/// 임의로 늘리거나 바꾸면 대조가 안 된다.
///
/// 실제 API 연동은 큐 8번이다. 그때 이 파일을 걷어내고 같은 모델을 API 응답으로 채운다.
library;

import '../models/applicant.dart';
import '../models/job_posting.dart';
import '../models/evaluation.dart';
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
  1 => stageCounts(
    mockApplicants.where((a) => a.jobPostingId == 1).toList(),
  ),
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
        comment: '문제 정의 → 측정 → 개선 순으로 설명이 또렷했습니다. '
            '대용량 처리 경험도 수치로 답변.',
        createdAt: DateTime(2026, 8, 24),
      ),
      Evaluation(
        id: 2,
        applicationId: 1,
        evaluatorName: '한소미',
        score: 4,
        comment: '기술 스택은 요건과 일치. 팀 협업 사례가 한 가지뿐이라 '
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
