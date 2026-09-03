// 화면 테스트 공용 시작점.
//
// 앱의 첫 화면은 시작 화면(토큰 확인)이고 그 다음이 로그인이다. 어느 화면을
// 보든 그 문을 지나야 하므로 매 테스트에서 같은 절차를 반복하지 않도록
// 여기 모은다.
//
// 큐 7 로 로그인이 진짜 호출이 됐다 — [FakeAuthService] 를 넣어 네트워크와
// Keystore 를 타지 않게 한다. 로그인 화면 자체를 보는 테스트
// (login_screen_test.dart)는 이 헬퍼를 쓰지 않는다.

import 'package:arda/main.dart';
import 'package:arda/routes.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:arda/data/repositories.dart';

import 'fake_auth.dart';
import 'fake_repos.dart';

/// 앱을 켜고 로그인을 통과해 탭 셸까지 간다.
///
/// [tab] 을 주면 그 탭까지 옮긴다. 셸은 홈(대시보드)에서 시작하므로
/// 공고·지원자 등을 보려면 탭 이름을 넘겨야 한다.
Future<void> bootToShell(WidgetTester tester, {String? tab}) async {
  // 시작 화면을 건너뛰고 로그인부터 — 토큰 확인은 launch_screen_test 가 본다.
  // 저장소도 가짜다(큐 8) — 화면 규칙을 보는 테스트가 서버에 붙을 이유가 없다
  await tester.pumpWidget(
    ArdaApp(
      auth: FakeAuthService(),
      initialRoute: Routes.login,
      repositories: Repositories(
        postings: FakePostingRepository(),
        applicants: FakeApplicantRepository(),
        schedules: FakeScheduleRepository(),
      ),
    ),
  );

  await tester.enterText(find.byType(TextField).first, 'a@b.com');
  await tester.enterText(find.byType(TextField).last, 'pw');
  await tester.pump();
  await tester.tap(find.text('로그인'));
  await tester.pumpAndSettle();

  if (tab != null) {
    await tester.tap(find.text(tab));
    await tester.pumpAndSettle();
  }
}
