// 퍼널 바 — 눈으로는 "가늘어서 안 보이는 것"과 "높이가 0인 것"이 구분되지 않는다.
// 실제로 8dp 로 그려지는지, 비율이 인원에 맞는지 크기로 검증한다.

import 'package:arda/models/stage.dart';
import 'package:arda/widgets/funnel_bar.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  Widget wrap(Map<Stage, int> counts) => MaterialApp(
    home: Scaffold(
      body: Center(
        child: SizedBox(width: 300, child: FunnelBar(counts: counts)),
      ),
    ),
  );

  testWidgets('막대 높이가 8dp 다', (tester) async {
    await tester.pumpWidget(wrap({Stage.applied: 3, Stage.interview: 1}));

    expect(tester.getSize(find.byType(FunnelBar)).height, 8);
  });

  testWidgets('구간 폭이 인원 비율을 따른다', (tester) async {
    await tester.pumpWidget(wrap({Stage.applied: 3, Stage.interview: 1}));

    // 3 : 1 이면 300px 이 225 : 75 로 나뉜다
    final segments = tester
        .widgetList<Expanded>(find.byType(Expanded))
        .map((e) => e.flex)
        .toList();
    expect(segments, [3, 1]);

    final boxes = find.byType(DecoratedBox);
    expect(tester.getSize(boxes.at(0)).width, 225);
    expect(tester.getSize(boxes.at(1)).width, 75);
    // 모든 구간이 실제 두께를 가진다 — 0 이면 화면에서 사라진다
    expect(tester.getSize(boxes.at(0)).height, 8);
  });

  testWidgets('인원 0인 단계는 구간을 차지하지 않는다', (tester) async {
    await tester.pumpWidget(wrap({Stage.applied: 2, Stage.rejected: 0}));

    expect(find.byType(Expanded), findsOneWidget);
  });

  testWidgets('아무도 없으면 빈 트랙만 그린다', (tester) async {
    await tester.pumpWidget(wrap({for (final s in Stage.values) s: 0}));

    expect(find.byType(Expanded), findsNothing);
    expect(tester.getSize(find.byType(FunnelBar)).height, 8);
  });
}
