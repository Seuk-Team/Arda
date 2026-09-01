// 지원자 탭 — 05-design §0.5 "전 공고 통합 검색 · 칸반 없음", §9 "테이블은 카드형".

import 'package:arda/data/mock_data.dart';
import 'package:arda/models/applicant.dart';
import 'package:arda/models/stage.dart';
import 'package:arda/screens/applicants_search_screen.dart';
import 'package:arda/widgets/applicant_card.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

Widget host({void Function(Applicant, String)? onOpen}) => MaterialApp(
  home: Scaffold(body: ApplicantsSearchScreen(onOpenApplicant: onOpen)),
);

Future<void> type(WidgetTester tester, String term) async {
  await tester.enterText(find.byType(TextField), term);
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('처음에는 전 공고 지원자가 모두 나온다', (tester) async {
    await tester.pumpWidget(host());

    // ListView 는 화면 밖 카드를 만들지 않는다 — 총 개수는 건수 라벨이 계약이다
    expect(find.byType(ApplicantCard), findsWidgets);
    expect(find.text('${mockApplicants.length}건'), findsOneWidget);
  });

  testWidgets('카드에 공고명이 함께 있다 — 공고를 가리지 않는 화면이라', (tester) async {
    await tester.pumpWidget(host());

    final card = tester.widget<ApplicantCard>(find.byType(ApplicantCard).first);
    expect(card.postingTitle, isNotNull);
    expect(find.text(mockPostings.first.title), findsWidgets);
  });

  testWidgets('이름으로 걸러진다', (tester) async {
    await tester.pumpWidget(host());
    await type(tester, '김도현');

    expect(find.byType(ApplicantCard), findsOneWidget);
    expect(find.text('1건'), findsOneWidget);
  });

  testWidgets('공고명으로도 걸러진다 — placeholder 가 약속한 대로', (tester) async {
    await tester.pumpWidget(host());
    expect(find.text('이름 또는 공고 검색'), findsOneWidget);

    await type(tester, '백엔드');
    expect(find.byType(ApplicantCard), findsWidgets);
  });

  testWidgets('단계 칩으로 걸러진다 — 전체가 기본', (tester) async {
    await tester.pumpWidget(host());
    expect(find.text('전체'), findsOneWidget);

    await tester.tap(find.text(Stage.interview.label).first);
    await tester.pumpAndSettle();

    final expected = mockApplicants
        .where((a) => a.currentStage == Stage.interview)
        .length;
    expect(find.byType(ApplicantCard), findsNWidgets(expected));
    expect(find.text('$expected건'), findsOneWidget);
  });

  testWidgets('검색 + 단계 칩이 함께 걸린다', (tester) async {
    await tester.pumpWidget(host());

    await tester.tap(find.text(Stage.interview.label).first);
    await tester.pumpAndSettle();
    await type(tester, '김도현');

    expect(find.byType(ApplicantCard), findsOneWidget);
  });

  testWidgets('결과가 없으면 웹과 같은 문구 (§6)', (tester) async {
    await tester.pumpWidget(host());
    await type(tester, '없는사람이름');

    expect(find.text('0건'), findsOneWidget);
    expect(find.text('검색 결과가 없습니다.'), findsOneWidget);
    // 검색 중이 아닐 때의 문구와 구별된다
    expect(find.text('등록된 지원자가 없습니다.'), findsNothing);
  });

  testWidgets('검색어를 지우면 다시 전체가 나온다', (tester) async {
    await tester.pumpWidget(host());
    await type(tester, '김도현');
    expect(find.byType(ApplicantCard), findsOneWidget);

    await tester.tap(find.byTooltip('검색어 지우기'));
    await tester.pumpAndSettle();
    // ListView 는 화면 밖 카드를 만들지 않는다 — 총 개수는 건수 라벨이 계약이다
    expect(find.byType(ApplicantCard), findsWidgets);
    expect(find.text('${mockApplicants.length}건'), findsOneWidget);
  });

  testWidgets('카드를 누르면 상세로 넘긴다', (tester) async {
    Applicant? opened;
    String? title;
    await tester.pumpWidget(host(onOpen: (a, t) {
      opened = a;
      title = t;
    }));

    await tester.tap(find.byType(ApplicantCard).first);
    await tester.pumpAndSettle();

    expect(opened, isNotNull);
    expect(title, isNotNull);
  });

  testWidgets('칸반은 없다 — 05-design §0.5', (tester) async {
    await tester.pumpWidget(host());
    expect(find.textContaining('칸반'), findsNothing);
  });
}
