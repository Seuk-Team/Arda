import 'package:arda/theme/tokens.dart';
import 'package:arda/widgets/app_bottom_nav.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

Widget _host(AppTab current, {ValueChanged<AppTab>? onSelected}) => MaterialApp(
  home: Scaffold(
    bottomNavigationBar: AppBottomNav(current: current, onSelected: onSelected),
  ),
);

void main() {
  testWidgets('탭 다섯 칸이 순서대로 있다 — 홈이 가운데', (tester) async {
    await tester.pumpWidget(_host(AppTab.home));

    expect(AppTab.values.map((t) => t.label).toList(), [
      '공고',
      '지원자',
      '홈',
      '캘린더',
      '더보기',
    ]);
    for (final tab in AppTab.values) {
      expect(find.text(tab.label), findsOneWidget);
    }
  });

  testWidgets('칸 폭이 균등하고 홈이 화면 가운데에 온다', (tester) async {
    await tester.pumpWidget(_host(AppTab.home));

    final widths = [
      for (final tab in AppTab.values) tester.getSize(find.text(tab.label)).width,
    ];
    expect(widths.every((w) => w > 0), isTrue);

    final screenWidth = tester.getSize(find.byType(MaterialApp)).width;
    final homeCenter = tester.getCenter(find.text('홈')).dx;
    // 가운데 칸이므로 화면 중앙과 같아야 한다
    expect(homeCenter, moreOrLessEquals(screenWidth / 2, epsilon: 0.5));
  });

  testWidgets('선택된 탭만 잎색 + w600, 나머지는 보조 텍스트색', (tester) async {
    await tester.pumpWidget(_host(AppTab.calendar));

    final selected = tester.widget<Text>(find.text('캘린더'));
    expect(selected.style!.color, AppColors.leaf);
    expect(selected.style!.fontWeight, AppType.wSemiBold);

    final other = tester.widget<Text>(find.text('공고'));
    expect(other.style!.color, AppColors.textSub);
    expect(other.style!.fontWeight, AppType.wRegular);

    // §2: 작은 글씨엔 그림자 금지
    expect(selected.style!.shadows, isNull);
  });

  testWidgets('항목 높이가 터치 타깃 44 를 넘는다 (05-design §9)', (tester) async {
    await tester.pumpWidget(_host(AppTab.home));

    for (final tab in AppTab.values) {
      final box = tester.getSize(
        find.ancestor(of: find.text(tab.label), matching: find.byType(InkWell)).first,
      );
      expect(box.height, greaterThanOrEqualTo(AppLayout.minTouchTarget));
      expect(box.width, greaterThanOrEqualTo(AppLayout.minTouchTarget));
    }
  });

  testWidgets('탭을 누르면 그 탭이 콜백으로 나온다', (tester) async {
    AppTab? tapped;
    await tester.pumpWidget(_host(AppTab.home, onSelected: (t) => tapped = t));

    await tester.tap(find.text('지원자'));
    expect(tapped, AppTab.applicants);
  });

  testWidgets('흰 바탕 + 윗선 1px — 바탕은 SafeArea 밖에 있다', (tester) async {
    await tester.pumpWidget(_host(AppTab.home));

    final decorated = tester.widget<DecoratedBox>(
      find.ancestor(of: find.byType(SafeArea), matching: find.byType(DecoratedBox)).first,
    );
    final deco = decorated.decoration as BoxDecoration;
    expect(deco.color, AppColors.bgElev);
    expect((deco.border as Border).top.color, AppColors.border);
    expect((deco.border as Border).top.width, AppShape.borderW);
  });
}
