/// 모바일 상단 바 — `mockup-mobile.html` 의 `.mbar` 를 옮긴 것.
///
/// 05-design §9: 모바일에는 사이드바를 넣지 않는다. 상단 바가 그 자리를 대신한다.
library;

import 'package:flutter/material.dart';

import '../theme/tokens.dart';

class AppTopBar extends StatelessWidget implements PreferredSizeWidget {
  const AppTopBar({super.key, this.onSearchPressed});

  final VoidCallback? onSearchPressed;

  /// `.mbar` 는 세로 패딩 `--sp-2`(8) + 터치 타깃 44 = 60
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
            padding: const EdgeInsets.symmetric(horizontal: AppSpace.s3),
            child: Row(
              children: [
                const Padding(
                  padding: EdgeInsets.symmetric(horizontal: AppSpace.s3),
                  child: _Logo(),
                ),
                const Spacer(),
                _IconButton(
                  onPressed: onSearchPressed,
                  semanticLabel: '검색',
                  icon: Icons.search,
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// 목업 `.logo` — 첫 글자 `A` 만 잎초록, 나머지는 잉크.
class _Logo extends StatelessWidget {
  const _Logo();

  @override
  Widget build(BuildContext context) {
    const base = TextStyle(
      fontFamily: AppType.fontFamily,
      fontSize: AppType.h1,
      fontWeight: FontWeight.w700,
      letterSpacing: -0.22, // 목업 letter-spacing:-.01em × 22px
      color: AppColors.text,
      shadows: AppTextShadow.heading,
    );

    return Text.rich(
      const TextSpan(
        children: [
          TextSpan(text: 'A', style: TextStyle(color: AppColors.leaf)),
          TextSpan(text: 'rda'),
        ],
        style: base,
      ),
      maxLines: 1,
      softWrap: false,
    );
  }
}

/// 목업 `.micon` — 44×44 터치 타깃, 테두리 1px, press 시 채움.
/// 05-design §5: 모바일은 hover 없음 전제라 press 만 정의한다.
class _IconButton extends StatelessWidget {
  const _IconButton({
    required this.onPressed,
    required this.semanticLabel,
    required this.icon,
  });

  final VoidCallback? onPressed;
  final String semanticLabel;
  final IconData icon;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      button: true,
      label: semanticLabel,
      child: Material(
        color: AppColors.bgElev,
        shape: const RoundedRectangleBorder(
          borderRadius: AppShape.ctl,
          side: BorderSide(color: AppColors.border, width: AppShape.borderW),
        ),
        clipBehavior: Clip.antiAlias,
        child: InkWell(
          onTap: onPressed,
          highlightColor: AppColors.sunkenHover,
          splashColor: AppColors.sunkenHover,
          child: SizedBox(
            width: AppLayout.minTouchTarget,
            height: AppLayout.minTouchTarget,
            child: Icon(icon, size: 20, color: AppColors.text),
          ),
        ),
      ),
    );
  }
}
