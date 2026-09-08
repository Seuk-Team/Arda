// 로그인 두 탭 + 지원자 입장 (2026-09-08).
//
// 담당자 탭이 그대로인지가 먼저다 — 지원자 갈래를 붙이면서 매일 쓰는 쪽을
// 망가뜨리면 안 된다. 그 다음이 지원자 입장이다.

import 'package:arda/models/applicant_portal.dart';
import 'package:arda/routes.dart';
import 'package:arda/screens/login_screen.dart';
import 'package:arda/theme/tokens.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

import 'fake_applicant.dart';
import 'fake_auth.dart';

final _interview = InterviewPublic(
  token: 'tok',
  status: InterviewStatus.pending,
  applicantName: '김도현',
  postingTitle: '프론트엔드 개발자 (React)',
  consentRequired: true,
);

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

/// 붙여넣기 버튼이 읽는 클립보드를 가짜로 채운다
void setClipboard(WidgetTester tester, String? text) {
  tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(
    SystemChannels.platform,
    (call) async {
      if (call.method == 'Clipboard.getData') {
        return text == null ? null : <String, dynamic>{'text': text};
      }
      return null;
    },
  );
}

void main() {
  group('탭', () {
    testWidgets('기본은 담당자 — 매일 켜는 쪽이다', (tester) async {
      await tester.pumpWidget(host());
      await tester.pumpAndSettle();

      // '비밀번호' 는 라벨과 힌트 둘 다에 있다 — 버튼으로 가른다
      expect(find.text('로그인'), findsOneWidget);
      expect(find.text('입장'), findsNothing);
    });

    testWidgets('지원자로 넘기면 비밀번호를 묻지 않는다 — 계정이 없다', (tester) async {
      await tester.pumpWidget(host());
      await tester.tap(find.text('지원자'));
      await tester.pumpAndSettle();

      expect(find.text('비밀번호'), findsNothing);
      expect(find.text('입장'), findsOneWidget);
      expect(find.text('메일로 링크 받기'), findsOneWidget);
    });

    testWidgets('담당자로 돌아올 수 있다', (tester) async {
      await tester.pumpWidget(host());
      await tester.tap(find.text('지원자'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('담당자'));
      await tester.pumpAndSettle();

      expect(find.text('로그인'), findsOneWidget);
      expect(find.text('입장'), findsNothing);
    });
  });

  group('지원자 입장', () {
    testWidgets('링크를 넣으면 서버에 확인하고 저장한 뒤 홈으로 간다', (tester) async {
      final portal = FakeApplicantPortalRepository(
        interviews: {'tok': _interview},
      );
      final store = FakeApplicantStore();
      await tester.pumpWidget(host(portal: portal, store: store));
      await tester.tap(find.text('지원자'));
      await tester.pumpAndSettle();

      await tester.enterText(
        find.byType(TextField).first,
        'https://seuk.suvisdev.cloud/interview/tok',
      );
      await tester.tap(find.text('입장'));
      await tester.pumpAndSettle();

      // **저장 전에 물어본다** — 죽은 링크를 넣어 두면 다음에 켤 때마다 오류다
      expect(portal.calls, contains('interview:tok'));
      expect(store.tokens.single.token, 'tok');
      expect(find.text('지원자 홈'), findsOneWidget);
    });

    testWidgets('못 알아보는 링크는 서버에 묻지도 않는다', (tester) async {
      final portal = FakeApplicantPortalRepository();
      final store = FakeApplicantStore();
      await tester.pumpWidget(host(portal: portal, store: store));
      await tester.tap(find.text('지원자'));
      await tester.pumpAndSettle();

      await tester.enterText(find.byType(TextField).first, 'https://x.dev');
      await tester.tap(find.text('입장'));
      await tester.pumpAndSettle();

      expect(portal.calls, isEmpty);
      expect(store.tokens, isEmpty);
      expect(find.textContaining('알아보지 못했습니다'), findsOneWidget);
    });

    testWidgets('서버가 거절하면 저장하지 않는다', (tester) async {
      // 'tok' 을 안 넣어 뒀으니 가짜가 404 를 던진다
      final portal = FakeApplicantPortalRepository();
      final store = FakeApplicantStore();
      await tester.pumpWidget(host(portal: portal, store: store));
      await tester.tap(find.text('지원자'));
      await tester.pumpAndSettle();

      await tester.enterText(find.byType(TextField).first, '/interview/tok');
      await tester.tap(find.text('입장'));
      await tester.pumpAndSettle();

      expect(store.tokens, isEmpty);
      expect(find.text('유효하지 않은 링크입니다'), findsOneWidget);
      expect(find.text('지원자 홈'), findsNothing);
    });

    testWidgets('붙여넣기가 입력창을 채운다 — 43자를 손으로 치게 하지 않는다', (tester) async {
      setClipboard(tester, 'https://x.dev/interview/tok');
      await tester.pumpWidget(host());
      await tester.tap(find.text('지원자'));
      await tester.pumpAndSettle();

      await tester.tap(find.text('붙여넣기'));
      await tester.pumpAndSettle();

      expect(
        tester.widget<TextField>(find.byType(TextField).first).controller!.text,
        'https://x.dev/interview/tok',
      );
    });

    testWidgets('복사해 둔 것이 없으면 그렇다고 말한다', (tester) async {
      setClipboard(tester, null);
      await tester.pumpWidget(host());
      await tester.tap(find.text('지원자'));
      await tester.pumpAndSettle();

      await tester.tap(find.text('붙여넣기'));
      await tester.pumpAndSettle();

      expect(find.text('복사해 둔 링크가 없습니다.'), findsOneWidget);
    });
  });

  group('링크 다시 받기', () {
    testWidgets('서버가 준 안내를 그대로 보여 준다 — 결과를 나눠 그리지 않는다', (tester) async {
      final portal = FakeApplicantPortalRepository(
        lookupMessage: '입력하신 주소로 지원 현황 조회 링크를 보냈습니다.',
      );
      await tester.pumpWidget(host(portal: portal));
      await tester.tap(find.text('지원자'));
      await tester.pumpAndSettle();

      await tester.enterText(find.byType(TextField).last, 'a@b.com');
      // 800x600 테스트 화면에서는 카드 아래가 잘린다 — 실제 폰에서는 스크롤하면
      // 닿는 자리라 보이게 만든 뒤 누른다
      await tester.ensureVisible(find.text('메일로 링크 받기'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('메일로 링크 받기'));
      await tester.pumpAndSettle();

      expect(portal.calls, contains('lookup:a@b.com'));
      expect(find.text('입력하신 주소로 지원 현황 조회 링크를 보냈습니다.'), findsOneWidget);
    });

    testWidgets('이메일이 비면 아무것도 안 보낸다', (tester) async {
      final portal = FakeApplicantPortalRepository();
      await tester.pumpWidget(host(portal: portal));
      await tester.tap(find.text('지원자'));
      await tester.pumpAndSettle();

      await tester.ensureVisible(find.text('메일로 링크 받기'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('메일로 링크 받기'));
      await tester.pumpAndSettle();

      expect(portal.calls, isEmpty);
    });
  });

  group('모양', () {
    testWidgets('고른 탭만 시안색이다 (§2)', (tester) async {
      await tester.pumpWidget(host());
      await tester.pumpAndSettle();

      final staff = tester.widget<Text>(find.text('담당자'));
      final applicant = tester.widget<Text>(find.text('지원자'));
      expect(staff.style!.color, AppColors.accentText);
      expect(applicant.style!.color, AppColors.textSub);
    });
  });
}
