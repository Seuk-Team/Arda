// 탭 셸 — 탭을 누르면 상단 제목과 본문이 함께 바뀌는지 본다.
// 아직 조각이 안 온 탭은 "비어 있어야 한다"는 것도 검증 대상이다(§0-5).

import 'package:arda/widgets/app_bottom_nav.dart';
import 'package:arda/widgets/app_top_bar.dart';
import 'package:arda/widgets/posting_card.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'app_boot.dart';

Future<void> tapTab(WidgetTester tester, String label) async {
  await tester.tap(
    find.descendant(of: find.byType(AppBottomNav), matching: find.text(label)),
  );
  await tester.pumpAndSettle();
}

/// 상단 바 제목 — 하단 탭 라벨과 글자가 겹치므로 탭바 밖에서 찾는다
Finder title(String text) =>
    find.descendant(of: find.byType(AppTopBar), matching: find.text(text));

void main() {
  testWidgets('앱을 켜면 홈(대시보드)이 먼저 뜬다', (tester) async {
    await bootToShell(tester);

    expect(title('대시보드'), findsOneWidget);
    // 공고 목록은 아직 자리를 비우고 있다
    expect(find.byType(PostingCard), findsNothing);
  });

  testWidgets('공고 탭을 누르면 공고 목록', (tester) async {
    await bootToShell(tester);
    await tapTab(tester, '공고');

    expect(title('채용 공고'), findsOneWidget);
    expect(find.byType(PostingCard), findsNWidgets(3));
  });

  testWidgets('탭마다 상단 제목이 05-design 메뉴 이름으로 바뀐다', (tester) async {
    await bootToShell(tester);

    for (final (label, screenTitle) in const [
      ('지원자', '지원자'),
      ('홈', '대시보드'),
      ('캘린더', '캘린더'),
      ('더보기', '더보기'),
      ('공고', '채용 공고'),
    ]) {
      await tapTab(tester, label);
      expect(title(screenTitle), findsOneWidget, reason: '$label 탭');
    }
  });

  testWidgets('탭을 옮기면 공고 목록이 자리를 비운다', (tester) async {
    await bootToShell(tester);
    await tapTab(tester, '공고');
    expect(find.byType(PostingCard), findsNWidgets(3));

    await tapTab(tester, '홈');
    expect(find.byType(PostingCard), findsNothing);

    await tapTab(tester, '공고');
    expect(find.byType(PostingCard), findsNWidgets(3));
  });

  // "아직 안 만든 탭은 비어 있다" 검사는 걷어냈다 — 다섯 탭에 모두 조각이
  // 들어와 전제가 사라졌다. 각 탭의 내용은 그 화면의 테스트가 본다.

  testWidgets('다섯 탭 모두 내용이 있다', (tester) async {
    await bootToShell(tester);

    for (final label in ['공고', '지원자', '홈', '캘린더', '더보기']) {
      await tapTab(tester, label);
      // 상단 제목 하나 + 탭 라벨 다섯 = 여섯. 그보다 많아야 본문이 있는 것이다
      expect(find.byType(Text), findsAtLeast(7), reason: '$label 탭이 비어 있다');
    }
  });

  testWidgets('탭을 옮겨도 하단 바는 자리를 지킨다', (tester) async {
    await bootToShell(tester);
    final before = tester.getRect(find.byType(AppBottomNav));

    await tapTab(tester, '캘린더');
    expect(tester.getRect(find.byType(AppBottomNav)), before);
  });

  testWidgets('공고에서 파고든 화면에는 탭바가 없다', (tester) async {
    await bootToShell(tester);
    await tapTab(tester, '공고');

    await tester.tap(find.byType(PostingCard).first);
    await tester.pumpAndSettle();
    expect(find.byType(AppBottomNav), findsNothing);
  });
}
