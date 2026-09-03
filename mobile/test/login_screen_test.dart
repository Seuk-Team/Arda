// 로그인 — 목업 JS 와 같은 규칙: 둘 다 채워야 버튼이 살아난다.
//
// 큐 7(2026-09-02)로 진짜 호출이 붙었다. 여기서는 [FakeAuthService] 로 응답을
// 정해 주고 **화면이 어떻게 반응하는지**만 본다 — 서버가 맞게 답하는지는
// 백엔드 테스트의 몫이다.

import 'package:arda/api/api_error.dart';
import 'package:arda/main.dart';
import 'package:arda/routes.dart';
import 'package:arda/screens/login_screen.dart';
import 'package:arda/theme/app_theme.dart';
import 'package:arda/widgets/app_bottom_nav.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'app_boot.dart';
import 'package:arda/data/repositories.dart';

import 'fake_auth.dart';
import 'fake_repos.dart';

void main() {
  /// 로그인 화면만 띄운다 — 버튼 활성화 같은 화면 규칙을 볼 때.
  Widget app({FakeAuthService? auth}) => MaterialApp(
    theme: buildAppTheme(),
    initialRoute: Routes.login,
    home: null,
    onGenerateRoute: (settings) => MaterialPageRoute(
      settings: settings,
      builder: (_) => LoginScreen(auth: auth ?? FakeAuthService()),
    ),
  );

  /// 앱 전체를 로그인 화면부터 띄운다 — 통과 후 어디로 가는지를 볼 때.
  ///
  /// 저장소도 가짜여야 한다. 통과하면 탭 셸이 뜨고 그 안의 공고 화면이 곧바로
  /// 서버를 부른다 — 진짜 저장소면 15초 타임아웃까지 매달린다(큐 8).
  Widget bootedApp({FakeAuthService? auth}) => ArdaApp(
    auth: auth ?? FakeAuthService(),
    initialRoute: Routes.login,
    repositories: Repositories(
      postings: FakePostingRepository(),
      applicants: FakeApplicantRepository(),
      // 캘린더 탭도 셸과 함께 만들어져 곧바로 서버를 부른다 (큐 8 4단계)
      schedules: FakeScheduleRepository(),
      dashboard: FakeDashboardRepository(),
    ),
  );

  Future<void> fill(WidgetTester tester) async {
    await tester.enterText(find.byType(TextField).first, 'a@b.com');
    await tester.enterText(find.byType(TextField).last, 'pw');
    await tester.pump();
  }

  group('버튼 활성화', () {
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
      await fill(tester);

      final button = tester.widget<FilledButton>(find.byType(FilledButton));
      expect(button.onPressed, isNotNull);
    });
  });

  group('실패 문구 — 원인마다 다르다', () {
    testWidgets('비밀번호가 틀리면 다시 입력하라고 한다', (tester) async {
      await tester.pumpWidget(
        app(auth: FakeAuthService(error: const LoginFailed())),
      );
      await fill(tester);

      await tester.tap(find.text('로그인'));
      await tester.pumpAndSettle();

      expect(find.text('이메일 또는 비밀번호가 올바르지 않습니다.'), findsOneWidget);
      // 로그인 화면에 그대로 남는다
      expect(find.byType(LoginScreen), findsOneWidget);
    });

    testWidgets('서버에 못 닿으면 다른 문구다 — 입력해 봐야 소용없다', (tester) async {
      await tester.pumpWidget(
        app(auth: FakeAuthService(error: const NetworkError())),
      );
      await fill(tester);

      await tester.tap(find.text('로그인'));
      await tester.pumpAndSettle();

      expect(find.textContaining('네트워크를 확인'), findsOneWidget);
    });

    testWidgets('다시 입력하면 문구가 사라진다 — 방금 것이 또 틀린 줄 안다', (tester) async {
      await tester.pumpWidget(
        app(auth: FakeAuthService(error: const LoginFailed())),
      );
      await fill(tester);
      await tester.tap(find.text('로그인'));
      await tester.pumpAndSettle();
      expect(find.text('이메일 또는 비밀번호가 올바르지 않습니다.'), findsOneWidget);

      await tester.enterText(find.byType(TextField).last, 'pw2');
      await tester.pump();

      expect(find.text('이메일 또는 비밀번호가 올바르지 않습니다.'), findsNothing);
    });
  });

  testWidgets('보내는 동안 버튼이 잠긴다 — 두 번 눌러 두 번 보내지 않는다', (tester) async {
    await tester.pumpWidget(
      app(auth: FakeAuthService(delay: const Duration(milliseconds: 200))),
    );
    await fill(tester);

    await tester.tap(find.text('로그인'));
    await tester.pump(); // 보내기 시작

    final button = tester.widget<FilledButton>(find.byType(FilledButton));
    expect(button.onPressed, isNull);
    expect(find.byType(CircularProgressIndicator), findsOneWidget);

    await tester.pumpAndSettle();
  });

  testWidgets('로그인하면 홈(대시보드)으로 넘어간다', (tester) async {
    await tester.pumpWidget(bootedApp());
    await fill(tester);

    await tester.tap(find.text('로그인'));
    await tester.pumpAndSettle();

    expect(find.text('대시보드'), findsWidgets);
    expect(find.byType(LoginScreen), findsNothing);
  });

  testWidgets('로그인한 사람 이름이 더보기에 뜬다 — 목데이터가 아니다', (tester) async {
    await tester.pumpWidget(
      bootedApp(auth: FakeAuthService(user: testUser.copyWithName('문해린'))),
    );
    await fill(tester);
    await tester.tap(find.text('로그인'));
    await tester.pumpAndSettle();

    await tester.tap(find.text('더보기'));
    await tester.pumpAndSettle();

    expect(find.text('문해린'), findsOneWidget);
  });

  group('화면 생김새', () {
    testWidgets('앱을 켜면 로그인이 먼저다 — 탭바는 아직 없다', (tester) async {
      await tester.pumpWidget(bootedApp());

      expect(find.byType(LoginScreen), findsOneWidget);
      expect(find.byType(AppBottomNav), findsNothing);
    });

    testWidgets('로고 아래 부제 — 무슨 서비스인지 알려 준다', (tester) async {
      await tester.pumpWidget(bootedApp());
      expect(find.text('채용 관리'), findsOneWidget);
    });

    testWidgets('아르 마크 · 로고 · 부제가 같은 세로선에 선다', (tester) async {
      await tester.pumpWidget(bootedApp());

      final markX = tester.getCenter(find.byType(Image)).dx;
      final logoX = tester.getCenter(find.textContaining('rda')).dx;
      final tagX = tester.getCenter(find.text('채용 관리')).dx;

      expect(logoX, moreOrLessEquals(markX, epsilon: 1));
      expect(tagX, moreOrLessEquals(markX, epsilon: 1));
    });
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
}
