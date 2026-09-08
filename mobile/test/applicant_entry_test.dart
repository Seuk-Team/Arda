// 로그인 두 탭 + 지원자 로그인 (2026-09-08).
//
// 담당자 탭이 그대로인지가 먼저다 — 지원자 갈래를 붙이면서 매일 쓰는 쪽을
// 망가뜨리면 안 된다. 그 다음이 지원자 로그인이다.
//
// **서버가 실패 사유를 안 나눈다**(ADR-0031): 없는 이메일·틀린 생년월일·
// 생년월일 없는 옛 지원서가 전부 같은 401 이고, 5회 실패하면 15분 429 다.
// 앱이 사유를 지어내면 서버가 일부러 감춘 것을 도로 드러내므로, 여기서는
// **서버 문구가 그대로 화면에 오르는지**를 본다.

import 'package:arda/api/api_error.dart';
import 'package:arda/routes.dart';
import 'package:arda/screens/login_screen.dart';
import 'package:arda/theme/tokens.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'fake_applicant.dart';
import 'fake_auth.dart';
import 'no_motion.dart';

Widget host({FakeApplicantPortalRepository? portal}) => MaterialApp(
  theme: ThemeData(useMaterial3: true),
  home: LoginScreen(
    auth: FakeAuthService(),
    portal: portal ?? FakeApplicantPortalRepository(),
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
  String email = 'dnwjdwkd145@naver.com',
  String birth = '19980412',
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

    testWidgets('링크를 넣는 자리는 없다 — 로그인이 유일한 문이다', (tester) async {
      disableMotion(tester);
      await tester.pumpWidget(host());
      await toApplicant(tester);

      expect(find.text('붙여넣기'), findsNothing);
      expect(find.text('링크로 입장'), findsNothing);
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

  group('입력 규칙', () {
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

      await fill(tester, birth: '1998041');
      expect(loginButton(tester).onPressed, isNull);
    });

    testWidgets('숫자만 들어간다 — 8자리 날짜 칸이다', (tester) async {
      disableMotion(tester);
      await tester.pumpWidget(host());
      await toApplicant(tester);

      await fill(tester, birth: '1998-04-12');
      expect(
        tester.widget<TextField>(find.byType(TextField).last).controller!.text,
        '19980412',
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
  });

  group('서버와 주고받기', () {
    testWidgets('성공하면 지원자 홈으로 간다', (tester) async {
      disableMotion(tester);
      final portal = FakeApplicantPortalRepository();
      await tester.pumpWidget(host(portal: portal));
      await toApplicant(tester);

      await fill(tester);
      await tester.tap(find.text('로그인'));
      await tester.pumpAndSettle();

      expect(portal.calls, contains('login:dnwjdwkd145@naver.com:19980412'));
      expect(portal.token, isNotNull);
      expect(find.text('지원자 홈'), findsOneWidget);
    });

    testWidgets('이메일 앞뒤 공백은 떼고 보낸다 — 복사하면 딸려 온다', (tester) async {
      disableMotion(tester);
      final portal = FakeApplicantPortalRepository();
      await tester.pumpWidget(host(portal: portal));
      await toApplicant(tester);

      await fill(tester, email: '  a@b.com  ');
      await tester.tap(find.text('로그인'));
      await tester.pumpAndSettle();

      expect(portal.calls, contains('login:a@b.com:19980412'));
    });

    testWidgets('틀리면 서버 문구를 그대로 띄운다 — 사유를 지어내지 않는다', (tester) async {
      disableMotion(tester);
      final portal = FakeApplicantPortalRepository(
        loginError: const ServerError(401, '이메일 또는 생년월일이 맞지 않습니다'),
      );
      await tester.pumpWidget(host(portal: portal));
      await toApplicant(tester);

      await fill(tester);
      await tester.tap(find.text('로그인'));
      await tester.pumpAndSettle();

      expect(find.text('이메일 또는 생년월일이 맞지 않습니다'), findsOneWidget);
      expect(find.text('지원자 홈'), findsNothing);
    });

    testWidgets('잠기면 잠겼다고 그대로 말한다 (429)', (tester) async {
      disableMotion(tester);
      final portal = FakeApplicantPortalRepository(
        loginError: const ServerError(429, '로그인 시도가 많습니다. 15분 뒤에 다시 시도해 주세요'),
      );
      await tester.pumpWidget(host(portal: portal));
      await toApplicant(tester);

      await fill(tester);
      await tester.tap(find.text('로그인'));
      await tester.pumpAndSettle();

      // 잠긴 뒤에는 맞는 값을 넣어도 막힌다 — 그 사실이 화면에 그대로 나와야
      // "비밀번호는 맞는데 왜 안 되지" 로 헤매지 않는다
      expect(find.text('로그인 시도가 많습니다. 15분 뒤에 다시 시도해 주세요'), findsOneWidget);
    });

    testWidgets('못 닿아도 버튼이 풀린다 — 스피너가 영영 돌면 안 된다', (tester) async {
      disableMotion(tester);
      final portal = FakeApplicantPortalRepository(
        loginError: const NetworkError(),
      );
      await tester.pumpWidget(host(portal: portal));
      await toApplicant(tester);

      await fill(tester);
      await tester.tap(find.text('로그인'));
      await tester.pumpAndSettle();

      expect(find.textContaining('네트워크를 확인'), findsOneWidget);
      expect(loginButton(tester).onPressed, isNotNull);
    });
  });
}
