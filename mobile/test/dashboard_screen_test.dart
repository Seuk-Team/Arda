// 대시보드 — 조각 3~9. 05-design 이 값을 못 박은 곳은 전부 그 값으로 검사한다.


import 'package:arda/data/mock_data.dart';
import 'package:arda/models/stage.dart';
import 'package:arda/screens/dashboard_screen.dart';
import 'package:arda/theme/tokens.dart';
import 'package:arda/widgets/funnel_bar.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// 2026-09-01 은 화요일 — 목데이터가 면접 2건을 두는 날
final aDay = DateTime(2026, 9, 1);

Widget host({DateTime? today}) =>
    MaterialApp(home: Scaffold(body: DashboardScreen(today: today ?? aDay)));

Finder get card => find
    .descendant(of: find.byType(DashboardScreen), matching: find.byType(Container))
    .first;

BoxDecoration decorationOf(WidgetTester tester) =>
    tester.widget<Container>(card).decoration! as BoxDecoration;

void main() {
  group('조각 3 — 카드 자리', () {
    testWidgets('흰 바탕 · radius 8 · 1px 테두리 · 카드 그림자 (§4)', (tester) async {
      await tester.pumpWidget(host());
      final deco = decorationOf(tester);

      expect(deco.color, AppColors.bgElev);
      expect(deco.borderRadius, AppShape.card);
      expect((deco.border! as Border).top.color, AppColors.border);
      expect((deco.border! as Border).top.width, AppShape.borderW);
      expect(deco.boxShadow, AppShadow.card);
    });

    testWidgets('화면 여백 --sp-4, 카드 안쪽 여백도 --sp-4 (§3 · §0.5)', (tester) async {
      await tester.pumpWidget(host());

      final screen = tester.getRect(find.byType(DashboardScreen));
      final box = tester.getRect(card);
      expect(box.left - screen.left, AppSpace.s4);
      expect(screen.right - box.right, AppSpace.s4);
      expect(box.top - screen.top, AppSpace.s4);

      expect(
        tester.widget<Container>(card).padding,
        const EdgeInsets.all(AppSpace.s4),
      );
    });

    testWidgets('높이는 내용이 정한다 — 잠정 높이를 걷어냈다', (tester) async {
      await tester.pumpWidget(host());

      // 카드 높이 = 내용 높이 + 안쪽 여백 위아래 + 테두리 위아래.
      // 고정 높이가 남아 있으면 이 등식이 깨진다
      final content = tester.getSize(
        find.descendant(of: card, matching: find.byType(Column)).first,
      );
      expect(
        tester.getSize(card).height,
        moreOrLessEquals(
          content.height + (AppSpace.s4 + AppShape.borderW) * 2,
          epsilon: 0.5,
        ),
      );
    });
  });

  group('조각 4 — 카드 제목 줄', () {
    testWidgets('제목은 h2 · w700 · 제목 그림자 (§2 · §0.5)', (tester) async {
      await tester.pumpWidget(host());

      final title = tester.widget<Text>(find.text('오늘 면접'));
      expect(title.style!.fontSize, AppType.h2);
      expect(title.style!.fontWeight, FontWeight.w700);
      expect(title.style!.color, AppColors.text);
      expect(title.style!.shadows, AppTextShadow.heading);
    });

    testWidgets('메타는 "날짜 · N건" — 날짜는 §2 표기, 일정은 명이 아니라 건', (tester) async {
      await tester.pumpWidget(host());
      expect(find.text('2026.09.01 · 2건'), findsOneWidget);
    });

    testWidgets('메타는 --font-num + tabular-nums, 그림자 없음 (§2)', (tester) async {
      await tester.pumpWidget(host());

      final meta = tester.widget<Text>(find.text('2026.09.01 · 2건'));
      expect(meta.style!.fontSize, AppType.num);
      expect(meta.style!.fontFeatures, AppType.tabularNums);
      expect(meta.style!.color, AppColors.textSub);
      expect(meta.style!.shadows, isNull);
    });
  });

  group('조각 5 — 면접 행', () {
    testWidgets('오늘 확정된 면접이 시각 순서대로 나온다', (tester) async {
      await tester.pumpWidget(host());

      expect(find.text('14:00'), findsOneWidget);
      expect(find.text('16:30'), findsOneWidget);
      expect(
        tester.getRect(find.text('14:00')).top,
        lessThan(tester.getRect(find.text('16:30')).top),
      );
    });

    testWidgets('행에 지원자 이름과 공고가 함께 있다', (tester) async {
      await tester.pumpWidget(host());

      for (final interview in mockInterviewsOn(aDay)) {
        expect(
          find.descendant(of: card, matching: find.text(interview.applicantName)),
          findsOneWidget,
        );
      }
      // 두 사람 모두 같은 공고라 제목은 2번. 진행중 공고 블록에도 같은 제목이
      // 있으므로 '오늘 면접' 카드 안으로 범위를 좁혀서 센다
      expect(
        find.descendant(of: card, matching: find.text('백엔드 개발자 (신입)')),
        findsNWidgets(2),
      );
    });

    testWidgets('시각은 --font-num + tabular + 잎초록 (§1 · §2)', (tester) async {
      await tester.pumpWidget(host());

      final time = tester.widget<Text>(find.text('14:00'));
      expect(time.style!.fontSize, AppType.num);
      expect(time.style!.fontFeatures, AppType.tabularNums);
      expect(time.style!.color, AppColors.leaf);
      // §2: 작은 글씨엔 그림자 금지
      expect(time.style!.shadows, isNull);
    });

    testWidgets('이름은 본문 크기 w600, 공고는 캡션 크기 보조색', (tester) async {
      await tester.pumpWidget(host());
      final first = mockInterviewsOn(aDay).first;

      final name = tester.widget<Text>(find.text(first.applicantName));
      expect(name.style!.fontSize, AppType.body);
      expect(name.style!.fontWeight, AppType.wSemiBold);

      final posting = tester.widget<Text>(find.text(first.postingTitle).first);
      expect(posting.style!.fontSize, AppType.caption);
      expect(posting.style!.color, AppColors.textSub);
    });

    testWidgets('긴 이름은 한 줄 말줄임 — 시간표가 무너지지 않는다 (§7)', (tester) async {
      await tester.pumpWidget(host());

      final long = mockInterviewsOn(aDay)
          .map((i) => i.applicantName)
          .reduce((a, b) => a.length >= b.length ? a : b);
      expect(long.length, greaterThan(20), reason: '긴 이름 케이스가 목데이터에 있어야 한다');

      final text = tester.widget<Text>(find.text(long));
      expect(text.maxLines, 1);
      expect(text.overflow, TextOverflow.ellipsis);

      // 두 행 높이가 같아야 한다 — 긴 이름이 줄을 늘리면 어긋난다
      final rows = tester.widgetList<Container>(find.byType(Container)).toList();
      expect(rows.length, greaterThanOrEqualTo(3)); // 카드 + 행 2
      final h1 = tester.getSize(find.byType(Container).at(1)).height;
      final h2 = tester.getSize(find.byType(Container).at(2)).height;
      expect(h1, h2);
    });

    testWidgets('행 사이 실선은 --border-soft 1px (§4)', (tester) async {
      await tester.pumpWidget(host());

      final row = tester.widget<Container>(find.byType(Container).at(1));
      final border = (row.decoration! as BoxDecoration).border! as Border;
      expect(border.top.color, AppColors.borderSoft);
      expect(border.top.width, AppShape.borderW);
    });

  });

  group('조각 6 — 캘린더 링크', () {
    testWidgets('링크 글자는 --leaf · sm · w600, 그림자 없음 (§1 · §2)', (tester) async {
      await tester.pumpWidget(host());

      final link = tester.widget<Text>(find.text('캘린더 →'));
      expect(link.style!.color, AppColors.leaf);
      expect(link.style!.fontSize, AppType.sm);
      expect(link.style!.fontWeight, AppType.wSemiBold);
      expect(link.style!.shadows, isNull);
    });

    testWidgets('누를 자리가 44×44 이상이다 (§9)', (tester) async {
      await tester.pumpWidget(host());

      final tapArea = tester.getSize(
        find.ancestor(of: find.text('캘린더 →'), matching: find.byType(InkWell)).first,
      );
      expect(tapArea.height, greaterThanOrEqualTo(AppLayout.minTouchTarget));
      expect(tapArea.width, greaterThanOrEqualTo(AppLayout.minTouchTarget));
    });

    testWidgets('오른쪽 끝이 카드 안쪽 선에 맞는다 — 위 날짜와 같은 세로선', (tester) async {
      await tester.pumpWidget(host());

      final link = tester.getRect(find.text('캘린더 →'));
      final meta = tester.getRect(find.text('2026.09.01 · 2건'));
      expect(link.right, moreOrLessEquals(meta.right, epsilon: 0.5));
    });

    testWidgets('누르면 콜백이 온다', (tester) async {
      var opened = false;
      await tester.pumpWidget(MaterialApp(
        home: Scaffold(
          body: DashboardScreen(today: aDay, onOpenCalendar: () => opened = true),
        ),
      ));

      await tester.tap(find.text('캘린더 →'));
      expect(opened, isTrue);
    });
  });

  group('조각 7 — 내 리뷰 대기', () {
    testWidgets('라벨 · 큰 숫자 · 채운 버튼', (tester) async {
      await tester.pumpWidget(host());

      expect(find.text('내 리뷰 대기'), findsOneWidget);
      // 범례에도 같은 숫자가 있어 글자로는 특정할 수 없다 — 키로 집는다
      expect(
        tester.widget<Text>(find.byKey(reviewCountKey)).data,
        '$mockReviewQueueCount',
      );
      expect(find.text('평가하러 가기'), findsOneWidget);
    });

    testWidgets('숫자는 display + 제목 그림자, 단위는 보조색 (§2)', (tester) async {
      await tester.pumpWidget(host());

      final number = tester.widget<Text>(find.byKey(reviewCountKey));
      expect(number.style!.fontSize, AppType.display);
      expect(number.style!.fontWeight, FontWeight.w700);
      expect(number.style!.shadows, AppTextShadow.heading);
      expect(number.style!.fontFeatures, AppType.tabularNums);

      final unit = tester.widget<Text>(find.byKey(reviewUnitKey));
      expect(unit.data, '명');
      expect(unit.style!.fontSize, AppType.num);
      expect(unit.style!.color, AppColors.textSub);
      // §2: 작은 글씨엔 그림자 금지
      expect(unit.style!.shadows, isNull);
    });

    testWidgets('버튼은 잎초록 · 흰 글자 · onFill 그림자 · 높이 44 (§1 · §2 · §9)', (tester) async {
      await tester.pumpWidget(host());

      final material = tester.widget<Material>(
        find.ancestor(of: find.text('평가하러 가기'), matching: find.byType(Material)).first,
      );
      expect(material.color, AppColors.leaf);

      final label = tester.widget<Text>(find.text('평가하러 가기'));
      expect(label.style!.color, AppColors.bgElev);
      expect(label.style!.shadows, AppTextShadow.onFill);

      final box = tester.getSize(
        find.ancestor(of: find.text('평가하러 가기'), matching: find.byType(InkWell)).first,
      );
      expect(box.height, AppLayout.minTouchTarget);
    });
  });

  group('조각 8 — 전형 현황', () {
    testWidgets('레일은 접수~합격 4단 — 불합격은 없다 (§0.5)', (tester) async {
      await tester.pumpWidget(host());

      final rail = tester.widget<FunnelBar>(find.byType(FunnelBar));
      expect(rail.stages, DashboardScreen.railStages);
      expect(rail.stages, isNot(contains(Stage.rejected)));
      expect(rail.keepEmptySegments, isTrue);
    });

    testWidgets('0건 구간도 6px 남는다 — §0.5 minmax(6px, n fr)', (tester) async {
      await tester.pumpWidget(
        const MaterialApp(
          home: Scaffold(
            body: Center(
              child: SizedBox(
                width: 300,
                child: FunnelBar(
                  counts: {
                    Stage.applied: 10,
                    Stage.screening: 0,
                    Stage.interview: 0,
                    Stage.accepted: 2,
                  },
                  stages: DashboardScreen.railStages,
                  keepEmptySegments: true,
                ),
              ),
            ),
          ),
        ),
      );

      final widths = tester
          .widgetList<SizedBox>(
            find.descendant(of: find.byType(Row), matching: find.byType(SizedBox)),
          )
          .map((b) => b.width)
          .whereType<double>()
          .toList();
      expect(widths.length, DashboardScreen.railStages.length);
      for (final w in widths) {
        expect(w, greaterThanOrEqualTo(6.0));
      }
      // 구간 합이 정확히 막대 폭 — 남거나 넘치지 않는다
      expect(widths.reduce((a, b) => a + b), moreOrLessEquals(300, epsilon: 0.5));
    });

    testWidgets('범례는 왼쪽부터 붙여 쓴다 — 균등 분산 금지 (§0.5)', (tester) async {
      await tester.pumpWidget(host());

      final wrap = tester.widget<Wrap>(find.byType(Wrap));
      expect(wrap.alignment, WrapAlignment.start);
      for (final stage in DashboardScreen.railStages) {
        expect(find.text(stage.label), findsWidgets);
      }
    });
  });

  group('조각 9 — 진행중 공고', () {
    testWidgets('진행중 공고만 나온다 — 마감은 없다', (tester) async {
      await tester.pumpWidget(host());

      for (final p in mockOpenPostings) {
        expect(find.text(p.title), findsWidgets);
      }
      for (final p in mockPostings.where((p) => !mockOpenPostings.contains(p))) {
        expect(find.text(p.title), findsNothing, reason: '마감된 공고');
      }
    });

    testWidgets('행 오른쪽 끝은 비워 둔다 — 아르 버튼 자리', (tester) async {
      await tester.pumpWidget(host());

      final screen = tester.getRect(find.byType(DashboardScreen));
      final meta = tester.getRect(find.textContaining('마감 D-').first);
      expect(screen.right - meta.right, greaterThan(60));
    });
  });
}
