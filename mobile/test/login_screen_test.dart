// 로그인 — 목업 JS 와 같은 규칙: 둘 다 채워야 버튼이 살아난다.
// 실제 인증은 큐 7번이라 여기서는 화면 동작만 본다.

import 'package:arda/routes.dart';
import 'package:arda/screens/login_screen.dart';
import 'package:arda/theme/app_theme.dart';
import 'package:arda/widgets/posting_card.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:arda/main.dart';

void main() {
  Widget app() => MaterialApp(
    theme: buildAppTheme(),
    initialRoute: Routes.login,
    home: null,
    onGenerateRoute: (settings) => MaterialPageRoute(
      settings: settings,
      builder: (_) => const LoginScreen(),
    ),
  );

  testWidgets('빈 칸이면 로그인 버튼이 비활성이다', (tester) async {
    await tester.pumpWidget(app());

    final button = tester.widget<FilledButton>(find.byType(FilledButton));
    expect(button.onPressed, isNull);
  });

  testWidgets('이메일만 채우면 아직 비활성이다', (tester) async {
    await tester.pumpWidget(app());

    await tester.enterText(find.byType(TextField).first, 'a@b.com');
    await tester.pump();

    final button = tester.widget<FilledButton>(find.byType(FilledButton));
    expect(button.onPressed, isNull);
  });

  testWidgets('둘 다 채우면 활성이 된다', (tester) async {
    await tester.pumpWidget(app());

    await tester.enterText(find.byType(TextField).first, 'a@b.com');
    await tester.enterText(find.byType(TextField).last, 'pw');
    await tester.pump();

    final button = tester.widget<FilledButton>(find.byType(FilledButton));
    expect(button.onPressed, isNotNull);
  });

  testWidgets('로그인하면 지원자 목록으로 넘어간다', (tester) async {
    await tester.pumpWidget(const ArdaApp());

    final ctx = tester.element(find.byType(PostingCard).first);
    Navigator.pushNamed(ctx, Routes.login);
    await tester.pumpAndSettle();

    await tester.enterText(find.byType(TextField).first, 'a@b.com');
    await tester.enterText(find.byType(TextField).last, 'pw');
    await tester.pump();

    await tester.tap(find.text('로그인'));
    await tester.pumpAndSettle();

    expect(find.byType(PostingCard), findsWidgets);
    expect(find.byType(LoginScreen), findsNothing);
  });
}
