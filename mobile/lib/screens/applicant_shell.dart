/// 지원자 셸 — 하단 탭 다섯 칸 (2026-09-08).
///
/// 담당자 셸([HomeShell])과 **완전히 다른 앱처럼** 돈다: 탭도, 상단 바 제목도,
/// 부르는 API 도 겹치지 않는다. 지원자는 담당자 화면을 한 조각도 보면 안 된다.
///
///   인적성 · 일정 · **홈** · 면접 · 더보기
///
/// 홈이 가운데인 이유는 담당자 셸과 같다 — 어디서든 돌아오는 자리고 엄지가
/// 제일 편하다. 왼쪽은 "먼저 하는 것"(인적성 → 일정 조율), 오른쪽은 "그다음"
/// (면접 → 내 정보).
///
/// ## 요청 한 번으로 다 받는다
///
/// `GET /applicant/me` 가 지원 현황과 **탭 넷의 토큰을 한 번에** 준다
/// (ADR-0031 + PR #84). 셸이 한 번 받아 나눠 주므로 탭마다 서버를 다시 부르지
/// 않는다 — 링크를 따로 받던 시절에 화면마다 왕복이 쌓이던 구조를 걷어냈다.
///
/// 서버가 **아직 할 일이 남은 것만** 내려준다: 면접 `pending`·`in_progress`,
/// 인적성 `pending`, 일정 `proposed`·`confirmed`. 들어가 봐야 막히는 문은
/// 오지 않으므로 앱이 거를 것이 없다.
///
/// 받은 적 없는 탭은 **비어 있다고 말한다.** 담당자가 아직 안 보낸 것이지
/// 지원자가 뭘 잘못한 게 아니라서, 오류처럼 그리지 않는다.
///
/// ## 탭은 처음 열 때 만든다
///
/// [IndexedStack] 은 자식을 다 만들어 두는데, 그러면 앱을 켜는 순간 네 화면이
/// 각자 자기 링크를 부른다. 한 번이라도 연 탭만 만든다 — 열어 둔 탭은 그대로
/// 살아 있어 돌아왔을 때 다시 안 받는다.
library;

import 'package:flutter/material.dart';

import '../api/api_error.dart';
import '../data/applicant_portal_repository.dart';
import '../models/applicant_me.dart';
import '../routes.dart';
import '../theme/tokens.dart';
import '../utils/format.dart';
import '../widgets/app_bottom_nav.dart';
import '../widgets/app_top_bar.dart';
import 'applicant_more_screen.dart';
import 'applicant_summary_screen.dart';
import 'aptitude_screen.dart';
import 'interview_live_screen.dart';
import 'schedule_screen.dart';

enum ApplicantTab implements NavTab {
  aptitude(Icons.fact_check_outlined, '인적성', '인적성 검사'),
  schedule(Icons.event_available_outlined, '일정', '면접 시간 조율'),
  home(Icons.home_outlined, '홈', '내 지원'),
  interview(Icons.videocam_outlined, '면접', 'AI 면접'),
  more(Icons.menu, '더보기', '더보기');

  const ApplicantTab(this.icon, this.label, this.title);

  @override
  final IconData icon;

  /// 탭바에 들어가는 짧은 이름 — 5칸에 맞춰 줄인 것
  @override
  final String label;

  /// 상단 바에 걸리는 이름. 라벨보다 길다(담당자 셸과 같은 규칙)
  final String title;
}

class ApplicantShell extends StatefulWidget {
  const ApplicantShell({super.key, this.portal, this.initialTab});

  /// 테스트가 가짜를 넣는 자리
  final ApplicantPortalRepository? portal;
  final ApplicantTab? initialTab;

  @override
  State<ApplicantShell> createState() => _ApplicantShellState();
}

class _ApplicantShellState extends State<ApplicantShell> {
  late final ApplicantPortalRepository _portal =
      widget.portal ?? ApplicantPortalRepository();

  late ApplicantTab _current = widget.initialTab ?? ApplicantTab.home;

  /// 한 번이라도 연 탭. 홈은 처음부터 열려 있다
  late final Set<ApplicantTab> _opened = {_current};

  ApplicantMe? _me;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _error = null);
    try {
      final me = await _portal.me();
      if (!mounted) return;
      setState(() => _me = me);
    } on AuthExpired {
      // 2시간짜리라 흔하다. 저장된 토큰은 ApiClient 가 이미 버렸다
      if (!mounted) return;
      Navigator.pushReplacementNamed(context, Routes.login);
    } on ApiError catch (e) {
      if (!mounted) return;
      setState(() => _error = e.message);
    }
  }

  void _go(ApplicantTab tab) => setState(() {
    _current = tab;
    _opened.add(tab);
  });

  /// 지원자로서 나가기. **담당자 토큰은 건드리지 않는다** — 저장소가 아예 다르다
  Future<void> _leave() async {
    await _portal.logout();
    if (!mounted) return;
    Navigator.pushReplacementNamed(context, Routes.login);
  }

  @override
  Widget build(BuildContext context) {
    final me = _me;
    return Scaffold(
      appBar: AppTopBar(title: _current.title),
      body: me == null ? _waiting() : _tabs(me),
      bottomNavigationBar: AppBottomNav(
        tabs: ApplicantTab.values,
        current: _current,
        onSelected: _go,
      ),
    );
  }

  Widget _waiting() => _error == null
      ? const Center(child: CircularProgressIndicator())
      : _Failed(message: _error!, onRetry: _load);

  Widget _tabs(ApplicantMe me) => IndexedStack(
    index: ApplicantTab.values.indexOf(_current),
    children: [
      for (final tab in ApplicantTab.values)
        // 안 연 탭은 자리만 잡아 둔다 — 만들면 자기 링크를 부른다
        _opened.contains(tab) ? _body(tab, me) : const SizedBox.shrink(),
    ],
  );

  Widget _body(ApplicantTab tab, ApplicantMe me) {
    // 지원이 여럿이면 **가장 최근 것**을 연다(서버가 최신 순으로 준다).
    // 홈은 전부 보여 주므로 거기서 어느 지원인지 알 수 있다
    final app = me.primary;

    /// 어느 것을 열 것인가.
    ///
    /// **아직 할 일이 남은 것을 먼저 고른다.** 2026-09-09 부터 서버가 끝난
    /// 것(`done`)도 같이 내리는데(02-api.md), 재발급으로 여러 개가 있으면
    /// 옛 것이 목록 앞에 온다(id 순) — 그대로 첫 번째를 열면 **새로 받은
    /// 면접을 두고 어제 끝낸 것을 연다.**
    ///
    /// 다 끝났으면 마지막 것을 준다. 화면이 "완료" 라고 말할 수 있어야 한다 —
    /// null 을 주면 "아직 없습니다" 가 되어 방금 마친 사람이 헷갈린다.
    String? pick(List<TokenLink> links) {
      if (links.isEmpty) return null;
      for (final l in links) {
        if (l.status != 'done') return l.token;
      }
      return links.last.token;
    }

    return switch (tab) {
      ApplicantTab.aptitude => AptitudeScreen(
        token: app == null ? null : pick(app.aptitudes),
        portal: _portal,
      ),
      ApplicantTab.schedule => ScheduleScreen(
        token: app == null ? null : pick(app.schedules),
        portal: _portal,
      ),
      ApplicantTab.home => ApplicantSummaryScreen(
        me: me,
        onOpen: _go,
        onRefresh: _load,
      ),
      ApplicantTab.interview => InterviewLiveScreen(
        token: app == null ? null : pick(app.interviews),
        portal: _portal,
      ),
      ApplicantTab.more => ApplicantMoreScreen(me: me, onLeave: _leave),
    };
  }
}

/// 링크를 아직 못 받은 탭. **오류처럼 그리지 않는다** — 담당자가 아직 안 보낸
/// 것이지 지원자가 뭘 잘못한 게 아니다
class ApplicantMissing extends StatelessWidget {
  const ApplicantMissing({super.key, required this.what});

  /// 무엇이 없는지 — "인적성 검사" · "면접 시간 제안"
  final String what;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(AppSpace.s6),
        child: Text(
          '아직 $what${subjectParticle(what)} 없습니다.\n담당자가 보내면 여기에 나타납니다.',
          textAlign: TextAlign.center,
          style: const TextStyle(
            fontFamily: AppType.fontFamily,
            fontSize: AppType.sm,
            height: 1.6,
            color: AppColors.textSub,
          ),
        ),
      ),
    );
  }
}

/// 못 받아 왔을 때. 앱엔 새로고침이 없어 다시 시도할 자리를 준다 (§6)
class _Failed extends StatelessWidget {
  const _Failed({required this.message, required this.onRetry});

  final String message;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(AppSpace.s5),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              message,
              textAlign: TextAlign.center,
              style: const TextStyle(
                fontFamily: AppType.fontFamily,
                fontSize: AppType.sm,
                color: AppColors.danger,
              ),
            ),
            const SizedBox(height: AppSpace.s4),
            SizedBox(
              height: AppLayout.minTouchTarget,
              child: OutlinedButton(
                onPressed: onRetry,
                child: const Text('다시 시도'),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
