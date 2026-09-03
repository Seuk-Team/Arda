// 내 계정 — 이름·비밀번호 저장 (큐 8 3단계, 2026-09-03).
//
// **401 이 이 화면의 함정이다.** 다른 화면에서 401 은 "세션 만료" 라 토큰을
// 지우고 로그인으로 보내지만, 여기서는 "현재 비밀번호를 틀렸다" 다.
// 그대로 두면 오타 한 번에 로그아웃된다.

import 'package:arda/api/api_error.dart';
import 'package:arda/auth/current_user.dart';
import 'package:arda/screens/settings_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'fake_auth.dart';

Future<void> open(WidgetTester tester, FakeAuthService auth) async {
  await tester.pumpWidget(
    CurrentUserScope(
      notifier: CurrentUser(testUser),
      auth: auth,
      child: MaterialApp(
        home: SettingsScreen(user: testUser, auth: auth),
      ),
    ),
  );
  await tester.pumpAndSettle();
}

Finder field(String label) => find.descendant(
  of: find.ancestor(of: find.text(label), matching: find.byType(Column)).first,
  matching: find.byType(TextField),
);

/// 비밀번호 세 칸을 채운다. 확인칸은 서버로 안 가고 화면에서만 대조한다
Future<void> fillPassword(
  WidgetTester tester, {
  required String current,
  required String next,
  String? confirm,
}) async {
  await scrollToPassword(tester);
  await tester.enterText(field('현재 비밀번호'), current);
  await tester.enterText(field('새 비밀번호'), next);
  await tester.enterText(field('새 비밀번호 확인'), confirm ?? next);
  await tester.pumpAndSettle();
}

/// ListView 라 아래쪽 칸·버튼은 화면에 들어와야 만들어진다
Future<void> scrollToPassword(WidgetTester tester) async {
  await tester.dragUntilVisible(
    find.widgetWithText(FilledButton, '변경'),
    find.byType(ListView).last,
    const Offset(0, -200),
  );
  await tester.pumpAndSettle();
}

Future<void> tapChange(WidgetTester tester) async {
  await tester.tap(find.widgetWithText(FilledButton, '변경'));
  await tester.pumpAndSettle();
}

void main() {
  group('이름', () {
    testWidgets('안 바꿨으면 [저장] 이 잠겨 있다 — 보낼 것이 없다', (tester) async {
      final auth = FakeAuthService();
      await open(tester, auth);

      final save = tester.widget<FilledButton>(
        find.widgetWithText(FilledButton, '저장'),
      );
      expect(save.onPressed, isNull);
      expect(auth.updateCalls, 0);
    });

    testWidgets('바꾸면 그 값만 간다 — 비밀번호는 안 보낸다', (tester) async {
      final auth = FakeAuthService();
      await open(tester, auth);

      await tester.enterText(field('이름'), '김민아2');
      await tester.pumpAndSettle();
      await tester.tap(find.widgetWithText(FilledButton, '저장'));
      await tester.pumpAndSettle();

      expect(auth.sentName, '김민아2');
      expect(auth.sentNewPassword, isNull);
      expect(find.textContaining('이름을 저장했습니다'), findsOneWidget);
    });

    testWidgets('이메일·역할은 잠긴 채다 — 서버가 아예 안 받는다', (tester) async {
      await open(tester, FakeAuthService());

      // 살아 있는 칸으로 두면 바꿀 수 있는 줄 안다
      expect(field('이메일'), findsNothing);
      expect(field('역할'), findsNothing);
      expect(find.text('이메일과 역할은 본인이 바꿀 수 없습니다.'), findsOneWidget);
    });
  });

  group('비밀번호', () {
    testWidgets('칸이 비면 [변경] 이 잠겨 있다', (tester) async {
      final auth = FakeAuthService();
      await open(tester, auth);
      await scrollToPassword(tester);

      final change = tester.widget<FilledButton>(
        find.widgetWithText(FilledButton, '변경'),
      );
      expect(change.onPressed, isNull);
      expect(auth.updateCalls, 0);
    });

    testWidgets('8자 미만이면 보내지 않는다 — 서버도 422 로 막는다', (tester) async {
      final auth = FakeAuthService();
      await open(tester, auth);

      await fillPassword(tester, current: 'old-one', next: 'short7');
      await tapChange(tester);

      expect(find.text('새 비밀번호는 8자 이상이어야 합니다.'), findsOneWidget);
      expect(auth.updateCalls, 0);
    });

    testWidgets('확인칸이 다르면 보내지 않는다', (tester) async {
      final auth = FakeAuthService();
      await open(tester, auth);

      await fillPassword(
        tester,
        current: 'old-one',
        next: 'newpassword',
        confirm: 'newpassword-oops',
      );
      await tapChange(tester);

      expect(find.text('새 비밀번호가 서로 다릅니다.'), findsOneWidget);
      expect(auth.updateCalls, 0);
    });

    testWidgets('현재·새 비밀번호가 짝으로 간다 — 확인칸은 안 보낸다', (tester) async {
      final auth = FakeAuthService();
      await open(tester, auth);

      await fillPassword(tester, current: 'old-one', next: 'newpassword');
      await tapChange(tester);

      expect(auth.sentCurrentPassword, 'old-one');
      expect(auth.sentNewPassword, 'newpassword');
      // 이름은 안 건드렸으니 안 보낸다
      expect(auth.sentName, isNull);
    });

    testWidgets('성공하면 세 칸을 비운다 — 남이 화면을 잡으면 그대로 보인다', (tester) async {
      await open(tester, FakeAuthService());

      await fillPassword(tester, current: 'old-one', next: 'newpassword');
      await tapChange(tester);

      expect(find.textContaining('비밀번호를 바꿨습니다'), findsOneWidget);
      final controller = tester.widget<TextField>(field('현재 비밀번호')).controller;
      expect(controller!.text, isEmpty);
    });

    testWidgets('현재 비밀번호가 틀리면 그 문구를 띄운다 — 로그아웃되면 안 된다', (tester) async {
      final auth = FakeAuthService(
        // api_client 가 401 을 만료가 아니라 이것으로 바꿔 준다
        updateError: const ServerError(401, '현재 비밀번호가 올바르지 않습니다'),
      );
      await open(tester, auth);

      await fillPassword(tester, current: 'wrong-one', next: 'newpassword');
      await tapChange(tester);

      expect(find.text('현재 비밀번호가 올바르지 않습니다'), findsOneWidget);
      // 화면이 그대로 남아 있어야 한다 — 로그인 화면으로 튕기면 안 된다
      expect(find.text('비밀번호 변경'), findsOneWidget);
      expect(auth.loggedOut, isFalse);
    });

    testWidgets('네트워크가 끊겨도 로그아웃되지 않는다', (tester) async {
      final auth = FakeAuthService(updateError: const NetworkError());
      await open(tester, auth);

      await fillPassword(tester, current: 'old-one', next: 'newpassword');
      await tapChange(tester);

      expect(find.textContaining('네트워크를 확인'), findsOneWidget);
      expect(auth.loggedOut, isFalse);
    });
  });
}
