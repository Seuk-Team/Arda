// 뼈대 단계의 테스트 — 화면이 뜨고 서로 이동되는지, 테마가 토큰을 쓰는지만 본다.
// 리스트 내용 검증은 카드 리스트 조각에서 추가한다.

import 'package:arda/main.dart';
import 'package:arda/screens/applicant_detail_screen.dart';
import 'package:arda/widgets/app_top_bar.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('첫 화면은 지원자 리스트다', (tester) async {
    await tester.pumpWidget(const ArdaApp());

    // 목업 .mbar — 이 화면은 제목 대신 상단 바를 쓴다
    expect(find.byType(AppTopBar), findsOneWidget);
  });

  testWidgets('카드를 누르면 상세로 가고 되돌아온다', (tester) async {
    await tester.pumpWidget(const ArdaApp());

    await tester.tap(find.text('박지훈')); // 지원 접수 탭의 카드를 눌러 상세로 간다
    await tester.pumpAndSettle();
    expect(find.byType(ApplicantDetailScreen), findsOneWidget);

    // 상세는 목업 .dclose 규격의 닫기 버튼으로 나온다
    await tester.tap(find.bySemanticsLabel('뒤로'));
    await tester.pumpAndSettle();
    expect(find.byType(AppTopBar), findsOneWidget);
  });

  testWidgets('테마가 05-design 토큰을 쓴다', (tester) async {
    await tester.pumpWidget(const ArdaApp());

    final theme = Theme.of(tester.element(find.byType(Scaffold)));
    expect(theme.scaffoldBackgroundColor, const Color(0xFFF4F7F0)); // --bg
    expect(theme.colorScheme.primary, const Color(0xFF3A6B21)); // --leaf
    expect(theme.textTheme.bodyLarge?.fontSize, 16); // --font-body
    expect(theme.textTheme.bodyLarge?.fontFamily, 'IBM Plex Sans KR');
  });
}
