/// 대시보드 (홈 탭) — 앱 UI 초안(2026-09-01).
///
/// 05-design §0.5 는 대시보드를 "요약 + 진입점"으로 정의한다. 다만 그 절이 그리는
/// 배치(숫자 카드 3장 → 지원자 현황 블록 → 캘린더 축소판 + 공고 퍼널 2열)는
/// 넓은 화면 기준이다. 375px 세로 한 줄로 옮기면 제일 안 급한 접수가 맨 위에 오고
/// 오늘 면접은 스크롤해야 나온다 — 넓은 화면은 한눈에 훑히지만 폰은 위에서부터
/// 읽으므로 순서가 곧 우선순위다. 그래서 급한 순으로 세운다:
///
///   오늘 면접 → 내 리뷰 대기 → 지원자 현황 → 진행중 공고
///
/// 조각 3~6: 오늘 면접 블록 · 조각 7: 내 리뷰 대기 · 조각 8: 지원자 현황 ·
/// 조각 9: 진행중 공고.
library;

import 'package:flutter/material.dart';

import '../data/mock_data.dart';
import '../models/applicant.dart';
import '../models/interview.dart';
import '../models/job_posting.dart';
import '../models/stage.dart';
import '../theme/tokens.dart';
import '../utils/format.dart';
import '../widgets/funnel_bar.dart';
import '../widgets/funnel_legend.dart';

class DashboardScreen extends StatelessWidget {
  const DashboardScreen({
    super.key,
    this.today,
    this.onOpenCalendar,
    this.onOpenReviews,
    this.onOpenApplicants,
    this.onOpenPostings,
  });

  /// 테스트가 날짜를 고정할 수 있게 열어 둔다. 비면 기기 오늘.
  final DateTime? today;

  /// 카드마다 이어지는 곳. 셸이 탭을 옮겨 준다 —
  /// 대시보드는 자기가 어느 탭에 앉아 있는지 몰라야 한다
  final VoidCallback? onOpenCalendar;
  final VoidCallback? onOpenReviews;
  final VoidCallback? onOpenApplicants;
  final VoidCallback? onOpenPostings;

  /// 05-design §0.5 대시보드 레일은 **접수~합격 4단**. 불합격은 레일에 없다
  static const railStages = [
    Stage.applied,
    Stage.screening,
    Stage.interview,
    Stage.accepted,
  ];

  @override
  Widget build(BuildContext context) {
    final day = today ?? DateTime.now();
    final interviews = mockInterviewsOn(day);
    final stageTotals = mockOpenStageCounts;
    final openPostings = mockOpenPostings;

    return ListView(
      // 05-design §3: 화면 여백은 --sp-4
      padding: const EdgeInsets.all(AppSpace.s4),
      children: [
        _Card(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              _CardHead(
                title: '오늘 면접',
                // §2 표기 통일: 날짜는 2026.09.02 형태. 건수는 사람이 아니라
                // 일정이므로 `2명`이 아니라 `2건`
                meta:
                    '${formatDate(day)} · ${formatItemCount(interviews.length)}',
              ),
              for (final interview in interviews) _InterviewRow(interview),
              _CardLink(label: '캘린더 →', onTap: onOpenCalendar),
            ],
          ),
        ),
        const SizedBox(height: AppSpace.s3),

        // ② 내 리뷰 대기 — 이 앱을 켜는 가장 큰 이유. 화면에서 유일하게 채운 버튼
        _Card(
          child: _ReviewQueue(
            count: mockReviewQueueCount,
            onTap: onOpenReviews,
          ),
        ),
        const SizedBox(height: AppSpace.s3),

        // ③ 지원자 현황 — 05-design §0.5 가 모바일에 요구하는 형태.
        //
        // 레일은 한눈에 보는 요약으로 위에 남기고, 그 아래에 단계별 목록을 편다:
        // 불합격 제외 4단계 · 단계당 [_perStage]명 + "외 n명 →" ·
        // 면접 행에는 확정 시각/제안 중 칩.
        //
        // **리스트/칸반 토글은 없다.** §9 "모바일은 칸반 금지 → 단계 탭 + 리스트",
        // §0.5 "칸반은 보기 전용 — 모바일(≤768px)은 §9 원칙대로 리스트만".
        _Card(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              _CardHead(
                title: '지원자 현황',
                meta: formatCount(
                  railStages.fold(0, (sum, s) => sum + (stageTotals[s] ?? 0)),
                ),
              ),
              const SizedBox(height: AppSpace.s3),
              FunnelBar(
                counts: stageTotals,
                stages: railStages,
                // §0.5: 0건 구간도 6px 남긴다 — 몇 단짜리인지가 늘 읽혀야 한다
                keepEmptySegments: true,
              ),
              const SizedBox(height: AppSpace.s3),
              FunnelLegend(counts: stageTotals, stages: railStages),
              for (final stage in railStages)
                _StageGroup(stage: stage, today: day),
              _CardLink(label: '전체 지원자 →', onTap: onOpenApplicants),
            ],
          ),
        ),
        const SizedBox(height: AppSpace.s3),

        // ④ 진행중 공고
        _Card(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              _CardHead(
                title: '진행중 공고',
                meta: formatItemCount(openPostings.length),
              ),
              for (final posting in openPostings)
                _PostingRow(posting: posting, today: day),
              _CardLink(label: '채용 공고 →', onTap: onOpenPostings),
            ],
          ),
        ),
      ],
    );
  }
}

/// 카드 오른쪽 아래로 빠지는 링크 — 이 블록이 어디로 이어지는지 알려 준다.
///
/// 05-design §1: 링크 글자는 `--leaf`(연두는 글자 대비가 모자란다).
/// §9: 터치 타깃 최소 44×44 — 글자 높이는 20 남짓이라 누를 자리를 44 로 넓힌다.
/// 좌우 여백은 두지 않는다 — 글자 오른쪽 끝이 카드 안쪽 선에 맞아야 위의
/// 날짜·건수와 같은 세로선에 선다.
class _CardLink extends StatelessWidget {
  const _CardLink({required this.label, this.onTap});

  final String label;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: Alignment.centerRight,
      child: Material(
        color: Colors.transparent,
        borderRadius: AppShape.ctl,
        clipBehavior: Clip.antiAlias,
        child: InkWell(
          onTap: onTap,
          // §5: 모바일은 hover 없음 전제 — press 만 정의한다
          highlightColor: AppColors.bgSunken,
          splashColor: AppColors.bgSunken,
          child: Container(
            constraints: const BoxConstraints(
              minHeight: AppLayout.minTouchTarget,
              minWidth: AppLayout.minTouchTarget,
            ),
            alignment: Alignment.centerRight,
            child: Text(
              label,
              softWrap: false,
              style: const TextStyle(
                fontFamily: AppType.fontFamily,
                fontSize: AppType.sm,
                fontWeight: AppType.wSemiBold,
                color: AppColors.leaf,
                // §2: 작은 글씨엔 그림자 금지
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// 05-design §4 카드 껍데기 — 흰 바탕 · radius 8 · 1px 테두리 · 옅은 카드 그림자.
/// 안쪽 여백은 §0.5 가 카드에 못 박은 `--sp-4`. 웹 `.card` 와 같은 규격이다.
///
/// 높이는 내용이 정한다 — 조각 3~4 동안 잡아 뒀던 잠정 높이(200)는 면접 행이
/// 들어오면서 걷어냈다.
class _Card extends StatelessWidget {
  const _Card({required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(AppSpace.s4),
      decoration: BoxDecoration(
        color: AppColors.bgElev,
        borderRadius: AppShape.card,
        border: Border.all(color: AppColors.border, width: AppShape.borderW),
        boxShadow: AppShadow.card,
      ),
      child: child,
    );
  }
}

/// 카드 머리 — 제목 왼쪽, 메타 오른쪽.
///
/// 제목 굵기는 05-design §0.5 가 카드 제목에 정한 `--font-h2`·w700·`--ts-heading`.
/// 번들한 IBM Plex Sans KR 은 400·600 두 종이라 w700 은 600 으로 붙는다 —
/// 상단 바(app_top_bar.dart)도 같은 방식이라 앱 안에서는 일관된다.
class _CardHead extends StatelessWidget {
  const _CardHead({required this.title, required this.meta});

  final String title;
  final String meta;

  @override
  Widget build(BuildContext context) {
    return Row(
      // 제목(18)과 메타(14)의 밑선을 맞춘다 — 크기가 달라 가운데 맞추면 어긋나 보인다
      crossAxisAlignment: CrossAxisAlignment.baseline,
      textBaseline: TextBaseline.alphabetic,
      children: [
        Expanded(
          child: Text(
            title,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(
              fontFamily: AppType.fontFamily,
              fontSize: AppType.h2,
              fontWeight: FontWeight.w700,
              color: AppColors.text,
              shadows: AppTextShadow.heading,
            ),
          ),
        ),
        const SizedBox(width: AppSpace.s2),
        Text(
          meta,
          softWrap: false,
          style: const TextStyle(
            fontFamily: AppType.fontFamily,
            // §2: 수치·날짜는 --font-num + tabular-nums (자리 폭 고정)
            fontSize: AppType.num,
            fontWeight: AppType.wRegular,
            fontFeatures: AppType.tabularNums,
            color: AppColors.textSub,
            // §2: 작은 글씨엔 그림자 금지
          ),
        ),
      ],
    );
  }
}

/// 면접 한 줄 — 시각 · 이름 · 공고.
///
/// 시각이 맨 앞이다. 이 카드를 보는 이유가 "몇 시에 누구"라서 시간표처럼 읽혀야 한다.
/// 면접관은 넣지 않는다 — 05-design 이 면접관 컬럼을 두는 곳은 캘린더의 그날 목록이다.
class _InterviewRow extends StatelessWidget {
  const _InterviewRow(this.interview);

  final Interview interview;

  /// 시각 칸 폭. `16:30` 이 tabular-nums 14px 로 들어가고도 남는다
  static const _timeWidth = 48.0;

  @override
  Widget build(BuildContext context) {
    return Container(
      // 머리·앞 행과 나누는 실선. 카드 테두리(--border)보다 옅은 --border-soft 다
      decoration: const BoxDecoration(
        border: Border(
          top: BorderSide(color: AppColors.borderSoft, width: AppShape.borderW),
        ),
      ),
      padding: const EdgeInsets.symmetric(vertical: AppSpace.s2),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: _timeWidth,
            child: Text(
              formatTime(interview.startAt),
              softWrap: false,
              style: const TextStyle(
                fontFamily: AppType.fontFamily,
                // §2: 수치·시각은 --font-num + tabular-nums
                fontSize: AppType.num,
                fontWeight: AppType.wSemiBold,
                fontFeatures: AppType.tabularNums,
                // §1: 잎초록은 강조 글자용. 이 줄에서 먼저 읽혀야 하는 값이다
                color: AppColors.leaf,
              ),
            ),
          ),
          const SizedBox(width: AppSpace.s3),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  interview.applicantName,
                  // §7: 한 줄 말줄임. 긴 이름이 줄을 늘리면 시간표가 무너진다
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                    fontFamily: AppType.fontFamily,
                    fontSize: AppType.body,
                    fontWeight: AppType.wSemiBold,
                    color: AppColors.text,
                  ),
                ),
                const SizedBox(height: AppSpace.s1),
                Text(
                  interview.postingTitle,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                    fontFamily: AppType.fontFamily,
                    fontSize: AppType.caption,
                    color: AppColors.textSub,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

/// 리뷰 대기 숫자·단위를 테스트가 집어 갈 손잡이.
/// 범례에도 같은 숫자가 나올 수 있어 글자만으로는 특정할 수 없다.
const reviewCountKey = Key('dashboard-review-count');
const reviewUnitKey = Key('dashboard-review-unit');

/// 내 리뷰 대기 — 큰 숫자 + 채운 버튼.
///
/// 화면에서 채운 버튼은 여기 하나다. 05-design §1 이 잎초록을 "버튼·링크·강조"에
/// 쓰라고 했고, 대시보드에서 담당자가 실제로 **할 일**은 이것뿐이라 나머지 카드는
/// 글자 링크로 두고 여기만 버튼으로 세운다.
class _ReviewQueue extends StatelessWidget {
  const _ReviewQueue({required this.count, this.onTap});

  final int count;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text(
                '내 리뷰 대기',
                style: TextStyle(
                  fontFamily: AppType.fontFamily,
                  fontSize: AppType.sm,
                  color: AppColors.textSub,
                ),
              ),
              const SizedBox(height: AppSpace.s1),
              // Text.rich 로 묶지 않는다 — 숫자와 단위를 따로 집어 확인할 수 있어야 하고,
              // 범례에도 같은 숫자가 있어 텍스트만으로는 구별이 안 된다
              Row(
                crossAxisAlignment: CrossAxisAlignment.baseline,
                textBaseline: TextBaseline.alphabetic,
                children: [
                  Text(
                    '$count',
                    key: reviewCountKey,
                    style: const TextStyle(
                      fontFamily: AppType.fontFamily,
                      // §2: 화면에서 제일 큰 글자 — display + 제목 그림자
                      fontSize: AppType.display,
                      fontWeight: FontWeight.w700,
                      fontFeatures: AppType.tabularNums,
                      color: AppColors.text,
                      shadows: AppTextShadow.heading,
                    ),
                  ),
                  const SizedBox(width: AppSpace.s1),
                  const Text(
                    '명',
                    key: reviewUnitKey,
                    style: TextStyle(
                      fontFamily: AppType.fontFamily,
                      fontSize: AppType.num,
                      fontWeight: AppType.wRegular,
                      color: AppColors.textSub,
                    ),
                  ),
                ],
              ),
            ],
          ),
        ),
        const SizedBox(width: AppSpace.s3),
        _FilledButton(label: '평가하러 가기', onTap: onTap),
      ],
    );
  }
}

/// 채운 버튼 — 잎초록 바탕 + 흰 글자.
///
/// 05-design §2: 색 채움 배경 위 밝은 글자에는 `--ts-onfill` 을 거의 항상 준다.
/// §9: 높이 44 (터치 타깃).
class _FilledButton extends StatelessWidget {
  const _FilledButton({required this.label, this.onTap});

  final String label;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: AppColors.leaf,
      borderRadius: AppShape.ctl,
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: onTap,
        // §1: 같은 자리의 press 는 한 톤 더 짙은 잎
        highlightColor: AppColors.leafStrong,
        splashColor: AppColors.leafStrong,
        child: Container(
          height: AppLayout.minTouchTarget,
          padding: const EdgeInsets.symmetric(horizontal: AppSpace.s4),
          alignment: Alignment.center,
          child: Text(
            label,
            softWrap: false,
            style: const TextStyle(
              fontFamily: AppType.fontFamily,
              fontSize: AppType.sm,
              fontWeight: AppType.wSemiBold,
              color: AppColors.bgElev,
              shadows: AppTextShadow.onFill,
            ),
          ),
        ),
      ),
    );
  }
}

/// 진행중 공고 한 줄 — 제목 · 인원 · 마감.
///
/// 내용을 왼쪽으로 몬다. 오른쪽 아래는 아르 버튼이 떠 있는 자리라 거기에
/// 읽어야 하는 값을 두면 가린다.
class _PostingRow extends StatelessWidget {
  const _PostingRow({required this.posting, required this.today});

  final JobPosting posting;
  final DateTime today;

  @override
  Widget build(BuildContext context) {
    final counts = postingCounts(posting.id);
    final people = counts.values.fold(0, (a, b) => a + b);
    final deadline = posting.deadlineOrDate(today);

    return Container(
      decoration: const BoxDecoration(
        border: Border(
          top: BorderSide(color: AppColors.borderSoft, width: AppShape.borderW),
        ),
      ),
      padding: const EdgeInsets.symmetric(vertical: AppSpace.s2),
      child: Row(
        children: [
          Flexible(
            child: Text(
              posting.title,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(
                fontFamily: AppType.fontFamily,
                fontSize: AppType.sm,
                fontWeight: AppType.wSemiBold,
                color: AppColors.text,
              ),
            ),
          ),
          const SizedBox(width: AppSpace.s2),
          Text(
            deadline == null
                ? formatCount(people)
                : '${formatCount(people)} · $deadline',
            softWrap: false,
            style: const TextStyle(
              fontFamily: AppType.fontFamily,
              fontSize: AppType.caption,
              fontFeatures: AppType.tabularNums,
              color: AppColors.textSub,
            ),
          ),
          // 오른쪽 끝을 비워 둔다 — 아르 버튼 자리
          const Spacer(),
        ],
      ),
    );
  }
}

/// 단계 그룹 — 05-design §0.5 지원자 현황 블록의 한 단계.
///
/// 색 점 + 단계 이름 + 인원, 그 아래 사람 몇 줄. 넘치면 "외 n명 →".
class _StageGroup extends StatelessWidget {
  const _StageGroup({required this.stage, required this.today});

  final Stage stage;
  final DateTime today;

  /// 단계당 보여 줄 사람 수.
  ///
  /// 웹은 5명이다. 폰에서 4단계 × 5명이면 접수만 훑다가 합격까지 못 내려가서
  /// 3명으로 줄였다 — "외 n명 →" 이 나머지를 받는다.
  static const _perStage = 3;

  @override
  Widget build(BuildContext context) {
    final all = mockApplicantsIn(stage);
    final total = mockOpenStageCounts[stage] ?? 0;
    final shown = all.take(_perStage).toList();

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Padding(
          padding: const EdgeInsets.only(top: AppSpace.s4, bottom: AppSpace.s1),
          child: Row(
            children: [
              Container(
                width: 8,
                height: 8,
                decoration: BoxDecoration(
                  // §1: 합격만 연두, 진행 중은 무채
                  color: stage == Stage.accepted
                      ? AppColors.sprout
                      : AppColors.neutral,
                  shape: BoxShape.circle,
                ),
              ),
              const SizedBox(width: AppSpace.s2),
              Text(
                stage.label,
                style: const TextStyle(
                  fontFamily: AppType.fontFamily,
                  fontSize: AppType.sm,
                  fontWeight: AppType.wSemiBold,
                  color: AppColors.text,
                ),
              ),
              const SizedBox(width: AppSpace.s2),
              Text(
                formatCount(total),
                style: const TextStyle(
                  fontFamily: AppType.fontFamily,
                  fontSize: AppType.caption,
                  fontFeatures: AppType.tabularNums,
                  color: AppColors.textSub,
                ),
              ),
            ],
          ),
        ),

        if (shown.isEmpty)
          // 숫자는 있는데 사람이 없는 단계 — 목데이터에 2번 공고 지원자가 없다
          const Padding(
            padding: EdgeInsets.symmetric(vertical: AppSpace.s2),
            child: Text(
              '없음',
              style: TextStyle(
                fontFamily: AppType.fontFamily,
                fontSize: AppType.caption,
                color: AppColors.textSub,
              ),
            ),
          )
        else
          for (final applicant in shown)
            _StageRow(applicant: applicant, stage: stage, today: today),

        if (total > shown.length)
          Padding(
            padding: const EdgeInsets.only(top: AppSpace.s2),
            child: Text(
              '외 ${total - shown.length}명 →',
              textAlign: TextAlign.right,
              style: const TextStyle(
                fontFamily: AppType.fontFamily,
                fontSize: AppType.caption,
                fontWeight: AppType.wSemiBold,
                fontFeatures: AppType.tabularNums,
                color: AppColors.leaf,
              ),
            ),
          ),
      ],
    );
  }
}

/// 단계 그룹의 한 줄 — 이름 · 공고 · (면접이면 시각 칩, 아니면 지원일).
class _StageRow extends StatelessWidget {
  const _StageRow({
    required this.applicant,
    required this.stage,
    required this.today,
  });

  final Applicant applicant;
  final Stage stage;
  final DateTime today;

  @override
  Widget build(BuildContext context) {
    final interview = stage == Stage.interview
        ? mockInterviewFor(applicant.id, today)
        : null;

    return Container(
      decoration: const BoxDecoration(
        border: Border(
          top: BorderSide(color: AppColors.borderSoft, width: AppShape.borderW),
        ),
      ),
      padding: const EdgeInsets.symmetric(vertical: AppSpace.s2),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.baseline,
        textBaseline: TextBaseline.alphabetic,
        children: [
          Flexible(
            child: Text(
              applicant.name,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              softWrap: false,
              style: const TextStyle(
                fontFamily: AppType.fontFamily,
                fontSize: AppType.sm,
                fontWeight: AppType.wSemiBold,
                color: AppColors.text,
              ),
            ),
          ),
          const SizedBox(width: AppSpace.s2),
          Expanded(
            flex: 2,
            child: Text(
              mockPostings
                  .firstWhere((p) => p.id == applicant.jobPostingId)
                  .title,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              softWrap: false,
              style: const TextStyle(
                fontFamily: AppType.fontFamily,
                fontSize: AppType.caption,
                color: AppColors.textSub,
              ),
            ),
          ),
          const SizedBox(width: AppSpace.s2),

          // §0.5: 면접 행에는 확정 시각 / 제안 중 칩.
          // 웹 Dashboard.tsx 의 scheduleChip 과 같은 네 갈래다 —
          // 확정이면 시각, 아니면 제안 중 · 제안 만료 · 일정 없음.
          // **확정만 연두, 나머지는 전부 무채**(§1 색은 판단에만).
          if (stage == Stage.interview)
            _Chip(
              label: interview != null
                  ? '${formatMonthDay(interview.startAt)} '
                        '${formatTime(interview.startAt)}'
                  : (mockScheduleStatus[applicant.id] ?? ScheduleStatus.none)
                        .label,
              confirmed: interview != null,
            )
          else
            Text(
              formatDate(applicant.createdAt),
              softWrap: false,
              style: const TextStyle(
                fontFamily: AppType.fontFamily,
                fontSize: AppType.caption,
                fontFeatures: AppType.tabularNums,
                color: AppColors.textSub,
              ),
            ),
        ],
      ),
    );
  }
}

/// 웹 `Dashboard.module.css` 의 `.chip` — 확정은 연두, 나머지는 무채.
class _Chip extends StatelessWidget {
  const _Chip({required this.label, required this.confirmed});

  final String label;
  final bool confirmed;

  @override
  Widget build(BuildContext context) {
    return Container(
      height: 22,
      padding: const EdgeInsets.symmetric(horizontal: AppSpace.s2),
      alignment: Alignment.center,
      decoration: BoxDecoration(
        color: confirmed ? AppColors.sproutSoft : AppColors.bgSunken,
        borderRadius: AppShape.pill,
        border: Border.all(
          color: confirmed ? AppColors.sprout : AppColors.border,
          width: AppShape.borderW,
        ),
      ),
      child: Text(
        label,
        softWrap: false,
        style: TextStyle(
          fontFamily: AppType.fontFamily,
          fontSize: AppType.caption,
          fontWeight: AppType.wSemiBold,
          fontFeatures: AppType.tabularNums,
          color: confirmed ? AppColors.leaf : AppColors.textSub,
        ),
      ),
    );
  }
}
