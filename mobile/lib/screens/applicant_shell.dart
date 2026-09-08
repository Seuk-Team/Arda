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
/// ## 탭마다 토큰이 따로다
///
/// 서버에 지원자 계정이 없어서 화면마다 **자기 링크의 토큰**이 인증이다
/// (지원 현황·인적성·일정·면접이 서로 다른 토큰이다). 셸이 저장소에서 한 번
/// 읽어 종류별로 나눠 준다 — 탭마다 저장소를 다시 열면 같은 것을 네 번 읽는다.
///
/// 받은 적 없는 링크의 탭은 **비어 있다고 말한다.** 담당자가 아직 안 보낸
/// 것이지 지원자가 뭘 잘못한 게 아니라서, 오류처럼 그리지 않는다.
///
/// ## 탭은 처음 열 때 받아 온다
///
/// [IndexedStack] 은 자식을 다 만들어 두는데, 그대로 두면 앱을 켜는 순간
/// 네 화면이 각자 서버를 부른다. 한 번이라도 연 탭만 만든다 — 열어 둔 탭은
/// 그대로 살아 있어 돌아왔을 때 다시 안 받는다.
library;

import 'package:flutter/material.dart';

import '../auth/applicant_store.dart';
import '../routes.dart';
import '../theme/tokens.dart';
import '../utils/format.dart';
import '../widgets/app_bottom_nav.dart';
import '../widgets/app_top_bar.dart';
import 'applicant_more_screen.dart';
import 'applicant_summary_screen.dart';
import 'aptitude_screen.dart';
import 'interview_screen.dart';
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
  const ApplicantShell({super.key, this.store, this.initialTab});

  /// 테스트가 가짜를 넣는 자리
  final ApplicantStore? store;
  final ApplicantTab? initialTab;

  @override
  State<ApplicantShell> createState() => _ApplicantShellState();
}

class _ApplicantShellState extends State<ApplicantShell> {
  late final ApplicantStore _store = widget.store ?? const ApplicantStore();

  late ApplicantTab _current = widget.initialTab ?? ApplicantTab.home;

  /// 한 번이라도 연 탭. 홈은 처음부터 열려 있다
  late final Set<ApplicantTab> _opened = {_current};

  /// 종류별 토큰. 아직 못 읽었으면 null 이다 — 그동안은 기다린다
  Map<ApplicantTokenKind, String>? _tokens;

  @override
  void initState() {
    super.initState();
    _read();
  }

  Future<void> _read() async {
    final tokens = ApplicantStore.byKind(await _store.read());
    if (!mounted) return;
    setState(() => _tokens = tokens);
  }

  void _go(ApplicantTab tab) => setState(() {
    _current = tab;
    _opened.add(tab);
  });

  @override
  Widget build(BuildContext context) {
    final tokens = _tokens;
    return Scaffold(
      appBar: AppTopBar(title: _current.title),
      body: tokens == null
          ? const Center(child: CircularProgressIndicator())
          : IndexedStack(
              index: ApplicantTab.values.indexOf(_current),
              children: [
                for (final tab in ApplicantTab.values)
                  // 안 연 탭은 자리만 잡아 둔다 — 만들면 서버를 부른다
                  _opened.contains(tab)
                      ? _body(tab, tokens)
                      : const SizedBox.shrink(),
              ],
            ),
      bottomNavigationBar: AppBottomNav(
        tabs: ApplicantTab.values,
        current: _current,
        onSelected: _go,
      ),
    );
  }

  Widget _body(ApplicantTab tab, Map<ApplicantTokenKind, String> tokens) =>
      switch (tab) {
        ApplicantTab.aptitude => AptitudeScreen(
          token: tokens[ApplicantTokenKind.aptitude],
        ),
        ApplicantTab.schedule => ScheduleScreen(
          token: tokens[ApplicantTokenKind.schedule],
        ),
        ApplicantTab.home => ApplicantSummaryScreen(
          tokens: tokens,
          onOpen: _go,
        ),
        ApplicantTab.interview => InterviewScreen(
          token: tokens[ApplicantTokenKind.interview],
          showChrome: false,
          // 보이는 동안만 카메라를 켠다 — 안 넘기면 다른 탭에 있는 내내
          // 카메라가 잡혀 있다(InterviewScreen.active 주석 참고)
          active: _current == ApplicantTab.interview,
        ),
        ApplicantTab.more => ApplicantMoreScreen(
          token: tokens[ApplicantTokenKind.portal],
          onLeave: _leave,
        ),
      };

  /// 지원자로서 나가기. **담당자 토큰은 건드리지 않는다** — 저장소가 아예 다르다
  Future<void> _leave() async {
    await _store.clear();
    if (!mounted) return;
    Navigator.pushReplacementNamed(context, Routes.login);
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
