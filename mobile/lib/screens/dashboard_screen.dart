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

import '../auth/authed_client.dart';
import '../auth/current_user.dart';
import '../data/dashboard_repository.dart';
import '../data/posting_repository.dart';
import '../data/repositories.dart';
import '../data/schedule_repository.dart';
import '../widgets/async_view.dart';
import '../models/interview.dart';
import '../models/stage.dart';
import '../theme/tokens.dart';
import '../utils/format.dart';

class DashboardScreen extends StatefulWidget {
  const DashboardScreen({
    super.key,
    this.today,
    this.onOpenCalendar,
    this.onOpenReviews,
    this.onOpenApplicants,
    this.onOpenPostings,
    this.repository,
  });

  /// 테스트가 날짜를 고정할 수 있게 열어 둔다. 비면 기기 오늘.
  final DateTime? today;

  /// 카드마다 이어지는 곳. 셸이 탭을 옮겨 준다 —
  /// 대시보드는 자기가 어느 탭에 앉아 있는지 몰라야 한다
  final VoidCallback? onOpenCalendar;
  final VoidCallback? onOpenReviews;
  final VoidCallback? onOpenApplicants;
  final VoidCallback? onOpenPostings;

  /// 테스트가 가짜를 넣는 자리 (큐 8 4단계)
  final DashboardRepository? repository;

  /// 05-design §0.5 대시보드 레일은 **접수~합격 4단**. 불합격은 레일에 없다
  static const railStages = [
    Stage.applied,
    Stage.screening,
    Stage.interview,
    Stage.accepted,
  ];

  @override
  State<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen> {
  late DashboardRepository _repo;
  Future<DashboardData>? _future;

  /// 내 id 를 알아야 "내 리뷰 대기" 를 물을 수 있다. 로그인 정보가 늦게
  /// 들어오면 그때 시작한다 — 없는 채로 부르면 남의 배정을 볼 수 없다
  int? _loadedFor;

  @override
  void initState() {
    super.initState();
    final scope = RepositoryScope.of(context);
    _repo =
        widget.repository ??
        scope?.dashboard ??
        DashboardRepository(
          authedClient(),
          scope?.postings ?? PostingRepository(authedClient()),
          scope?.schedules ?? ScheduleRepository(authedClient()),
        );
  }

  /// `ignore()` 이유는 postings_screen.dart 참고
  Future<DashboardData> _load(int userId) =>
      _repo.load(userId: userId, today: widget.today)..ignore();

  void _reload() {
    final id = _loadedFor;
    if (id == null) return;
    setState(() {
      _future = _load(id);
    });
  }

  @override
  Widget build(BuildContext context) {
    final me = CurrentUserScope.of(context);

    // 로그인 정보가 들어온 뒤 한 번만 시작한다. build 마다 만들면 다시 그릴
    // 때마다 새 요청이 나간다
    if (me != null && _loadedFor != me.id) {
      _loadedFor = me.id;
      _future = _load(me.id);
    }

    final future = _future;
    if (future == null) {
      // 아직 내가 누구인지 모른다 — 시작 화면이 곧 채운다
      return const Center(child: CircularProgressIndicator());
    }

    return AsyncView<DashboardData>(
      future: future,
      onRetry: _reload,
      emptyMessage: '',
      builder: (context, data) => _body(data),
    );
  }

  Widget _body(DashboardData data) {
    final day = widget.today ?? DateTime.now();
    final interviews = data.todayInterviews;
    final stageTotals = data.stageCounts;
    final openPostings = data.openPostings;

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
              _CardLink(label: '캘린더 →', onTap: widget.onOpenCalendar),
            ],
          ),
        ),
        const SizedBox(height: AppSpace.s3),

        // ② 내 리뷰 대기 — 이 앱을 켜는 가장 큰 이유. 화면에서 유일하게 채운 버튼
        _Card(
          child: _ReviewQueue(
            count: data.reviewWaiting,
            onTap: widget.onOpenReviews,
          ),
        ),
        const SizedBox(height: AppSpace.s3),

        // ③ 전체 현황 — 회사 합계 (2026-09-07, 웹 대시보드 개편을 따라감).
        //
        // **지원자 이름 목록을 걷어냈다.** 사람을 훑는 일은 '지원자' 탭이 이미
        // 하고, 폰에서 이름 10줄은 그 탭과 구별이 안 된다. 대시보드는 "지금
        // 어디에 몇 명"에만 답한다.
        //
        // 합격·불합격에는 막대를 안 그린다. 한번 되면 영원히 쌓이는 누적값이라
        // 심사 중 세 칸과 같은 자를 쓰면 시간이 갈수록 앞 세 칸이 실오라기가
        // 된다 — 견줄 대상이 아니다. 덤으로 --ok 와 --danger 는 적록색약에서
        // ΔE 3.5 라 나란히 두면 경계가 안 보인다.
        _Card(child: _TotalsBlock(counts: stageTotals)),
        const SizedBox(height: AppSpace.s3),

        // ④ 공고별 현황 — ③ 을 공고로 쪼갠 것. 두 블록의 합은 항상 같다
        _Card(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              _CardHead(
                title: '공고별 현황',
                meta: formatItemCount(openPostings.length),
              ),
              for (final p in openPostings) _PostingRow(item: p, today: day),
              _CardLink(label: '채용 공고 →', onTap: widget.onOpenPostings),
            ],
          ),
        ),
      ],
    );
  }
}

/// 전체 현황 — 진행중 공고를 다 더한 그림 (2026-09-07, 웹 대시보드와 같은 형태).
///
/// 심사 중 세 단계는 **큰 숫자 + 막대**, 합격·불합격은 **숫자만**이다.
/// 뒤 둘은 한번 되면 영원히 쌓이는 누적값이라 앞 셋과 같은 자를 쓰면 시간이
/// 갈수록 앞이 실오라기가 된다 — 견줄 대상이 아니라 총계다.
///
/// 막대는 심사 중 세 칸끼리만 견준다. 폰은 가로가 좁아 다섯을 한 줄에 못
/// 세우므로 3 + 2 로 접는다.
class _TotalsBlock extends StatelessWidget {
  const _TotalsBlock({required this.counts});

  final Map<Stage, int> counts;

  static const _live = [Stage.applied, Stage.screening, Stage.interview];

  @override
  Widget build(BuildContext context) {
    final live = [for (final s in _live) counts[s] ?? 0];
    final maxLive = live.fold(1, (m, v) => v > m ? v : m);
    final accepted = counts[Stage.accepted] ?? 0;
    final rejected = counts[Stage.rejected] ?? 0;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        _CardHead(
          title: '전체 현황',
          meta: formatCount(
            live.fold(0, (a, b) => a + b) + accepted + rejected,
          ),
        ),
        const SizedBox(height: AppSpace.s3),
        Row(
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
            for (var i = 0; i < _live.length; i++) ...[
              if (i > 0) const SizedBox(width: AppSpace.s3),
              Expanded(
                child: _StatCell(
                  label: _live[i].label,
                  value: live[i],
                  color: AppColors.funnelRamp[i],
                  // 0 이면 막대를 안 그린다 — 높이 0 짜리를 억지로 남기면
                  // "아주 적음"으로 읽힌다. 없는 것과 적은 것은 다르다
                  fill: live[i] == 0 ? 0 : live[i] / maxLive,
                ),
              ),
            ],
          ],
        ),
        const SizedBox(height: AppSpace.s4),
        // 심사가 끝난 사람은 파이프라인 밖이다. 선을 하나 그어 가른다 —
        // 그냥 이으면 "5단계"로 읽힌다
        const Divider(height: AppShape.borderW),
        const SizedBox(height: AppSpace.s3),
        Row(
          children: [
            Expanded(
              child: _StatCell(
                label: Stage.accepted.label,
                value: accepted,
                color: AppColors.okText,
                fill: null,
              ),
            ),
            const SizedBox(width: AppSpace.s3),
            Expanded(
              child: _StatCell(
                label: Stage.rejected.label,
                value: rejected,
                color: AppColors.danger,
                fill: null,
              ),
            ),
          ],
        ),
      ],
    );
  }
}

/// 숫자 한 칸. [fill] 이 null 이면 막대 대신 '누적'이라 적는다 —
/// 자리를 비워 두면 밑선이 어긋나고, 왜 막대가 없는지도 안 보인다.
class _StatCell extends StatelessWidget {
  const _StatCell({
    required this.label,
    required this.value,
    required this.color,
    required this.fill,
  });

  final String label;
  final int value;
  final Color color;
  final double? fill;

  @override
  Widget build(BuildContext context) {
    final f = fill;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Container(
              width: 7,
              height: 7,
              decoration: BoxDecoration(
                color: color,
                borderRadius: BorderRadius.circular(2),
              ),
            ),
            const SizedBox(width: AppSpace.s2),
            Flexible(
              child: Text(
                label,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(
                  fontSize: AppType.caption,
                  color: AppColors.textSub,
                ),
              ),
            ),
          ],
        ),
        const SizedBox(height: AppSpace.s2),
        Row(
          crossAxisAlignment: CrossAxisAlignment.baseline,
          textBaseline: TextBaseline.alphabetic,
          children: [
            Text(
              '$value',
              style: TextStyle(
                fontSize: AppType.display,
                fontWeight: AppType.wSemiBold,
                color: f == null ? color : AppColors.text,
                fontFeatures: AppType.tabularNums,
                height: 1,
              ),
            ),
            const SizedBox(width: AppSpace.s1),
            const Text(
              '명',
              style: TextStyle(
                fontSize: AppType.caption,
                color: AppColors.textSub,
              ),
            ),
          ],
        ),
        const SizedBox(height: AppSpace.s2),
        if (f == null)
          const SizedBox(
            height: 10,
            child: Align(
              alignment: Alignment.centerLeft,
              child: Text(
                '누적',
                style: TextStyle(fontSize: 10, color: AppColors.textSub),
              ),
            ),
          )
        else
          ClipRRect(
            borderRadius: const BorderRadius.horizontal(
              right: Radius.circular(3),
            ),
            child: Container(
              height: 10,
              color: AppColors.bgSunken,
              child: FractionallySizedBox(
                alignment: Alignment.centerLeft,
                widthFactor: f,
                child: Container(color: color),
              ),
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
  const _PostingRow({required this.item, required this.today});

  /// 공고 + 그 공고의 단계별 인원. 목록이 이미 세어 준 것을 그대로 쓴다
  final PostingWithCounts item;

  final DateTime today;

  @override
  Widget build(BuildContext context) {
    final posting = item.posting;
    final people = item.total;
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
