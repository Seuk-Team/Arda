// 뼈대 단계의 테스트 — 화면 3개가 서로 이동되는지만 확인한다.
// 목록·상세 내용은 아직 없으므로 검증하지 않는다.

import 'package:arda/main.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('첫 화면은 공고 리스트다', (tester) async {
    await tester.pumpWidget(const ArdaApp());

    expect(find.text('채용 공고'), findsOneWidget);
  });

  testWidgets('공고 → 지원자 → 상세 로 이동하고 되돌아온다', (tester) async {
    await tester.pumpWidget(const ArdaApp());

    await tester.tap(find.text('지원자 보기'));
    await tester.pumpAndSettle();
    expect(find.text('지원자'), findsOneWidget);

    await tester.tap(find.text('지원자 상세 보기'));
    await tester.pumpAndSettle();
    expect(find.text('지원자 상세'), findsOneWidget);

    // 상세는 마지막 화면이라 AppBar 뒤로가기로만 나온다
    await tester.tap(find.byTooltip('Back'));
    await tester.pumpAndSettle();
    expect(find.text('지원자'), findsOneWidget);
  });

  testWidgets('테마가 05-design 토큰을 쓴다', (tester) async {
    await tester.pumpWidget(const ArdaApp());

    final theme = Theme.of(tester.element(find.byType(Scaffold)));
    expect(theme.scaffoldBackgroundColor, const Color(0xFFF4F7F0)); // --bg
    expect(theme.colorScheme.primary, const Color(0xFF3A6B21)); // --leaf
    expect(theme.textTheme.bodyLarge?.fontSize, 16); // --font-body
    expect(theme.textTheme.bodyLarge?.fontFamily, 'IBM Plex Sans KR');
  });
}
