// 로그인 두 탭 + 지원자 로그인 (2026-09-08).
//
// 담당자 탭이 그대로인지가 먼저다 — 지원자 갈래를 붙이면서 매일 쓰는 쪽을
// 망가뜨리면 안 된다. 그 다음이 지원자 로그인이다.
//
// **지원자 로그인은 서버에 아직 없다.** 그래서 여기서 보는 것은 화면 규칙이다:
// 무엇을 채워야 버튼이 살아나는지, 이상한 생년월일을 보내기 전에 잡는지,
// 서버가 거절하면 무엇을 보여 주는지.

import 'package:arda/auth/applicant_store.dart';
import 'package:arda/routes.dart';
import 'package:arda/screens/login_screen.dart';
import 'package:arda/theme/tokens.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'fake_applicant.dart';
import 'fake_auth.dart';
import 'no_motion.dart';

const _token = ApplicantToken(kind: ApplicantTokenKind.portal, token: 'p1');

Widget host({
  FakeApplicantPortalRepository? portal,
  FakeApplicantStore? store,
}) => MaterialApp(
  theme: ThemeData(useMaterial3: true),
  home: LoginScreen(
    auth: FakeAuthService(),
    portal: portal ?? FakeApplicantPortalRepository(),
    applicantStore: store ?? FakeApplicantStore(),
  ),
  routes: {Routes.applicantHome: (_) => const Scaffold(body: Text('지원자 홈'))},
);

/// 지원자 탭으로 옮긴다
Future<void> toApplicant(WidgetTester tester) async {
  await tester.tap(find.text('지원자'));
  await tester.pumpAndSettle();
}

/// 이메일·생년월일을 채운다. [birth] 를 비우면 이메일만 채운다
Future<void> fill(
  WidgetTester tester, {
  String email = 'a@b.com',
  String birth = '19980315',
}) async {
  await tester.enterText(find.byType(TextField).first, email);
  if (birth.isNotEmpty) {
    await tester.enterText(find.byType(TextField).last, birth);
  }
  await tester.pumpAndSettle();
}

/// 로그인 버튼. 두 탭 모두 이름이 같아 화면에 하나뿐이다
FilledButton loginButton(WidgetTester tester) => tester.widget<FilledButton>(
  find.ancestor(of: find.text('로그인'), matching: find.byType(FilledButton)),
);

void main() {
  group('탭', () {
    testWidgets('기본은 담당자 — 매일 켜는 쪽이다', (tester) async {
      disableMotion(tester);
      await tester.pumpWidget(host());
      await tester.pumpAndSettle();

      expect(find.text('생년월일 8자리'), findsNothing);
      // '비밀번호' 는 라벨과 힌트 둘 다에 있다
      expect(find.text('비밀번호'), findsWidgets);
    });

    testWidgets('지원자는 비밀번호 대신 생년월일이다', (tester) async {
      disableMotion(tester);
      await tester.pumpWidget(host());
      await toApplicant(tester);

      expect(find.text('생년월일 8자리'), findsOneWidget);
      expect(find.text('비밀번호'), findsNothing);
    });

    testWidgets('링크를 넣는 자리는 없다 — 링크는 앱을 설치할 때 준다', (tester) async {
      disableMotion(tester);
      await tester.pumpWidget(host());
      await toApplicant(tester);

      expect(find.text('붙여넣기'), findsNothing);
      expect(find.text('입장'), findsNothing);
      expect(find.text('메일로 링크 받기'), findsNothing);
    });

    testWidgets('담당자로 돌아올 수 있다', (tester) async {
      disableMotion(tester);
      await tester.pumpWidget(host());
      await toApplicant(tester);
      await tester.tap(find.text('담당자'));
      await tester.pumpAndSettle();

      expect(find.text('비밀번호'), findsWidgets);
      expect(find.text('생년월일 8자리'), findsNothing);
    });

    testWidgets('고른 탭만 시안색이다 (§2)', (tester) async {
      disableMotion(tester);
      await tester.pumpWidget(host());
      await tester.pumpAndSettle();

      expect(
        tester.widget<Text>(find.text('담당자')).style!.color,
        AppColors.accentText,
      );
      expect(
        tester.widget<Text>(find.text('지원자')).style!.color,
        AppColors.textSub,
      );
    });
  });

  group('지원자 로그인', () {
    testWidgets('둘 다 채워야 버튼이 살아난다', (tester) async {
      disableMotion(tester);
      await tester.pumpWidget(host());
      await toApplicant(tester);
      expect(loginButton(tester).onPressed, isNull);

      await fill(tester, birth: '');
      expect(loginButton(tester).onPressed, isNull);

      await fill(tester);
      expect(loginButton(tester).onPressed, isNotNull);
    });

    testWidgets('8자리를 다 안 채우면 잠겨 있다', (tester) async {
      disableMotion(tester);
      await tester.pumpWidget(host());
      await toApplicant(tester);

      await fill(tester, birth: '1998031');
      expect(loginButton(tester).onPressed, isNull);
    });

    testWidgets('숫자만 들어간다 — 8자리 날짜 칸이다', (tester) async {
      disableMotion(tester);
      await tester.pumpWidget(host());
      await toApplicant(tester);

      await fill(tester, birth: '1998-03-15');
      expect(
        tester.widget<TextField>(find.byType(TextField).last).controller!.text,
        '19980315',
      );
    });

    testWidgets('날짜가 아니면 서버에 보내지 않는다', (tester) async {
      disableMotion(tester);
      final portal = FakeApplicantPortalRepository();
      await tester.pumpWidget(host(portal: portal));
      await toApplicant(tester);

      // 13월은 없다. DateTime 은 넘치면 다음 해로 넘겨 버려서 되돌려 봐야 잡힌다
      await fill(tester, birth: '19981345');
      await tester.tap(find.text('로그인'));
      await tester.pumpAndSettle();

      expect(portal.calls, isEmpty);
      expect(find.textContaining('생년월일을 다시 확인해 주세요'), findsOneWidget);
    });

    testWidgets('2월 30일도 잡는다', (tester) async {
      disableMotion(tester);
      final portal = FakeApplicantPortalRepository();
      await tester.pumpWidget(host(portal: portal));
      await toApplicant(tester);

      await fill(tester, birth: '19980230');
      await tester.tap(find.text('로그인'));
      await tester.pumpAndSettle();

      expect(portal.calls, isEmpty);
    });

    testWidgets('서버가 아직 없어서 준비 중이라고 답한다', (tester) async {
      disableMotion(tester);
      // loginTokens 를 안 준 가짜 = 진짜와 같이 501
      final portal = FakeApplicantPortalRepository();
      final store = FakeApplicantStore();
      await tester.pumpWidget(host(portal: portal, store: store));
      await toApplicant(tester);

      await fill(tester);
      await tester.tap(find.text('로그인'));
      await tester.pumpAndSettle();

      expect(portal.calls, contains('login:a@b.com:19980315'));
      expect(find.text('지원자 로그인은 아직 준비 중입니다.'), findsOneWidget);
      expect(store.tokens, isEmpty);
      expect(find.text('지원자 홈'), findsNothing);
    });

    testWidgets('서버가 생기면 토큰을 저장하고 홈으로 간다', (tester) async {
      disableMotion(tester);
      final portal = FakeApplicantPortalRepository(loginTokens: const [_token]);
      final store = FakeApplicantStore();
      await tester.pumpWidget(host(portal: portal, store: store));
      await toApplicant(tester);

      await fill(tester);
      await tester.tap(find.text('로그인'));
      await tester.pumpAndSettle();

      expect(store.tokens.single, _token);
      expect(find.text('지원자 홈'), findsOneWidget);
    });

    testWidgets('이메일 앞뒤 공백은 떼고 보낸다 — 복사하면 딸려 온다', (tester) async {
      disableMotion(tester);
      final portal = FakeApplicantPortalRepository(loginTokens: const [_token]);
      await tester.pumpWidget(host(portal: portal));
      await toApplicant(tester);

      await fill(tester, email: '  a@b.com  ');
      await tester.tap(find.text('로그인'));
      await tester.pumpAndSettle();

      expect(portal.calls, contains('login:a@b.com:19980315'));
    });
  });
}
