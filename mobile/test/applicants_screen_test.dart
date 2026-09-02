// 지원자 리스트 — 단계 탭이 실제로 목록을 거르는지 본다.
// 첫 화면이 공고 목록이라 공고를 하나 열고 들어간다.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:arda/widgets/search_field.dart';
import 'package:arda/widgets/stage_tabs.dart';

import 'app_boot.dart';

/// 단계 탭을 누른다.
///
/// 단계 이름은 화면에 여러 번 나온다 — 탭 줄 · 퍼널 범례 · 카드의 단계 칩.
/// `find.text` 만 쓰면 어느 것을 누를지 모호해진다.
Future<void> tapTab(WidgetTester tester, String label) async {
  await tester.tap(
    find.descendant(of: find.byType(StageTabs), matching: find.text(label)),
  );
  await tester.pumpAndSettle();
}

Future<void> openFirstPosting(WidgetTester tester) async {
  await bootToShell(tester);
  // 첫 화면은 홈(대시보드)이다 — 공고를 보려면 탭을 먼저 누른다
  await tester.tap(find.text('공고'));
  await tester.pumpAndSettle();
  await tester.tap(find.text('백엔드 개발자 (신입)'));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('처음엔 전체가 보인다 — 웹과 같다 (2026-09-02)', (tester) async {
    await openFirstPosting(tester);

    // 지원 접수만 먼저 띄우면 다른 단계에 사람이 있는지 알려면 탭을 눌러 봐야 한다.
    // 목록 순서는 목업 그대로(최신 지원일 → 오래된 순)라 위에서 두 단계가 섞인다.
    // 아래쪽 사람은 ListView 가 아직 만들지 않아 찾지 않는다
    expect(find.text('김도현'), findsOneWidget); // 면접
    expect(find.text('박지훈'), findsOneWidget); // 지원 접수
  });

  testWidgets('탭을 바꾸면 그 단계만 보인다', (tester) async {
    await openFirstPosting(tester);

    await tapTab(tester, '면접');

    // 면접은 2명 — 김도현과 긴 이름 지원자
    expect(find.text('김도현'), findsOneWidget);
    expect(find.text('박지훈'), findsNothing);
  });

  testWidgets('전체로 돌아오면 다시 다 보인다', (tester) async {
    await openFirstPosting(tester);

    await tapTab(tester, '면접');
    expect(find.text('박지훈'), findsNothing);

    await tapTab(tester, '전체');
    expect(find.text('박지훈'), findsOneWidget);
  });

  testWidgets('이메일로도 찾는다 — 웹의 검색 범위 (2026-09-02)', (tester) async {
    await openFirstPosting(tester);

    // 기본 범위가 전체라 이메일 조각으로도 걸린다
    await tester.enterText(find.byType(TextField), 'dohyun.kim');
    await tester.pumpAndSettle();

    expect(find.text('김도현'), findsOneWidget);
    expect(find.text('박지훈'), findsNothing);
  });

  testWidgets('범위를 이름으로 좁히면 이메일은 안 걸린다', (tester) async {
    await openFirstPosting(tester);

    // 검색 범위 선택 — 탭 줄 밖의 '전체'
    await tester.tap(
      find.descendant(of: find.byType(SearchField), matching: find.text('전체')),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('이름').last);
    await tester.pumpAndSettle();

    await tester.enterText(find.byType(TextField), 'dohyun.kim');
    await tester.pumpAndSettle();

    expect(find.text('김도현'), findsNothing);
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
