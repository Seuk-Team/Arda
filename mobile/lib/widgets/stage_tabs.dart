/// 단계 탭 — `mockup-mobile.html` 의 `.tabs` 를 옮긴 것.
///
/// 05-design §9: 모바일은 칸반을 쓰지 않는다. 이 탭이 칸반 열을 대신한다.
/// 선택 표시 규격은 목업이 `mockup.html` 의 `.vtoggle button.on` 을 따온 것이다.
library;

import 'package:flutter/material.dart';

import '../models/stage.dart';
import '../theme/tokens.dart';

class StageTabs extends StatelessWidget {
  const StageTabs({
    super.key,
    required this.selected,
    required this.onSelected,
    required this.counts,
  });

  /// **null 이면 「전체」다.** 웹은 공고를 열면 전 단계를 한 표에 보여 주고
  /// 단계는 필터로만 쓴다 — 앱도 같게 맞췄다(2026-09-02). 지원 접수만 먼저
  /// 보여 주면 다른 단계에 사람이 있는지 알려면 탭을 하나씩 눌러 봐야 한다
  final Stage? selected;

  final ValueChanged<Stage?> onSelected;

  /// 단계 → 인원. 시안: 막대는 비율만, **숫자는 탭이** 보여 준다
  final Map<Stage, int> counts;

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: const BoxDecoration(
        color: AppColors.bgElev,
        border: Border(
          bottom: BorderSide(color: AppColors.border, width: AppShape.borderW),
        ),
      ),
      // 탭 줄만 가로로 스크롤한다. 페이지 자체는 가로 스크롤하지 않는다
      // (05-design §3: 가로 스크롤은 칸반 영역에만 허용 — 여기선 탭 줄에 한정)
      child: SingleChildScrollView(
        scrollDirection: Axis.horizontal,
        padding: const EdgeInsets.symmetric(
          horizontal: AppSpace.s4,
          vertical: AppSpace.s2,
        ),
        child: Row(
          children: [
            // 전체가 맨 앞 — 웹 표의 기본 상태와 같다
            _Tab(
              label: '전체',
              count: counts.values.fold(0, (a, b) => a + b),
              isSelected: selected == null,
              onTap: () => onSelected(null),
            ),
            const SizedBox(width: AppSpace.s2),
            for (final stage in Stage.values) ...[
              _Tab(
                label: stage.label,
                count: counts[stage] ?? 0,
                isSelected: stage == selected,
                onTap: () => onSelected(stage),
              ),
              if (stage != Stage.values.last)
                const SizedBox(width: AppSpace.s2),
            ],
          ],
        ),
      ),
    );
  }
}

class _Tab extends StatelessWidget {
  const _Tab({
    required this.label,
    required this.count,
    required this.isSelected,
    required this.onTap,
  });

  final String label;
  final int count;
  final bool isSelected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      selected: isSelected,
      button: true,
      child: Material(
        // 선택된 탭만 연두 워시. 나머지는 패널과 같은 흰색이다
        color: isSelected ? AppColors.sproutSoft : AppColors.bgElev,
        borderRadius: AppShape.ctl,
        clipBehavior: Clip.antiAlias,
        child: InkWell(
          onTap: onTap,
          // §5: 모바일은 hover 없음 전제 — press 만 정의한다
          highlightColor: AppColors.bgSunken,
          splashColor: AppColors.bgSunken,
          child: Container(
            height: AppType.menuItemHeight,
            alignment: Alignment.center,
            padding: const EdgeInsets.symmetric(horizontal: AppSpace.s4),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(
                  label,
                  // 탭 라벨은 한 줄 고정. 두 줄이 되면 버그다 (§2)
                  softWrap: false,
                  style: TextStyle(
                    fontFamily: AppType.fontFamily,
                    fontSize: AppType.sm,
                    fontWeight: AppType.wSemiBold,
                    color: isSelected ? AppColors.leaf : AppColors.textSub,
                    shadows: isSelected ? AppTextShadow.heading : null,
                  ),
                ),
                const SizedBox(width: AppSpace.s2),
                // 시안: 막대가 못 담는 값을 탭이 읽히게 한다
                Text(
                  "$count",
                  softWrap: false,
                  style: TextStyle(
                    fontFamily: AppType.fontFamily,
                    fontSize: AppType.sm,
                    fontWeight: AppType.wSemiBold,
                    color: isSelected ? AppColors.leaf : AppColors.textSub,
                    fontFeatures: AppType.tabularNums,
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
