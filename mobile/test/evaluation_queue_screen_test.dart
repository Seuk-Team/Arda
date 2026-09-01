// 평가 현황 — 05-design §6 의 세 상태를 한 화면에서 전부 검증한다.
// 문구는 웹(Evaluations.tsx)에서 가져온 것이라 글자 그대로 비교한다.

import 'package:arda/data/mock_data.dart';
import 'package:arda/screens/evaluation_queue_screen.dart';
import 'package:arda/theme/tokens.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

Widget host(QueueLoader loader) =>
    MaterialApp(home: EvaluationQueueScreen(loader: loader));

QueueEntry entryFor(int applicantId) {
  final applicant = mockApplicants.firstWhere((a) => a.id == applicantId);
  final title = mockPostings
      .firstWhere((p) => p.id == applicant.jobPostingId)
      .title;
  return (applicant, title);
}

void main() {
  group('§6 로딩', () {
    testWidgets('불러오는 동안 문구 + 골격 카드', (tester) async {
      await tester.pumpWidget(
        host(() => Future.delayed(const Duration(seconds: 1), () => const [])),
      );
      await tester.pump(); // 첫 프레임 — 아직 대기 중

      expect(find.text('불러오는 중…'), findsOneWidget);
      // 골격 3장 — 곧 무엇이 올지 자리로 알려 준다
      expect(find.byType(FractionallySizedBox), findsNWidgets(9));

      // 남은 타이머를 흘려보낸다 — 안 그러면 '보류 중인 타이머' 로 실패한다
      await tester.pump(const Duration(seconds: 1));
    });
  });

  group('§6 비어 있음', () {
    testWidgets('웹과 같은 문구', (tester) async {
      await tester.pumpWidget(host(() async => const []));
      await tester.pumpAndSettle();

      expect(find.text('평가 대기 중인 지원자가 없습니다.'), findsOneWidget);
      expect(find.text('불러오는 중…'), findsNothing);
    });
  });

  group('§6 오류', () {
    testWidgets('웹 문구 + [다시 시도] — 앱엔 새로고침이 없다', (tester) async {
      await tester.pumpWidget(host(() async => throw Exception('boom')));
      await tester.pumpAndSettle();

      expect(find.text('평가 대기 목록을 불러오지 못했습니다'), findsOneWidget);
      expect(find.text('다시 시도'), findsOneWidget);
    });

    testWidgets('오류 문구는 적갈, 워시 배경 (§1)', (tester) async {
      await tester.pumpWidget(host(() async => throw Exception('boom')));
      await tester.pumpAndSettle();

      final message = tester.widget<Text>(
        find.text('평가 대기 목록을 불러오지 못했습니다'),
      );
      expect(message.style!.color, AppColors.danger);

      final box = tester.widget<Container>(
        find.ancestor(
          of: find.text('평가 대기 목록을 불러오지 못했습니다'),
          matching: find.byType(Container),
        ).last,
      );
      expect((box.decoration! as BoxDecoration).color, AppColors.dangerSoft);
    });

    testWidgets('[다시 시도] 를 누르면 다시 부른다', (tester) async {
      var calls = 0;
      await tester.pumpWidget(
        host(() async {
          calls++;
          if (calls == 1) throw Exception('boom');
          return [entryFor(4)];
        }),
      );
      await tester.pumpAndSettle();
      expect(find.text('다시 시도'), findsOneWidget);

      await tester.tap(find.text('다시 시도'));
      await tester.pumpAndSettle();

      expect(calls, 2);
      expect(find.text('평가 대기 목록을 불러오지 못했습니다'), findsNothing);
      expect(find.text('정우진'), findsOneWidget);
    });

    testWidgets('[다시 시도] 는 터치 타깃 44 (§9)', (tester) async {
      await tester.pumpWidget(host(() async => throw Exception('boom')));
      await tester.pumpAndSettle();

      final size = tester.getSize(
        find.ancestor(of: find.text('다시 시도'), matching: find.byType(InkWell)).first,
      );
      expect(size.height, AppLayout.minTouchTarget);
      expect(size.width, greaterThanOrEqualTo(AppLayout.minTouchTarget));
    });
  });

  group('목록', () {
    testWidgets('대기 인원과 카드가 나온다', (tester) async {
      await tester.pumpWidget(host(() async => [entryFor(4), entryFor(1)]));
      await tester.pumpAndSettle();

      expect(find.text('평가 대기 2명'), findsOneWidget);
      expect(find.text('정우진'), findsOneWidget);
      expect(find.text('김도현'), findsOneWidget);
    });

    testWidgets('카드에 공고와 단계가 함께 있다', (tester) async {
      await tester.pumpWidget(host(() async => [entryFor(4)]));
      await tester.pumpAndSettle();

      expect(find.text(mockPostings.first.title), findsOneWidget);
      expect(find.text('서류 검토'), findsOneWidget);
    });
  });

  // testWidgets 가 아니라 test 다. 목 로더 안의 Future.delayed 는 위젯 테스트의
  // 가짜 시계에서 스스로 깨어나지 않아, pump 없이 await 하면 그대로 멈춘다.
  test('목 로더는 평가 기록이 없는 서류·면접 단계만 준다', () async {
    final queue = await mockQueueLoader();

    expect(queue, isNotEmpty);
    for (final (applicant, _) in queue) {
      expect(mockEvaluations.containsKey(applicant.id), isFalse);
    }
    expect(queue.length, mockReviewQueueCount);
  });
}
