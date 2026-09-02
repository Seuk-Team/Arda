/// 모바일 상단 바 — 시안(2026-08-28).
///
/// 시안의 전 화면이 `[←] 화면 제목  [동작]` 형태다.
/// 목업(`.mbar`)은 로고 `Arda` 를 달았지만, 화면이 여럿으로 늘면서 지금 어느
/// 화면인지가 로고보다 중요해졌다. 로고는 로그인 화면에만 남는다.
///
/// 05-design §9: 모바일에는 사이드바를 넣지 않는다. 상단 바가 그 자리를 대신한다.
library;

import 'package:flutter/material.dart';

import '../theme/tokens.dart';

class AppTopBar extends StatelessWidget implements PreferredSizeWidget {
  const AppTopBar({
    super.key,
    required this.title,
    this.showBack = false,
    this.onSearchPressed,
    this.onAddPressed,
  });

  final String title;

  /// 공고 → 지원자로 파고들 때만 뒤로가기를 단다. 첫 화면에는 없다
  final bool showBack;

  final VoidCallback? onSearchPressed;

  /// 만들기 진입점 — 공고 탭의 [+] (2026-09-02). 검색 오른쪽에 온다:
  /// 거르는 것보다 만드는 것이 덜 잦아 손에서 먼 쪽이 맞다
  final VoidCallback? onAddPressed;

  /// 터치 타깃 44 + 위아래 여백 8 = 60
  static const _height = AppLayout.minTouchTarget + AppSpace.s2 * 2;

  @override
  Size get preferredSize => const Size.fromHeight(_height);

  @override
  Widget build(BuildContext context) {
    return Container(
      // 흰 바탕은 상태 표시줄 뒤까지 이어지고, 내용만 SafeArea 안으로 들어간다.
      // Scaffold 는 appBar 자리에 preferredSize + 상태 표시줄 높이를 준다 —
      // SafeArea 로 그 여백을 소비하지 않으면 내용이 시계·배터리와 겹친다.
      decoration: const BoxDecoration(
        color: AppColors.bgElev,
        border: Border(
          bottom: BorderSide(color: AppColors.border, width: AppShape.borderW),
        ),
      ),
      child: SafeArea(
        bottom: false,
        child: SizedBox(
          height: _height,
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: AppSpace.s2),
            child: Row(
              children: [
                if (showBack) ...[
                  AppIconButton(
                    icon: Icons.arrow_back,
                    semanticLabel: '뒤로',
                    onPressed: () => Navigator.pop(context),
                  ),
                  const SizedBox(width: AppSpace.s1),
                ] else
                  const SizedBox(width: AppSpace.s2),

                Expanded(
                  child: Text(
                    title,
                    // 05-design §7: 제목은 한 줄 ellipsis
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    softWrap: false,
                    style: const TextStyle(
                      fontFamily: AppType.fontFamily,
                      fontSize: AppType.h1,
                      fontWeight: FontWeight.w700,
                      letterSpacing: -0.22,
                      color: AppColors.text,
                      shadows: AppTextShadow.heading,
                    ),
                  ),
                ),

                if (onSearchPressed != null)
                  AppIconButton(
                    icon: Icons.search,
                    semanticLabel: '검색',
                    onPressed: onSearchPressed,
                  ),
                if (onAddPressed != null)
                  AppIconButton(
                    icon: Icons.add,
                    semanticLabel: '공고 등록',
                    onPressed: onAddPressed,
                  ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// 상단 바의 아이콘 버튼 — 44×44 터치 타깃(05-design §9), 테두리 없음.
class AppIconButton extends StatelessWidget {
  const AppIconButton({
    super.key,
    required this.icon,
    required this.semanticLabel,
    required this.onPressed,
  });

  final IconData icon;
  final String semanticLabel;
  final VoidCallback? onPressed;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      button: true,
      label: semanticLabel,
      child: Material(
        color: Colors.transparent,
        shape: const CircleBorder(),
        clipBehavior: Clip.antiAlias,
        child: InkWell(
          onTap: onPressed,
          // §5: 모바일은 hover 없음 전제 — press 만 정의한다
          highlightColor: AppColors.bgSunken,
          splashColor: AppColors.bgSunken,
          child: SizedBox(
            width: AppLayout.minTouchTarget,
            height: AppLayout.minTouchTarget,
            child: Icon(icon, size: 24, color: AppColors.text),
          ),
        ),
      ),
    );
  }
}
