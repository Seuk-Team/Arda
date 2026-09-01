// 단계 변경 시트 — 메일이 나가는 되돌릴 수 없는 동작이라 안전장치가 핵심이다.
// 시안(2026-08-28) 1번이 정한 네 가지를 검증한다.

import 'package:arda/main.dart';
import 'package:arda/widgets/stage_rail.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// 공고 → 지원자 → 상세 → 단계 변경 시트까지 연다.
///
/// 박지훈은 `지원 접수` 단계라 갈 수 있는 곳이 서류 검토·불합격 둘뿐이다 —
/// "전진은 한 칸씩"과 "불합격은 어디서든"을 한 화면에서 볼 수 있는 자리다.
Future<void> openSheet(WidgetTester tester) async {
  await tester.pumpWidget(const ArdaApp());
  // 첫 화면은 홈(대시보드)이다 — 공고를 보려면 탭을 먼저 누른다
  await tester.tap(find.text('공고'));
  await tester.pumpAndSettle();

  await tester.tap(find.text('백엔드 개발자 (신입)'));
  await tester.pumpAndSettle();

  await tester.tap(find.text('박지훈'));
  await tester.pumpAndSettle();

  await tester.tap(find.text('단계 변경'));
  await tester.pumpAndSettle();
}

/// 상세 화면의 전형 레일도 단계 이름을 그린다(앱 UI 초안 2026-09-01).
/// 시트 안의 선택지만 보도록 범위를 좁힌다 — 안 그러면 같은 글자를 두 번 잡는다.
Finder inSheet(String text) =>
    find.descendant(of: find.byType(BottomSheet), matching: find.text(text));

/// 레일 밖에서 찾는다 — 시트가 닫힌 뒤 상세 화면을 볼 때 쓴다
Finder outsideRail(String text) =>
    find.descendant(of: find.byType(StageRail), matching: find.text(text));

void main() {
  testWidgets('갈 수 있는 단계만 보여 준다 — 지원 접수에서는 2개', (tester) async {
    await openSheet(tester);

    // applied → screening(한 칸) · rejected(어디서든). interview 는 건너뛰기라 없다
    expect(inSheet('서류 검토'), findsOneWidget);
    expect(inSheet('불합격'), findsOneWidget);
    expect(inSheet('면접'), findsNothing);
    expect(inSheet('최종 합격'), findsNothing);
  });

  testWidgets('고르기 전에는 확정 버튼이 잠겨 있다', (tester) async {
    await openSheet(tester);

    final button = tester.widget<FilledButton>(
      find.widgetWithText(FilledButton, '단계 선택'),
    );
    expect(button.onPressed, isNull);
  });

  testWidgets('메일이 안 나가는 단계에는 경고를 띄우지 않는다', (tester) async {
    await openSheet(tester);

    // screening 은 NOTIFY_STAGES 에 없다 — 늘 띄우면 경고를 안 읽게 된다
    await tester.tap(inSheet('서류 검토'));
    await tester.pumpAndSettle();

    expect(find.text('지원자에게 안내 메일이 나갑니다'), findsNothing);
    expect(find.text('서류 검토으로 변경'), findsOneWidget);
  });

  testWidgets('메일이 나가는 단계에는 경고를 띄운다', (tester) async {
    await openSheet(tester);

    await tester.tap(inSheet('불합격'));
    await tester.pumpAndSettle();

    expect(find.text('지원자에게 안내 메일이 나갑니다'), findsOneWidget);
    expect(find.text('보낸 메일은 취소할 수 없습니다. 확인하고 변경하세요.'), findsOneWidget);
    // 색 하나로 알리지 않는다 — 아이콘도 함께 (05-design §10)
    expect(find.byIcon(Icons.warning_amber), findsOneWidget);
  });

  testWidgets('불합격은 사유가 비면 확정 버튼이 잠긴다 — D8', (tester) async {
    await openSheet(tester);

    await tester.tap(inSheet('불합격'));
    await tester.pumpAndSettle();

    final locked = tester.widget<FilledButton>(
      find.widgetWithText(FilledButton, '불합격으로 변경'),
    );
    expect(locked.onPressed, isNull);

    await tester.enterText(find.byType(TextField), '기술 요건 미달');
    await tester.pumpAndSettle();

    final unlocked = tester.widget<FilledButton>(
      find.widgetWithText(FilledButton, '불합격으로 변경'),
    );
    expect(unlocked.onPressed, isNotNull);
  });

  testWidgets('취소하면 아무 일도 일어나지 않는다', (tester) async {
    await openSheet(tester);

    await tester.tap(inSheet('서류 검토'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('취소'));
    await tester.pumpAndSettle();

    expect(find.text('단계 변경'), findsOneWidget); // 상세의 버튼만 남는다
    expect(find.byType(SnackBar), findsNothing);
  });
}
