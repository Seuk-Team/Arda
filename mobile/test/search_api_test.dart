// 통합 검색이 서버로 간다 — 큐 8 4단계 (2026-09-03).
//
// 화면 규칙(칩·빈 문구·카드)은 applicants_search_screen_test.dart 가 본다.
// 여기서는 **서버로 뭘 보내고 어떻게 이어 붙이는지**만 본다.

import 'package:arda/api/api_error.dart';
import 'package:arda/data/mock_data.dart';
import 'package:arda/models/applicant.dart';
import 'package:arda/models/stage.dart';
import 'package:arda/screens/applicants_search_screen.dart';
import 'package:arda/widgets/applicant_card.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'fake_repos.dart';

Future<void> open(
  WidgetTester tester,
  FakeApplicantRepository repo, {
  FakePostingRepository? postings,
}) async {
  await tester.pumpWidget(
    MaterialApp(
      home: Scaffold(
        body: ApplicantsSearchScreen(
          repository: repo,
          postingRepository: postings ?? FakePostingRepository(),
        ),
      ),
    ),
  );
  await tester.pumpAndSettle();
}

/// 디바운스를 지나 실제로 보내지는 지점까지 간다
Future<void> typeAndSettle(WidgetTester tester, String term) async {
  await tester.enterText(find.byType(TextField), term);
  await tester.pump(const Duration(milliseconds: 350));
  await tester.pumpAndSettle();
}

void main() {
  group('보내는 조건', () {
    testWidgets('열자마자 한 번 받는다 — 검색어 없이 전체', (tester) async {
      final repo = FakeApplicantRepository();
      await open(tester, repo);

      expect(repo.searchCalls, 1);
      expect(repo.searchedStage, isNull);
      expect(repo.searchedOffset, 0);
    });

    testWidgets('타자마다 보내지 않는다 — 300ms 쉬어야 한 번 간다', (tester) async {
      final repo = FakeApplicantRepository();
      await open(tester, repo);
      final before = repo.searchCalls;

      // 빠르게 세 글자를 친다
      for (final t in ['김', '김도', '김도현']) {
        await tester.enterText(find.byType(TextField), t);
        await tester.pump(const Duration(milliseconds: 100));
      }
      // 아직 안 갔다
      expect(repo.searchCalls, before);

      await tester.pump(const Duration(milliseconds: 350));
      await tester.pumpAndSettle();
      expect(repo.searchCalls, before + 1, reason: '마지막 한 번만');
      expect(repo.searchedQuery, '김도현');
    });

    testWidgets('단계 칩은 즉시 간다 — 타자와 달리 연달아 눌리지 않는다', (tester) async {
      final repo = FakeApplicantRepository();
      await open(tester, repo);
      final before = repo.searchCalls;

      await tester.tap(find.text(Stage.interview.label).first);
      await tester.pumpAndSettle();

      expect(repo.searchCalls, before + 1);
      expect(repo.searchedStage, Stage.interview);
    });

    testWidgets('공고명을 치면 q 가 아니라 posting_id 로 좁힌다', (tester) async {
      // 서버 `q` 는 이름·이메일만 본다(search.py:120) — 공고는 id 로 좁혀야 한다
      final repo = FakeApplicantRepository();
      await open(tester, repo);

      await typeAndSettle(tester, mockPostings.first.title);

      expect(repo.searchedPostingId, mockPostings.first.id);
      expect(repo.searchedQuery, isNull, reason: '둘 다 보내면 AND 라 교집합이 된다');
    });
  });

  group('더 보기', () {
    /// 30개를 넘겨야 버튼이 나온다
    List<Applicant> many(int n) => [
      for (var i = 0; i < n; i++)
        Applicant(
          id: 1000 + i,
          jobPostingId: mockPostings.first.id,
          name: '지원자$i',
          email: 'a$i@example.com',
          currentStage: Stage.applied,
          createdAt: DateTime(2026, 9, 1),
        ),
    ];

    testWidgets('받아 둔 것보다 전체가 많으면 [더 보기] 가 있다', (tester) async {
      await open(tester, FakeApplicantRepository(searchResults: many(45)));

      expect(find.text('45건'), findsOneWidget, reason: '서버가 센 전체를 적는다');
      await tester.dragUntilVisible(
        find.text('더 보기'),
        find.byType(Scrollable).last,
        const Offset(0, -400),
      );
      expect(find.text('더 보기'), findsOneWidget);
    });

    testWidgets('누르면 뒤에 이어 붙인다 — 앞 것이 사라지지 않는다', (tester) async {
      final repo = FakeApplicantRepository(searchResults: many(45));
      await open(tester, repo);

      await tester.dragUntilVisible(
        find.text('더 보기'),
        find.byType(Scrollable).last,
        const Offset(0, -400),
      );
      await tester.tap(find.text('더 보기'));
      await tester.pumpAndSettle();

      // 두 번째 쪽을 30번째부터 달라고 했다
      expect(repo.searchedOffset, 30);
      // 다 받았으니 버튼이 사라진다
      expect(find.text('더 보기'), findsNothing);
    });

    testWidgets('전체를 다 받았으면 [더 보기] 가 없다', (tester) async {
      await open(tester, FakeApplicantRepository(searchResults: many(5)));

      expect(find.byType(ApplicantCard), findsWidgets);
      expect(find.text('더 보기'), findsNothing);
    });
  });

  testWidgets('실패하면 서버 문구 + [다시 시도] (§6)', (tester) async {
    await open(tester, FakeApplicantRepository(error: const NetworkError()));

    expect(find.textContaining('네트워크를 확인'), findsOneWidget);
    expect(find.text('다시 시도'), findsOneWidget);
  });
}
