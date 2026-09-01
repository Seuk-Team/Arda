/// 탭 셸 — 앱 UI 초안(2026-09-01) 조각 2.
///
/// 하단 탭바가 앉을 자리를 만든다. 상단 바 제목과 본문이 탭을 따라 바뀐다.
/// 제목은 05-design §0.5 화면 지도의 메뉴 이름을 그대로 쓴다(채용 공고·지원자·캘린더).
///
/// **아직 만들지 않은 탭은 바탕만 있는 빈 영역이다** — §0-5 는 블록의 첫 조각을
/// "위치·크기·바탕색만 잡는 빈 영역"으로 정의하고 자리 표시 문구까지 금지한다.
/// "준비 중" 같은 글자를 넣지 않은 것은 빠뜨린 게 아니라 규칙이다.
///
/// 탭이 바뀌어도 각 탭의 스크롤 위치는 남는다([IndexedStack]) — 공고를 한참
/// 내려보다 캘린더에 다녀오면 보던 자리로 돌아와야 한다.
///
/// 공고에서 지원자·상세로 파고드는 것은 이 셸 위에 쌓는 별도 라우트다.
/// 그 화면들에는 탭바가 없다(초안 그대로 — 하단이 동작 버튼 자리다).
library;

import 'package:flutter/material.dart';

import '../routes.dart';
import '../theme/tokens.dart';
import '../widgets/app_bottom_nav.dart';
import '../widgets/app_top_bar.dart';
import 'applicants_search_screen.dart';
import 'ar_screen.dart';
import 'calendar_screen.dart';
import 'dashboard_screen.dart';
import 'more_screen.dart';
import 'postings_screen.dart';

class HomeShell extends StatefulWidget {
  const HomeShell({super.key, this.initialTab = AppTab.postings});

  final AppTab initialTab;

  @override
  State<HomeShell> createState() => _HomeShellState();
}

class _HomeShellState extends State<HomeShell> {
  late AppTab _current = widget.initialTab;

  /// 상단 바에 걸리는 이름. 탭 라벨(짧게 줄인 것)과 다르다 —
  /// 탭은 5칸에 들어가야 해서 "공고", 화면 제목은 05-design 의 "채용 공고".
  static const _titles = <AppTab, String>{
    AppTab.postings: '채용 공고',
    AppTab.applicants: '지원자',
    AppTab.home: '대시보드',
    AppTab.calendar: '캘린더',
    AppTab.more: '더보기',
  };

  /// 탭 이동 — 하단 바와 카드 안 링크("캘린더 →")가 같은 문을 쓴다
  void _go(AppTab tab) => setState(() => _current = tab);

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppTopBar(title: _titles[_current]!),
      body: IndexedStack(
        index: AppTab.values.indexOf(_current),
        children: [
          const PostingsScreen(),
          ApplicantsSearchScreen(
            onOpenApplicant: (applicant, postingTitle) => Navigator.pushNamed(
              context,
              Routes.applicantDetail,
              arguments: (applicant, postingTitle),
            ),
          ),
          DashboardScreen(
            onOpenCalendar: () => _go(AppTab.calendar),
            // 평가 현황은 탭 5칸에 못 들어가 더보기 안에 있다(조각 1 메모)
            onOpenReviews: () => _go(AppTab.more),
            onOpenApplicants: () => _go(AppTab.applicants),
            onOpenPostings: () => _go(AppTab.postings),
          ),
          const CalendarScreen(),
          const MoreScreen(),
        ],
      ),
      // 05-design §0.5: 아르는 **전 화면 공통 진입점**이다. 탭이 있는 화면에서는
      // 엄지가 닿는 오른쪽 아래에 둔다 — 파고든 화면(상세)은 하단이 동작 버튼
      // 자리라 상단 바 오른쪽 아바타가 그 자리를 대신한다
      floatingActionButton: _ArButton(onPressed: () => showArSheet(context)),
      bottomNavigationBar: AppBottomNav(current: _current, onSelected: _go),
    );
  }
}

/// 아르 진입점 — 탭바 위 오른쪽에 뜨는 동그란 버튼.
///
/// Material 의 [FloatingActionButton] 을 쓰지 않는다: 기본 색·그림자·모양이
/// Material 3 토큰을 따라가서 05-design 값과 어긋난다. 여기서는 사이드바 색
/// (아르가 사는 자리)과 §4 오버레이 그림자를 그대로 쓴다.
class _ArButton extends StatelessWidget {
  const _ArButton({required this.onPressed});

  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      button: true,
      label: '아르에게 물어보기',
      child: Container(
        decoration: const BoxDecoration(
          shape: BoxShape.circle,
          boxShadow: AppShadow.overlay,
        ),
        child: Material(
          color: AppColors.sidebarBg,
          shape: const CircleBorder(
            side: BorderSide(
              color: AppColors.sidebarLine,
              width: AppShape.borderW,
            ),
          ),
          clipBehavior: Clip.antiAlias,
          child: InkWell(
            onTap: onPressed,
            child: const SizedBox(
              // 초안: 56 — §9 터치 타깃 44 를 넉넉히 넘긴다
              width: 56,
              height: 56,
              child: ArAvatar(size: 56),
            ),
          ),
        ),
      ),
    );
  }
}
