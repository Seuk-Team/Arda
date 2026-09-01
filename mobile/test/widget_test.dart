// 화면이 뜨고 계층대로 이동되는지, 테마가 토큰을 쓰는지만 본다.
// 공고 → 그 공고의 지원자 → 지원자 상세 (시안 2026-08-28)

import 'package:arda/main.dart';
import 'package:arda/screens/applicant_detail_screen.dart';
import 'package:arda/widgets/posting_card.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('첫 화면은 채용 공고 목록이다', (tester) async {
    await tester.pumpWidget(const ArdaApp());
    // 첫 화면은 홈(대시보드)이다 — 공고를 보려면 탭을 먼저 누른다
    await tester.tap(find.text('공고'));
    await tester.pumpAndSettle();

    expect(find.text('채용 공고'), findsOneWidget);
    expect(find.byType(PostingCard), findsNWidgets(3));
  });

  testWidgets('공고 → 지원자 → 상세 로 들어가고 되돌아온다', (tester) async {
    await tester.pumpWidget(const ArdaApp());
    // 첫 화면은 홈(대시보드)이다 — 공고를 보려면 탭을 먼저 누른다
    await tester.tap(find.text('공고'));
    await tester.pumpAndSettle();

    await tester.tap(find.text('백엔드 개발자 (신입)'));
    await tester.pumpAndSettle();
    expect(find.text('지원자'), findsOneWidget);

    // 지원 접수 탭이 기본이라 박지훈이 보인다
    await tester.tap(find.text('박지훈'));
    await tester.pumpAndSettle();
    expect(find.byType(ApplicantDetailScreen), findsOneWidget);

    await tester.tap(find.bySemanticsLabel('뒤로'));
    await tester.pumpAndSettle();
    expect(find.text('지원자'), findsOneWidget);

    await tester.tap(find.bySemanticsLabel('뒤로'));
    await tester.pumpAndSettle();
    expect(find.text('채용 공고'), findsOneWidget);
  });

  testWidgets('테마가 05-design 토큰을 쓴다', (tester) async {
    await tester.pumpWidget(const ArdaApp());
    // 첫 화면은 홈(대시보드)이다 — 공고를 보려면 탭을 먼저 누른다
    await tester.tap(find.text('공고'));
    await tester.pumpAndSettle();

    final theme = Theme.of(tester.element(find.byType(Scaffold)));
    expect(theme.scaffoldBackgroundColor, const Color(0xFFF4F7F0)); // --bg
    expect(theme.colorScheme.primary, const Color(0xFF3A6B21)); // --leaf
    expect(theme.textTheme.bodyLarge?.fontSize, 16); // --font-body
    expect(theme.textTheme.bodyLarge?.fontFamily, 'IBM Plex Sans KR');
  });
}
