// 지원자 리스트 — 단계 탭이 실제로 목록을 거르는지 본다.
// 첫 화면이 공고 목록이라 공고를 하나 열고 들어간다.

import 'package:arda/main.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

Future<void> openFirstPosting(WidgetTester tester) async {
  await tester.pumpWidget(const ArdaApp());
  // 첫 화면은 홈(대시보드)이다 — 공고를 보려면 탭을 먼저 누른다
  await tester.tap(find.text('공고'));
  await tester.pumpAndSettle();
  await tester.tap(find.text('백엔드 개발자 (신입)'));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('처음엔 지원 접수 단계만 보인다', (tester) async {
    await openFirstPosting(tester);

    expect(find.text('박지훈'), findsOneWidget);
    expect(find.text('김도현'), findsNothing);
  });

  testWidgets('탭을 바꾸면 그 단계만 보인다', (tester) async {
    await openFirstPosting(tester);

    await tester.tap(find.text('면접'));
    await tester.pumpAndSettle();

    // 면접은 2명 — 김도현과 긴 이름 지원자
    expect(find.text('김도현'), findsOneWidget);
    expect(find.text('박지훈'), findsNothing);
  });

  testWidgets('합격·불합격만 색을 쓴다 — 05-design §1', (tester) async {
    await openFirstPosting(tester);

    await tester.tap(find.text('최종 합격'));
    await tester.pumpAndSettle();
    final accepted = tester.widget<Text>(find.text('최종 합격').last);
    expect(accepted.style?.color, const Color(0xFF3A6B21)); // --leaf

    await tester.tap(find.text('불합격'));
    await tester.pumpAndSettle();
    final rejected = tester.widget<Text>(find.text('불합격').last);
    expect(rejected.style?.color, const Color(0xFFA9503C)); // --danger

    await tester.tap(find.text('면접'));
    await tester.pumpAndSettle();
    final inProgress = tester.widget<Text>(find.text('면접').last);
    expect(inProgress.style?.color, const Color(0xFF5C6654)); // --text-sub
  });
}
