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
  });

  final Stage selected;
  final ValueChanged<Stage> onSelected;

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
          horizontal: AppSpace.s3,
          vertical: AppSpace.s2,
        ),
        child: Row(
          children: [
            for (final stage in Stage.values) ...[
              _Tab(
                label: stage.label,
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
    required this.isSelected,
    required this.onTap,
  });

  final String label;
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
            height: AppLayout.minTouchTarget,
            alignment: Alignment.center,
            padding: const EdgeInsets.symmetric(horizontal: AppSpace.s4),
            child: Text(
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
          ),
        ),
      ),
    );
  }
}
