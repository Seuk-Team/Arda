/// 하단 탭바 — 앱 UI 초안(2026-09-01) 조각 1.
///
/// 05-design §9 는 768px 아래에서 "사이드바 접기"까지만 정하고 무엇으로 대체할지는
/// 비워 뒀다. 웹 사이드바 6개(대시보드·채용 공고·지원자·캘린더·평가 현황·설정)를
/// 5칸으로 접는다 — 탭 5칸이 한계라 6개를 다 펴면 라벨이 깨진다.
///
///   공고 · 지원자 · **홈** · 캘린더 · 더보기   (평가 현황·설정은 더보기 안)
///
/// 홈이 가운데인 이유: 어디서든 돌아오는 자리라 한쪽으로 치우칠 이유가 없고,
/// 엄지가 제일 편한 자리다. 왼쪽은 "공고·사람", 오른쪽은 "일정·그 외".
///
/// 아이콘은 Material 아웃라인 — 05-design 에 아이콘 규칙이 없어 §0-6(플랫폼 공식
/// 디자인 문서 우선)대로 Android 기본을 쓴다.
///
/// **이 조각의 범위는 바 자체까지다.** 탭을 눌러 화면이 바뀌는 것은 다음 조각(§0-5).
library;

import 'package:flutter/material.dart';

import '../theme/tokens.dart';

/// 탭 다섯 칸. 순서가 곧 화면 배치 순서다.
enum AppTab {
  postings(Icons.description_outlined, '공고'),
  applicants(Icons.people_outline, '지원자'),
  home(Icons.home_outlined, '홈'),
  calendar(Icons.calendar_today_outlined, '캘린더'),
  more(Icons.menu, '더보기');

  const AppTab(this.icon, this.label);

  final IconData icon;
  final String label;
}

class AppBottomNav extends StatelessWidget {
  const AppBottomNav({super.key, required this.current, this.onSelected});

  final AppTab current;
  final ValueChanged<AppTab>? onSelected;

  /// 항목 높이. 05-design §9 터치 타깃 최소 44 를 넘긴다
  /// (아이콘 24 + 간격 4 + 라벨 한 줄 ≈ 45, 위아래 여백 포함 62).
  static const _itemHeight = 62.0;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      // 흰 바탕과 윗선은 제스처 바 뒤까지 이어지고, 항목만 SafeArea 안으로 들어간다.
      // SafeArea 를 높이 제약 안에 두면 항목이 제스처 바에 눌려 44 아래로 내려간다.
      decoration: const BoxDecoration(
        color: AppColors.bgElev,
        border: Border(
          top: BorderSide(color: AppColors.border, width: AppShape.borderW),
        ),
      ),
      child: SafeArea(
        top: false,
        child: SizedBox(
          height: _itemHeight,
          child: Row(
            children: [
              for (final tab in AppTab.values)
                Expanded(
                  child: _NavItem(
                    tab: tab,
                    selected: tab == current,
                    onTap: onSelected,
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }
}

class _NavItem extends StatelessWidget {
  const _NavItem({required this.tab, required this.selected, this.onTap});

  final AppTab tab;
  final bool selected;
  final ValueChanged<AppTab>? onTap;

  @override
  Widget build(BuildContext context) {
    // 05-design §1: 강조는 색으로. 연두(--sprout)는 글자 대비가 모자라 짙은 잎을 쓴다
    final color = selected ? AppColors.leaf : AppColors.textSub;

    return Semantics(
      button: true,
      selected: selected,
      label: tab.label,
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          onTap: onTap == null ? null : () => onTap!(tab),
          // §5: 모바일은 hover 없음 전제 — press 만 정의한다
          highlightColor: AppColors.bgSunken,
          splashColor: AppColors.bgSunken,
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(tab.icon, size: 24, color: color),
              const SizedBox(height: AppSpace.s1),
              Text(
                tab.label,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(
                  fontFamily: AppType.fontFamily,
                  fontSize: AppType.caption,
                  // 선택 시 굵기만 올린다. 크기는 스케일 밖으로 나가지 않는다(§2)
                  fontWeight: selected ? AppType.wSemiBold : AppType.wRegular,
                  color: color,
                  // §2: 본문·캡션 등 작은 글씨엔 그림자 금지
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
