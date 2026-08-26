/// [AppTokens] 를 Flutter 의 [ThemeData] 로 연결한다.
///
/// 화면 코드에서 색·크기를 직접 쓰지 않고 테마를 통해 받게 하는 것이 목적이다 —
/// 05-design §0-1 "모든 값은 토큰으로".
library;

import 'package:flutter/material.dart';

import 'tokens.dart';

/// 05-design §0-4: **테마는 라이트 온리.** 다크 테마를 만들지 않는다.
ThemeData buildAppTheme() {
  const colors = ColorScheme.light(
    primary: AppColors.leaf,
    onPrimary: AppColors.bgElev,
    secondary: AppColors.sprout,
    onSecondary: AppColors.text,
    surface: AppColors.bgElev,
    onSurface: AppColors.text,
    surfaceContainerLowest: AppColors.bg,
    surfaceContainerLow: AppColors.bgSunken,
    outline: AppColors.border,
    outlineVariant: AppColors.borderSoft,
    error: AppColors.danger,
    onError: AppColors.bgElev,
  );

  return ThemeData(
    useMaterial3: true,
    colorScheme: colors,
    scaffoldBackgroundColor: AppColors.bg,
    fontFamily: AppType.fontFamily,
    textTheme: _textTheme,
    appBarTheme: const AppBarTheme(
      backgroundColor: AppColors.bgElev,
      foregroundColor: AppColors.text,
      surfaceTintColor: Colors.transparent,
      elevation: 0,
      // 05-design §4: 그림자 2종만. AppBar 아래 경계는 그림자 대신 1px 라인으로 긋는다
      shape: Border(
        bottom: BorderSide(color: AppColors.border, width: AppShape.borderW),
      ),
      centerTitle: false,
      titleTextStyle: TextStyle(
        fontFamily: AppType.fontFamily,
        fontSize: AppType.h1,
        fontWeight: AppType.wSemiBold,
        color: AppColors.text,
        // §2: h1 에는 텍스트 그림자를 **항상**
        shadows: AppTextShadow.heading,
      ),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        backgroundColor: AppColors.leaf,
        foregroundColor: AppColors.bgElev,
        // §9: 터치 타깃 최소 44×44 (HIG)
        minimumSize: const Size(AppLayout.minTouchTarget, AppLayout.minTouchTarget),
        padding: const EdgeInsets.symmetric(
          horizontal: AppSpace.s5,
          vertical: AppSpace.s3,
        ),
        shape: const RoundedRectangleBorder(borderRadius: AppShape.ctl),
        textStyle: const TextStyle(
          fontFamily: AppType.fontFamily,
          fontSize: AppType.body,
          fontWeight: AppType.wSemiBold,
        ),
      ).copyWith(
        // §2: 색 채움 배경 위 밝은 글자에는 --ts-onfill 을 거의 항상
        textStyle: const WidgetStatePropertyAll(
          TextStyle(
            fontFamily: AppType.fontFamily,
            fontSize: AppType.body,
            fontWeight: AppType.wSemiBold,
            shadows: AppTextShadow.onFill,
          ),
        ),
      ),
    ),
    listTileTheme: const ListTileThemeData(
      minTileHeight: AppType.menuItemHeight,
      textColor: AppColors.text,
      iconColor: AppColors.textSub,
    ),
    dividerTheme: const DividerThemeData(
      color: AppColors.border,
      thickness: AppShape.borderW,
      space: AppShape.borderW,
    ),
  );
}

/// 05-design §2 스케일 7단계를 Material 슬롯에 얹은 것.
/// **이 표 밖의 크기를 쓰지 않는다.**
///
/// | 05-design      | Material 슬롯   |
/// |----------------|-----------------|
/// | display 26     | headlineLarge   |
/// | h1 22          | headlineMedium  |
/// | h2 18          | titleLarge      |
/// | body 16        | bodyLarge       |
/// | sm 14          | bodyMedium      |
/// | caption 12     | labelSmall      |
///
/// `--font-num` 은 크기가 sm 과 같고 자리 폭 고정만 다르므로 슬롯 대신
/// [AppType.tabularNums] 를 필요한 곳에 직접 붙인다.
const _textTheme = TextTheme(
  headlineLarge: TextStyle(
    fontSize: AppType.display,
    fontWeight: AppType.wSemiBold,
    color: AppColors.text,
    shadows: AppTextShadow.heading,
  ),
  headlineMedium: TextStyle(
    fontSize: AppType.h1,
    fontWeight: AppType.wSemiBold,
    color: AppColors.text,
    shadows: AppTextShadow.heading,
  ),
  titleLarge: TextStyle(
    fontSize: AppType.h2,
    fontWeight: AppType.wSemiBold,
    color: AppColors.text,
    shadows: AppTextShadow.heading,
  ),
  bodyLarge: TextStyle(
    fontSize: AppType.body,
    fontWeight: AppType.wRegular,
    color: AppColors.text,
  ),
  bodyMedium: TextStyle(
    fontSize: AppType.sm,
    fontWeight: AppType.wRegular,
    color: AppColors.textSub,
  ),
  labelSmall: TextStyle(
    fontSize: AppType.caption,
    fontWeight: AppType.wRegular,
    color: AppColors.textSub,
  ),
);
