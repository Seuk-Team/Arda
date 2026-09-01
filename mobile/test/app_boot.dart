// 화면 테스트 공용 시작점.
//
// 앱의 첫 화면은 로그인이다. 어느 화면을 보든 그 문을 한 번 지나야 하므로
// 매 테스트에서 같은 절차를 반복하지 않도록 여기 모은다.
//
// 로그인 화면 자체를 보는 테스트(login_screen_test.dart)는 이 헬퍼를 쓰지 않는다.

import 'package:arda/main.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// 앱을 켜고 로그인을 통과해 탭 셸까지 간다.
///
/// [tab] 을 주면 그 탭까지 옮긴다. 셸은 홈(대시보드)에서 시작하므로
/// 공고·지원자 등을 보려면 탭 이름을 넘겨야 한다.
///
/// 아직 인증이 없어 아무 값이나 통과한다 — 큐 7(JWT)에서 실제 호출이 붙으면
/// 여기도 가짜 응답을 물리는 자리가 된다.
Future<void> bootToShell(WidgetTester tester, {String? tab}) async {
  await tester.pumpWidget(const ArdaApp());

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
