// 지원자 리스트 — 단계 탭이 실제로 목록을 거르는지 본다.
// 목데이터 6명은 mockup-mobile.html 에서 온 것이라, 단계별 인원도 목업과 같다.

import 'package:arda/main.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('처음엔 지원 접수 단계만 보인다', (tester) async {
    await tester.pumpWidget(const ArdaApp());

    // 목업이 `지원 접수` 에 .on 을 붙여 둔 상태
    expect(find.text('박지훈'), findsOneWidget);
    expect(find.text('김도현'), findsNothing);
  });

  testWidgets('탭을 바꾸면 그 단계만 보인다', (tester) async {
    await tester.pumpWidget(const ArdaApp());

    await tester.tap(find.text('면접'));
    await tester.pumpAndSettle();

    // 면접은 2명 — 김도현과 긴 이름 지원자
    expect(find.text('김도현'), findsOneWidget);
    expect(find.text('박지훈'), findsNothing);
  });

  testWidgets('합격·불합격만 색을 쓴다 — 05-design §1', (tester) async {
    await tester.pumpWidget(const ArdaApp());

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
