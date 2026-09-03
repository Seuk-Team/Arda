/// 평가 현황 — 앱 UI 초안(2026-09-01) 조각 13.
///
/// 05-design §0.5: "평가 현황 | 면접관 관점: **내게 배정된 평가 대기 큐** + 우측
/// 평가 패널, 등록 시 자동 다음 지원자". 375px 엔 "우측"이 없으므로 큐만 두고,
/// 한 명을 누르면 그 사람의 평가 화면으로 넘어간다(§9 상세는 화면을 덮는다).
///
/// **이 화면이 §6 세 상태를 처음으로 다 갖춘 화면이다.** 문구는 지어내지 않고
/// 웹(`frontend/app/src/pages/Evaluations.tsx`)에서 그대로 가져왔다:
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
import '../models/applicant.dart';
import '../routes.dart';
import '../theme/tokens.dart';
import '../utils/format.dart';
import '../widgets/app_top_bar.dart';
import '../widgets/stage_label.dart';

/// 평가 대기 한 줄에 필요한 것 — 지원자 + 어느 공고인지.
typedef QueueEntry = (Applicant applicant, String postingTitle);

/// 큐를 가져오는 일. 테스트가 세 상태(로딩·빈·오류)를 만드는 구멍이다.
typedef QueueLoader = Future<List<QueueEntry>> Function();

class EvaluationQueueScreen extends StatefulWidget {
  const EvaluationQueueScreen({super.key, this.loader});

  /// 테스트가 세 상태를 각각 만들 수 있게 열어 둔다
  final QueueLoader? loader;

  @override
  State<EvaluationQueueScreen> createState() => _EvaluationQueueScreenState();
}

class _EvaluationQueueScreenState extends State<EvaluationQueueScreen> {
  Future<List<QueueEntry>>? _future;
  int? _loadedFor;

  /// 배정 → 사람마다 상세, 그리고 공고명 표.
  ///
  /// **배정 응답에 이름도 공고명도 없어서** 건마다 상세를 한 번 더 받는다
  /// (`AssignmentOut` 은 id 뿐). 웹 `Evaluations.tsx` 도 `Promise.all` 로
  /// 똑같이 한다 — 배정이 보통 몇 건이라 병렬이면 체감이 없다.
  ///
  /// 공고명은 못 받아도 큐는 보여 준다(웹과 같은 처리).
  Future<List<QueueEntry>> _serverLoader(int userId) async {
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

    final ids = await dash.assignedIds(userId);

    var titles = <int, String>{};
    try {
      final postings = await postingRepo.list();
      titles = {for (final p in postings) p.posting.id: p.posting.title};
    } on Exception {
      titles = const {};
    }

    final details = await Future.wait(ids.map(applicantRepo.detail));
    return [
      for (final d in details)
        (d.applicant, titles[d.applicant.jobPostingId] ?? ''),
    ];
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
      body: FutureBuilder<List<QueueEntry>>(
        future: _future,
        builder: (context, snapshot) {
          if (_future == null ||
              snapshot.connectionState == ConnectionState.waiting) {
            return const _Loading();
          }
          if (snapshot.hasError) {
            return _Error(onRetry: _reload);
          }
          final items = snapshot.data ?? const [];
          if (items.isEmpty) return const _Empty();
          return _Queue(items: items);
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

class _Queue extends StatelessWidget {
  const _Queue({required this.items});

  final List<QueueEntry> items;

  @override
  Widget build(BuildContext context) {
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
          // 웹 헤더가 "평가 대기 N명" 이다
          child: Text(
            '평가 대기 ${formatCount(items.length)}',
            style: const TextStyle(
              fontFamily: AppType.fontFamily,
              fontSize: AppType.sm,
              fontWeight: AppType.wSemiBold,
              fontFeatures: AppType.tabularNums,
              color: AppColors.text,
            ),
          ),
        ),
        Expanded(
          child: ListView.separated(
            padding: const EdgeInsets.fromLTRB(
              AppSpace.s4,
              0,
              AppSpace.s4,
              AppSpace.s4,
            ),
            itemCount: items.length,
            separatorBuilder: (_, _) => const SizedBox(height: AppSpace.s3),
            itemBuilder: (_, i) => _QueueCard(entry: items[i]),
          ),
        ),
      ],
    );
  }
}

class _QueueCard extends StatelessWidget {
  const _QueueCard({required this.entry});

  final QueueEntry entry;

  @override
  Widget build(BuildContext context) {
    final (applicant, postingTitle) = entry;

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
              Row(
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
                  StageLabel(stage: applicant.currentStage),
                ],
              ),
              const SizedBox(height: AppSpace.s2),
              Text(
                postingTitle,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                softWrap: false,
                style: const TextStyle(
                  fontFamily: AppType.fontFamily,
                  fontSize: AppType.sm,
                  color: AppColors.textSub,
                ),
              ),
              const SizedBox(height: AppSpace.s1),
              Text(
                // 웹은 "배정일" 컬럼이다. 목데이터에 배정이 없어 지원일을 쓴다 —
                // API 연동 때 assigned_at 으로 바꾼다
                formatDate(applicant.createdAt),
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
      ),
    );
  }
}
