// 로그인 — 목업 JS 와 같은 규칙: 둘 다 채워야 버튼이 살아난다.
// 실제 인증은 큐 7번이라 여기서는 화면 동작만 본다.

import 'package:arda/main.dart';
import 'package:arda/routes.dart';
import 'package:arda/screens/login_screen.dart';
import 'package:arda/theme/app_theme.dart';
import 'package:arda/widgets/app_bottom_nav.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'app_boot.dart';

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

  testWidgets('로그인하면 홈(대시보드)으로 넘어간다', (tester) async {
    await tester.pumpWidget(const ArdaApp());

    final ctx = tester.element(find.byType(Navigator).first);
    Navigator.pushNamed(ctx, Routes.login);
    await tester.pumpAndSettle();

    await tester.enterText(find.byType(TextField).first, 'a@b.com');
    await tester.enterText(find.byType(TextField).last, 'pw');
    await tester.pump();

    await tester.tap(find.text('로그인'));
    await tester.pumpAndSettle();

    expect(find.text('대시보드'), findsWidgets);
    expect(find.byType(LoginScreen), findsNothing);
  });

  testWidgets('앱을 켜면 로그인이 먼저다 — 탭바는 아직 없다', (tester) async {
    await tester.pumpWidget(const ArdaApp());

    expect(find.byType(LoginScreen), findsOneWidget);
    expect(find.byType(AppBottomNav), findsNothing);
  });

  testWidgets('로고 아래 부제 — 무슨 서비스인지 알려 준다', (tester) async {
    await tester.pumpWidget(const ArdaApp());
    expect(find.text('채용 관리'), findsOneWidget);
  });

  testWidgets('로그아웃하면 로그인으로 돌아가고 스택이 비워진다', (tester) async {
    await bootToShell(tester, tab: '더보기');

    await tester.tap(find.text('로그아웃'));
    await tester.pumpAndSettle();

    expect(find.byType(LoginScreen), findsOneWidget);
    // 뒤로가기로 앱 안에 다시 들어올 수 없어야 한다
    expect(find.byType(AppBottomNav), findsNothing);
    final navigator = tester.state<NavigatorState>(
      find.byType(Navigator).first,
    );
    expect(navigator.canPop(), isFalse);
  });

  testWidgets('아르 마크 · 로고 · 부제가 같은 세로선에 선다', (tester) async {
    await tester.pumpWidget(const ArdaApp());

    final markX = tester.getCenter(find.byType(Image)).dx;
    final logoX = tester.getCenter(find.textContaining('rda')).dx;
    final tagX = tester.getCenter(find.text('채용 관리')).dx;

    expect(logoX, moreOrLessEquals(markX, epsilon: 1));
    expect(tagX, moreOrLessEquals(markX, epsilon: 1));
  });
}
