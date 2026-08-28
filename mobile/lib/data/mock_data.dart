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
import '../models/stage.dart';

/// 목업 상단의 공고 — "백엔드 개발자 (신입) · 마감 D-12"
///
/// 마감일은 고정 날짜라 D-day 표기는 실제 오늘 날짜에 따라 달라진다.
/// 목업의 `D-12` 를 그대로 박아 두면 계산이 맞는지 확인할 수 없어 날짜로 뒀다.
final mockPosting = JobPosting(
  id: 1,
  title: '백엔드 개발자 (신입)',
  deadline: DateTime(2026, 9, 9),
);

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
