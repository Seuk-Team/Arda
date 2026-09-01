// 캘린더 — 05-design 캘린더 절이 앱(≤768px)에 정한 것만 그리는지 본다.
// 핵심: 월 그리드가 아니라 주간 스트립 + 그날 목록.

import 'package:arda/data/mock_data.dart';
import 'package:arda/screens/calendar_screen.dart';
import 'package:arda/theme/tokens.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// 2026-09-01 은 화요일 — 목데이터가 면접 2건을 두는 날
final tuesday = DateTime(2026, 9, 1);

Widget host({DateTime? today}) =>
    MaterialApp(home: Scaffold(body: CalendarScreen(today: today ?? tuesday)));

void main() {
  testWidgets('한 주 7칸이 일요일부터 나온다 — 월 그리드가 아니다', (tester) async {
    await tester.pumpWidget(host());

    for (final label in ['일', '월', '화', '수', '목', '금', '토']) {
      expect(find.text(label), findsOneWidget);
    }
    // 2026-08-30(일) ~ 09-05(토)
    final sunday = startOfWeek(tuesday);
    expect(sunday, DateTime(2026, 8, 30));
    for (var i = 0; i < 7; i++) {
      final d = sunday.add(Duration(days: i));
      expect(find.text('${d.day}'), findsWidgets, reason: '${d.day}일 칸');
    }
    // 월 그리드라면 30칸 넘게 나온다 — 스트립 안이 7칸뿐인지 확인
    expect(
      find.descendant(
        of: find.byKey(weekStripKey),
        matching: find.byType(Expanded),
      ),
      findsNWidgets(7),
    );
  });

  testWidgets('칸에는 건수만 적는다 — 이름은 없다', (tester) async {
    await tester.pumpWidget(host());

    for (final interview in mockInterviewsOn(tuesday)) {
      expect(
        find.descendant(
          of: find.byKey(weekStripKey),
          matching: find.text(interview.applicantName),
        ),
        findsNothing,
      );
    }
  });

  testWidgets('오늘이 기본 선택 — 그날 목록이 함께 나온다', (tester) async {
    await tester.pumpWidget(host());

    expect(find.text('2026.09.01'), findsOneWidget);
    expect(find.text('2건'), findsOneWidget);
    expect(find.text('14:00'), findsOneWidget);
    expect(find.text('16:30'), findsOneWidget);
  });

  testWidgets('그날 목록에 면접관이 있다 (05-design 캘린더 절)', (tester) async {
    await tester.pumpWidget(host());
    expect(find.textContaining('면접관'), findsWidgets);
  });

  testWidgets('다른 날을 고르면 그날 목록으로 바뀐다', (tester) async {
    await tester.pumpWidget(host());

    // 목요일(09.03) — 목데이터가 1건 두는 날
    await tester.tap(find.byKey(dayCellKey(DateTime(2026, 9, 3))));
    await tester.pumpAndSettle();

    expect(find.text('2026.09.03'), findsOneWidget);
    expect(find.text('1건'), findsOneWidget);
    expect(find.text('11:00'), findsOneWidget);
  });

  testWidgets('면접 없는 날은 빈 상태 문구 (§6)', (tester) async {
    await tester.pumpWidget(host());

    // 수요일(09.02) — 목데이터가 비워 둔 날
    await tester.tap(find.byKey(dayCellKey(DateTime(2026, 9, 2))));
    await tester.pumpAndSettle();

    expect(find.text('0건'), findsOneWidget);
    expect(find.text('면접 없음'), findsOneWidget);
  });

  testWidgets('같은 시각 두 건이면 시각은 첫 행에만 (캘린더 절 슬롯 묶기)', (tester) async {
    await tester.pumpWidget(host());

    // 금요일(09.04) — 10:00 하나 + 15:00 두 건
    await tester.tap(find.byKey(dayCellKey(DateTime(2026, 9, 4))));
    await tester.pumpAndSettle();

    expect(find.text('3건'), findsOneWidget);
    expect(find.text('15:00'), findsOneWidget, reason: '같은 시각은 한 번만 적는다');
  });

  testWidgets('주 이동은 달이 아니라 주 단위다', (tester) async {
    await tester.pumpWidget(host());
    expect(find.text('08.30 – 09.05'), findsOneWidget);

    await tester.tap(find.byIcon(Icons.chevron_right));
    await tester.pumpAndSettle();
    expect(find.text('09.06 – 09.12'), findsOneWidget);

    await tester.tap(find.byIcon(Icons.chevron_left));
    await tester.pumpAndSettle();
    expect(find.text('08.30 – 09.05'), findsOneWidget);
  });

  testWidgets('"오늘" 을 누르면 오늘로 돌아온다', (tester) async {
    await tester.pumpWidget(host());

    await tester.tap(find.byIcon(Icons.chevron_right));
    await tester.pumpAndSettle();
    expect(find.text('2026.09.01'), findsNothing);

    await tester.tap(find.text('오늘'));
    await tester.pumpAndSettle();
    expect(find.text('2026.09.01'), findsOneWidget);
  });

  testWidgets('"내 면접만" 은 권한이 아니라 필터 — 기본은 꺼짐', (tester) async {
    await tester.pumpWidget(host());

    final pill = tester.widget<Material>(
      find.ancestor(of: find.text('내 면접만'), matching: find.byType(Material)).first,
    );
    expect(pill.color, AppColors.bgSunken, reason: '기본은 꺼진 상태');

    await tester.tap(find.text('내 면접만'));
    await tester.pumpAndSettle();

    final on = tester.widget<Material>(
      find.ancestor(of: find.text('내 면접만'), matching: find.byType(Material)).first,
    );
    expect(on.color, AppColors.sproutSoft, reason: '켜지면 연두 워시 (§1)');
  });

  testWidgets('터치 타깃 44 — 날짜 칸과 주 이동 버튼 (§9)', (tester) async {
    await tester.pumpWidget(host());

    final cell = tester.getSize(
      find.ancestor(of: find.text('일'), matching: find.byType(InkWell)).first,
    );
    expect(cell.height, greaterThanOrEqualTo(AppLayout.minTouchTarget));

    final prev = tester.getSize(
      find.ancestor(of: find.byIcon(Icons.chevron_left), matching: find.byType(InkWell)).first,
    );
    expect(prev.height, greaterThanOrEqualTo(AppLayout.minTouchTarget));
    expect(prev.width, greaterThanOrEqualTo(AppLayout.minTouchTarget));
  });

  testWidgets('그날 목록 행을 누르면 그 지원자 상세로 간다 (05-design 2026-09-01)', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(body: CalendarScreen(today: tuesday)),
        onGenerateRoute: (settings) => MaterialPageRoute(
          settings: settings,
          builder: (_) => const Scaffold(body: Text('상세 화면')),
        ),
      ),
    );

    await tester.tap(find.text('김도현'));
    await tester.pumpAndSettle();

    expect(find.text('상세 화면'), findsOneWidget);
  });
}
