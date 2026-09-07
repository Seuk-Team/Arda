/// 평가 현황 — 앱 UI 초안(2026-09-01) 조각 13, 2026-09-07 웹 개편을 따라 고침.
///
/// 05-design §0.5: "평가 현황 | 면접관 관점: **내게 배정된 평가 대기 큐** + 우측
/// 평가 패널, 등록 시 자동 다음 지원자". 375px 엔 "우측"이 없으므로 큐만 두고,
/// 한 명을 누르면 그 사람의 평가 화면으로 넘어간다(§9 상세는 화면을 덮는다).
///
/// **2026-09-07 — 웹(`pages/Evaluations.tsx`)과 같은 것을 보여 준다.** 전에는
/// 이름·공고·날짜 세 줄뿐이라 "누가 밀렸는지" 를 알 수 없었다. 이제 줄마다
/// 상태가 붙는다: 배정 n일째 · 의견 갈림 · n일 경과 · 누가 냈는지 · 점수.
/// 계산은 웹과 같은 임계값으로 `utils/eval_queue.dart` 가 한다.
///
/// 웹의 **왼쪽 공고 레일**은 폰에서 가로 칩 줄이 된다 — 세로로 두면 375px 에서
/// 목록에 남는 폭이 없다. 공고가 하나뿐이면 접는다('전체' 와 같은 것이라
/// 두 번 적는 꼴이다).
///
/// **이 화면이 §6 세 상태를 처음으로 다 갖춘 화면이다.** 문구는 지어내지 않고
/// 웹에서 그대로 가져왔다:
///
/// - 로딩 → "불러오는 중…"
/// - 비어 있음 → "평가 대기 중인 지원자가 없습니다."
/// - 오류 → "평가 대기 목록을 불러오지 못했습니다"
///
/// 웹과 딱 하나 다르다: **오류에 [다시 시도] 를 단다.** 앱에는 새로고침이 없어
/// 문구만 띄우면 사용자가 할 수 있는 일이 없다.
library;

import 'package:flutter/material.dart';

import '../auth/authed_client.dart';
import '../auth/current_user.dart';
import '../data/applicant_repository.dart';
import '../data/dashboard_repository.dart';
import '../data/posting_repository.dart';
import '../data/repositories.dart';
import '../data/schedule_repository.dart';
import '../data/settings_repository.dart';
import '../routes.dart';
import '../theme/tokens.dart';
import '../utils/eval_queue.dart';
import '../utils/format.dart';
import '../widgets/app_top_bar.dart';

/// 큐를 가져오는 일. 테스트가 세 상태(로딩·빈·오류)를 만드는 구멍이다.
typedef QueueLoader = Future<QueueData> Function();

class EvaluationQueueScreen extends StatefulWidget {
  const EvaluationQueueScreen({super.key, this.loader});

  /// 테스트가 세 상태를 각각 만들 수 있게 열어 둔다
  final QueueLoader? loader;

  @override
  State<EvaluationQueueScreen> createState() => _EvaluationQueueScreenState();
}

class _EvaluationQueueScreenState extends State<EvaluationQueueScreen> {
  Future<QueueData>? _future;
  int? _loadedFor;

  /// 배정 → 사람마다 상세, 그리고 공고명·평가자 이름 표.
  ///
  /// **배정 응답에 이름도 공고명도 없어서** 건마다 상세를 한 번 더 받는다
  /// (`AssignmentOut` 은 id·시각뿐). 웹 `Evaluations.tsx` 도 `Promise.all` 로
  /// 똑같이 한다 — 배정이 보통 몇 건이라 병렬이면 체감이 없다.
  ///
  /// 곁다리 둘(공고명·평가자 이름)은 **실패해도 큐를 막지 않는다**(웹과 같은
  /// 처리). 공고명이 없으면 레일을 접고, 이름이 없으면 아바타가 '?' 로 뜬다.
  Future<QueueData> _serverLoader(int userId) async {
    final scope = RepositoryScope.of(context);
    final dash =
        scope?.dashboard ??
        DashboardRepository(
          authedClient(),
          scope?.postings ?? PostingRepository(authedClient()),
          scope?.schedules ?? ScheduleRepository(authedClient()),
        );
    final applicantRepo =
        scope?.applicants ?? ApplicantRepository(authedClient());
    final postingRepo = scope?.postings ?? PostingRepository(authedClient());
    final settingsRepo = SettingsRepository(authedClient());

    final assignments = await dash.assignments(userId);

    var titles = <int, String>{};
    try {
      final postings = await postingRepo.list();
      titles = {for (final p in postings) p.posting.id: p.posting.title};
    } on Exception {
      titles = const {};
    }

    var names = <int, String>{};
    try {
      final users = await settingsRepo.users();
      names = {for (final u in users) u.id: u.name};
    } on Exception {
      names = const {};
    }

    final details = await Future.wait(
      assignments.map((a) => applicantRepo.detail(a.applicationId)),
    );
    return QueueData(
      meId: userId,
      evaluatorNames: names,
      entries: [
        for (var i = 0; i < details.length; i++)
          QueueEntry(
            applicant: details[i].applicant,
            postingTitle: titles[details[i].applicant.jobPostingId] ?? '',
            assignedAt: assignments[i].assignedAt,
            evaluations: details[i].evaluations,
            avgScore: details[i].avgScore,
          ),
      ],
    );
  }

  void _reload() {
    final id = _loadedFor;
    setState(() {
      _future = widget.loader != null
          ? widget.loader!()
          : (id == null ? null : _serverLoader(id));
    });
  }

  @override
  Widget build(BuildContext context) {
    // 배정은 "누구에게" 가 있어야 물을 수 있다. 로그인 정보가 들어온 뒤
    // 한 번만 시작한다 — build 마다 만들면 다시 그릴 때마다 새 요청이 나간다
    if (widget.loader != null) {
      _future ??= widget.loader!();
    } else {
      final me = CurrentUserScope.of(context);
      if (me != null && _loadedFor != me.id) {
        _loadedFor = me.id;
        _future = _serverLoader(me.id)..ignore();
      }
    }

    return Scaffold(
      appBar: const AppTopBar(title: '평가 현황', showBack: true),
      body: FutureBuilder<QueueData>(
        future: _future,
        builder: (context, snapshot) {
          if (_future == null ||
              snapshot.connectionState == ConnectionState.waiting) {
            return const _Loading();
          }
          if (snapshot.hasError) {
            return _Error(onRetry: _reload);
          }
          final data = snapshot.data;
          if (data == null || data.isEmpty) return const _Empty();
          return _Queue(data: data);
        },
      ),
    );
  }
}

/// 로딩 — 문구 한 줄 + 골격 카드.
///
/// 스피너 대신 골격을 쓴다: 곧 무엇이 올지 자리로 미리 알려 주면 기다림이 짧게
/// 느껴진다(Material "skeleton" 권고). 05-design §5 의 모션 토큰만 쓴다.
class _Loading extends StatelessWidget {
  const _Loading();

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.all(AppSpace.s4),
      children: [
        const Padding(
          padding: EdgeInsets.only(bottom: AppSpace.s3),
          child: Text(
            '불러오는 중…',
            style: TextStyle(
              fontFamily: AppType.fontFamily,
              fontSize: AppType.sm,
              color: AppColors.textSub,
            ),
          ),
        ),
        for (var i = 0; i < 3; i++) ...[
          const _SkeletonCard(),
          const SizedBox(height: AppSpace.s3),
        ],
      ],
    );
  }
}

class _SkeletonCard extends StatelessWidget {
  const _SkeletonCard();

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
      child: const Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _Bar(widthFactor: 0.38, height: 16),
          SizedBox(height: AppSpace.s3),
          _Bar(widthFactor: 0.64, height: 12),
          SizedBox(height: AppSpace.s2),
          _Bar(widthFactor: 0.5, height: 12),
        ],
      ),
    );
  }
}

class _Bar extends StatelessWidget {
  const _Bar({required this.widthFactor, required this.height});

  final double widthFactor;
  final double height;

  @override
  Widget build(BuildContext context) {
    return FractionallySizedBox(
      alignment: Alignment.centerLeft,
      widthFactor: widthFactor,
      child: Container(
        height: height,
        decoration: const BoxDecoration(
          // 인풋·트랙과 같은 단계 — 패널보다 한 단계 아래(§1 --bg-sunken)
          color: AppColors.bgSunken,
          borderRadius: AppShape.ctl,
        ),
      ),
    );
  }
}

/// 비어 있음 — 웹과 같은 문구.
class _Empty extends StatelessWidget {
  const _Empty();

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(AppSpace.s6),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              width: 56,
              height: 56,
              alignment: Alignment.center,
              decoration: const BoxDecoration(
                color: AppColors.bgSunken,
                shape: BoxShape.circle,
              ),
              child: const Icon(
                Icons.star_outline,
                size: 26,
                color: AppColors.neutral,
              ),
            ),
            const SizedBox(height: AppSpace.s3),
            const Text(
              '평가 대기 중인 지원자가 없습니다.',
              textAlign: TextAlign.center,
              style: TextStyle(
                fontFamily: AppType.fontFamily,
                fontSize: AppType.sm,
                color: AppColors.textSub,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// 오류 — 웹 문구 + [다시 시도].
class _Error extends StatelessWidget {
  const _Error({required this.onRetry});

  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Container(
        margin: const EdgeInsets.all(AppSpace.s4),
        padding: const EdgeInsets.symmetric(
          horizontal: AppSpace.s4,
          vertical: AppSpace.s5,
        ),
        decoration: BoxDecoration(
          // §1: 적갈 워시 — 종료·실패 신호
          color: AppColors.dangerSoft,
          borderRadius: AppShape.card,
          border: Border.all(color: AppColors.danger, width: AppShape.borderW),
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Semantics(
              liveRegion: true,
              child: const Text(
                '평가 대기 목록을 불러오지 못했습니다',
                textAlign: TextAlign.center,
                style: TextStyle(
                  fontFamily: AppType.fontFamily,
                  fontSize: AppType.sm,
                  color: AppColors.danger,
                ),
              ),
            ),
            const SizedBox(height: AppSpace.s4),
            Material(
              color: AppColors.bgElev,
              borderRadius: AppShape.ctl,
              clipBehavior: Clip.antiAlias,
              child: InkWell(
                onTap: onRetry,
                highlightColor: AppColors.dangerSoft,
                splashColor: AppColors.dangerSoft,
                child: Container(
                  height: AppLayout.minTouchTarget,
                  padding: const EdgeInsets.symmetric(horizontal: AppSpace.s5),
                  alignment: Alignment.center,
                  decoration: BoxDecoration(
                    borderRadius: AppShape.ctl,
                    border: Border.all(
                      color: AppColors.danger,
                      width: AppShape.borderW,
                    ),
                  ),
                  child: const Text(
                    '다시 시도',
                    style: TextStyle(
                      fontFamily: AppType.fontFamily,
                      fontSize: AppType.sm,
                      fontWeight: AppType.wSemiBold,
                      color: AppColors.danger,
                    ),
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// 목록 — 요약 줄 + 공고 레일 + 줄들.
///
/// 레일이 골라 놓은 것을 기억해야 해서 StatefulWidget 이다.
class _Queue extends StatefulWidget {
  const _Queue({required this.data});

  final QueueData data;

  @override
  State<_Queue> createState() => _QueueState();
}

class _QueueState extends State<_Queue> {
  /// 고른 공고. null 이면 '전체'
  int? _selected;

  @override
  Widget build(BuildContext context) {
    final rows = buildRows(widget.data);
    final groups = buildGroups(rows);

    // 골라 둔 공고가 사라졌으면(평가를 내고 목록에서 빠졌다) 전체로 돌아간다 —
    // 안 그러면 아무것도 없는 화면이 남는다
    final sel = groups.any((g) => g.id == _selected) ? _selected : null;
    final shown = sel == null
        ? rows
        : [
            for (final r in rows)
              if (r.postingId == sel) r,
          ];

    final pending = rows.where((r) => r.mine == null).length;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(
            AppSpace.s4,
            AppSpace.s4,
            AppSpace.s4,
            AppSpace.s2,
          ),
          // 웹 머리말과 같은 문구다
          child: Text(
            '내가 안 낸 평가 ${formatItemCount(pending)} / 배정 ${formatItemCount(rows.length)}',
            style: const TextStyle(
              fontFamily: AppType.fontFamily,
              fontSize: AppType.sm,
              fontFeatures: AppType.tabularNums,
              color: AppColors.textSub,
            ),
          ),
        ),

        // 공고가 하나뿐이면 '전체' 와 같은 것이라 레일을 접는다.
        // 공고명을 못 받았을 때(제목이 빈 문자열)도 마찬가지 — 이름 없는 칸을
        // 고르게 하는 것은 고르는 게 아니다
        if (groups.length > 2 && groups.every((g) => g.title.isNotEmpty))
          _Rail(
            groups: groups,
            selected: sel,
            onSelect: (id) => setState(() => _selected = id),
          ),

        Expanded(
          child: ListView.separated(
            padding: const EdgeInsets.fromLTRB(
              AppSpace.s4,
              AppSpace.s3,
              AppSpace.s4,
              AppSpace.s4,
            ),
            itemCount: shown.length,
            separatorBuilder: (_, _) => const SizedBox(height: AppSpace.s3),
            itemBuilder: (_, i) =>
                _QueueCard(row: shown[i], names: widget.data.evaluatorNames),
          ),
        ),
      ],
    );
  }
}

/// 공고 레일 — 웹은 왼쪽 세로 목록, 폰은 가로 칩 줄이다.
///
/// 고르는 곳이면서 진행률 표시다: 칸마다 `낸 것/배정` 과 막대가 붙어,
/// 고르기 전에도 어느 공고가 밀렸는지가 보인다.
class _Rail extends StatelessWidget {
  const _Rail({
    required this.groups,
    required this.selected,
    required this.onSelect,
  });

  final List<QueueGroup> groups;
  final int? selected;
  final ValueChanged<int?> onSelect;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: 58,
      child: ListView.separated(
        scrollDirection: Axis.horizontal,
        padding: const EdgeInsets.symmetric(horizontal: AppSpace.s4),
        itemCount: groups.length,
        separatorBuilder: (_, _) => const SizedBox(width: AppSpace.s2),
        itemBuilder: (_, i) {
          final g = groups[i];
          return _RailChip(
            group: g,
            on: g.id == selected,
            onTap: () => onSelect(g.id),
          );
        },
      ),
    );
  }
}

class _RailChip extends StatelessWidget {
  const _RailChip({required this.group, required this.on, required this.onTap});

  final QueueGroup group;
  final bool on;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Material(
      // 고른 칸은 사이드바 활성 항목과 같은 표시 — 시안 워시 + 테두리 (§2)
      color: on ? AppColors.accentSoft : AppColors.bgSunken,
      shape: RoundedRectangleBorder(
        borderRadius: AppShape.ctl,
        side: BorderSide(
          color: on ? AppColors.accent : AppColors.borderSoft,
          width: AppShape.borderW,
        ),
      ),
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: onTap,
        highlightColor: AppColors.sunkenHover,
        splashColor: AppColors.sunkenHover,
        child: Semantics(
          selected: on,
          button: true,
          child: Container(
            width: 132,
            padding: const EdgeInsets.symmetric(
              horizontal: AppSpace.s3,
              vertical: AppSpace.s2,
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Row(
                  children: [
                    Expanded(
                      child: Text(
                        group.title,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        softWrap: false,
                        style: TextStyle(
                          fontFamily: AppType.fontFamily,
                          fontSize: AppType.caption,
                          fontWeight: AppType.wSemiBold,
                          color: on ? AppColors.accentText : AppColors.text,
                        ),
                      ),
                    ),
                    const SizedBox(width: AppSpace.s1),
                    Text(
                      '${group.done}/${group.total}',
                      style: const TextStyle(
                        fontFamily: AppType.fontFamily,
                        fontSize: AppType.caption,
                        fontFeatures: AppType.tabularNums,
                        color: AppColors.textSub,
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 6),
                ClipRRect(
                  borderRadius: const BorderRadius.all(Radius.circular(2)),
                  child: SizedBox(
                    height: 4,
                    child: Stack(
                      children: [
                        Container(color: AppColors.bgSunken),
                        FractionallySizedBox(
                          alignment: Alignment.centerLeft,
                          widthFactor: group.ratio,
                          child: Container(color: AppColors.accent),
                        ),
                      ],
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// 한 줄 — 웹은 다섯 열, 폰은 세 줄이다.
///
/// 폭이 375 라 열로 세울 수가 없다. 대신 **위에서 아래로** 급한 것부터 둔다:
/// 이름·점수 → 단계·배정일 → 누가 냈는지·무엇을 하게 되는지.
class _QueueCard extends StatelessWidget {
  const _QueueCard({required this.row, required this.names});

  final QueueRow row;

  /// evaluator_id → 이름. 비어 있으면 아바타가 '?' 로 뜬다
  final Map<int, String> names;

  @override
  Widget build(BuildContext context) {
    final applicant = row.applicant;

    return Material(
      color: AppColors.bgElev,
      shape: const RoundedRectangleBorder(
        borderRadius: AppShape.card,
        side: BorderSide(color: AppColors.border, width: AppShape.borderW),
      ),
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: () => Navigator.pushNamed(
          context,
          Routes.evaluations,
          arguments: applicant,
        ),
        highlightColor: AppColors.bgSunken,
        splashColor: AppColors.bgSunken,
        child: Padding(
          padding: const EdgeInsets.all(AppSpace.s4),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // ① 이름 + 점수
              Row(
                crossAxisAlignment: CrossAxisAlignment.baseline,
                textBaseline: TextBaseline.alphabetic,
                children: [
                  Expanded(
                    child: Text(
                      applicant.name,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      softWrap: false,
                      style: const TextStyle(
                        fontFamily: AppType.fontFamily,
                        fontSize: AppType.body,
                        fontWeight: AppType.wSemiBold,
                        color: AppColors.text,
                      ),
                    ),
                  ),
                  const SizedBox(width: AppSpace.s2),
                  _Score(row: row),
                ],
              ),
              const SizedBox(height: AppSpace.s2),

              // ② 단계 · 배정 n일째 + (남들만 냈으면) 몇 명이 냈는지
              Row(
                children: [
                  Expanded(
                    child: Text(
                      '${applicant.currentStage.label} · 배정 ${row.days}일째',
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      softWrap: false,
                      style: const TextStyle(
                        fontFamily: AppType.fontFamily,
                        fontSize: AppType.sm,
                        fontFeatures: AppType.tabularNums,
                        color: AppColors.textSub,
                      ),
                    ),
                  ),
                  if (row.sub.isNotEmpty) ...[
                    const SizedBox(width: AppSpace.s2),
                    Text(
                      row.sub,
                      style: const TextStyle(
                        fontFamily: AppType.fontFamily,
                        fontSize: AppType.caption,
                        color: AppColors.textSub,
                      ),
                    ),
                  ],
                ],
              ),
              const SizedBox(height: AppSpace.s3),

              // ③ 평가자 · 배지 · 다음 동작
              Row(
                children: [
                  _Avatars(row: row, names: names),
                  // 배지는 색만으로 뜻을 나르지 않는다 — 글자가 항상 같이 있다
                  if (row.split) ...[
                    const SizedBox(width: AppSpace.s2),
                    const _Badge(
                      label: '의견 갈림',
                      fg: AppColors.warnText,
                      line: AppColors.warn,
                    ),
                  ],
                  if (row.stale) ...[
                    const SizedBox(width: AppSpace.s2),
                    _Badge(
                      label: '${row.days}일 경과',
                      fg: AppColors.danger,
                      line: AppColors.danger,
                    ),
                  ],
                  const Spacer(),
                  const SizedBox(width: AppSpace.s2),
                  _Action(row: row),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// 점수 — 갈렸으면 양끝, 아직이면 '미착수'.
class _Score extends StatelessWidget {
  const _Score({required this.row});

  final QueueRow row;

  @override
  Widget build(BuildContext context) {
    // 아직 안 낸 것은 숫자가 아니라 글자다 — 크기를 낮춰 점수와 안 헷갈리게 한다
    if (row.scoreTone == ScoreTone.none) {
      return Text(
        row.scoreText,
        style: const TextStyle(
          fontFamily: AppType.fontFamily,
          fontSize: AppType.sm,
          color: AppColors.textSub,
        ),
      );
    }
    return Text(
      row.scoreText,
      style: TextStyle(
        fontFamily: AppType.fontFamily,
        fontSize: AppType.body,
        fontWeight: AppType.wSemiBold,
        fontFeatures: AppType.tabularNums,
        color: row.scoreTone == ScoreTone.warn
            ? AppColors.warnText
            : AppColors.okText,
      ),
    );
  }
}

/// 누가 냈는지 — 셋까지 그리고 나머지는 수로.
class _Avatars extends StatelessWidget {
  const _Avatars({required this.row, required this.names});

  final QueueRow row;
  final Map<int, String> names;

  @override
  Widget build(BuildContext context) {
    final all = row.evaluators;
    // 아무도 안 냈으면 빈 칸으로 둔다 — 오른쪽이 이미 '미착수'라고 말하고 있어
    // 여기 '평가 없음'을 또 쓰면 같은 말을 두 번 한다
    if (all.isEmpty) return const SizedBox.shrink();

    final shown = all.take(3).toList();
    final rest = all.length - shown.length;

    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        for (final e in shown) ...[
          _AvatarDot(
            name: e.evaluatorName ?? names[e.evaluatorId] ?? '?',
            score: e.score,
          ),
          const SizedBox(width: 3),
        ],
        if (rest > 0)
          Text(
            '+$rest',
            style: const TextStyle(
              fontFamily: AppType.fontFamily,
              fontSize: AppType.caption,
              fontFeatures: AppType.tabularNums,
              color: AppColors.textSub,
            ),
          ),
      ],
    );
  }
}

class _AvatarDot extends StatelessWidget {
  const _AvatarDot({required this.name, required this.score});

  final String name;
  final int score;

  @override
  Widget build(BuildContext context) {
    final av = avatarOf(name);
    return Semantics(
      label: '$name $score점',
      child: Container(
        width: 24,
        height: 24,
        alignment: Alignment.center,
        decoration: BoxDecoration(color: Color(av.bg), shape: BoxShape.circle),
        child: Text(
          av.initials,
          maxLines: 1,
          style: TextStyle(
            fontFamily: AppType.fontFamily,
            fontSize: AppType.caption,
            fontWeight: AppType.wSemiBold,
            color: Color(av.fg),
          ),
        ),
      ),
    );
  }
}

class _Badge extends StatelessWidget {
  const _Badge({required this.label, required this.fg, required this.line});

  final String label;
  final Color fg;
  final Color line;

  @override
  Widget build(BuildContext context) {
    return Container(
      height: 20,
      padding: const EdgeInsets.symmetric(horizontal: 7),
      alignment: Alignment.center,
      decoration: BoxDecoration(
        color: line.withValues(alpha: 0.14),
        borderRadius: const BorderRadius.all(Radius.circular(3)),
        border: Border.all(
          color: line.withValues(alpha: 0.35),
          width: AppShape.borderW,
        ),
      ),
      child: Text(
        label,
        style: TextStyle(
          fontFamily: AppType.fontFamily,
          fontSize: AppType.caption,
          fontWeight: AppType.wSemiBold,
          fontFeatures: AppType.tabularNums,
          color: fg,
        ),
      ),
    );
  }
}

/// 눌렀을 때 무엇을 하게 되는지. **카드 전체가 이미 눌리는 자리라** 이건
/// 버튼이 아니라 표시다 — 그래서 따로 탭을 받지 않는다(같은 자리에 탭이 둘이면
/// 44 규칙을 지켜도 무엇이 눌렸는지 알 수 없다).
class _Action extends StatelessWidget {
  const _Action({required this.row});

  final QueueRow row;

  @override
  Widget build(BuildContext context) {
    // 내가 아직 안 낸 건만 채운다 — 할 일이 있는 줄이 눈에 먼저 든다
    final go = row.mine == null;
    return Container(
      height: 28,
      padding: const EdgeInsets.symmetric(horizontal: 11),
      alignment: Alignment.center,
      decoration: BoxDecoration(
        color: go ? AppColors.accentFill : AppColors.bgSunken,
        borderRadius: AppShape.ctl,
        border: go
            ? null
            : Border.all(color: AppColors.border, width: AppShape.borderW),
      ),
      child: Text(
        row.action,
        style: TextStyle(
          fontFamily: AppType.fontFamily,
          fontSize: AppType.caption,
          fontWeight: AppType.wSemiBold,
          color: go ? AppColors.onAccent : AppColors.text,
          shadows: go ? AppTextShadow.onFill : null,
        ),
      ),
    );
  }
}
