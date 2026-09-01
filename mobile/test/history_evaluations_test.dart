// 단계 이력 · 평가 목록 — 시안(2026-08-28) 2·3번.
// 둘 다 상세에서 들어가는 별도 화면이다.

import 'package:arda/main.dart';
import 'package:arda/models/evaluation.dart' as model;
import 'package:flutter_test/flutter_test.dart';

/// 공고 → 지원자 → 김도현 상세까지 연다.
/// 김도현은 단계 이력 4건·평가 3건을 가진 유일한 목데이터다.
Future<void> openKimDohyun(WidgetTester tester) async {
  await tester.pumpWidget(const ArdaApp());
  // 첫 화면은 홈(대시보드)이다 — 공고를 보려면 탭을 먼저 누른다
  await tester.tap(find.text('공고'));
  await tester.pumpAndSettle();

  await tester.tap(find.text('백엔드 개발자 (신입)'));
  await tester.pumpAndSettle();

  await tester.tap(find.text('면접'));
  await tester.pumpAndSettle();

  await tester.tap(find.text('김도현'));
  await tester.pumpAndSettle();
}

void main() {
  group('평균 계산', () {
    test('5·4·4 면 4.3 — 소수 첫째 자리', () {
      final s = model.EvaluationSummary(
        items: [
          for (final score in [5, 4, 4])
            model.Evaluation(
              id: score,
              applicationId: 1,
              evaluatorName: '평가자',
              score: score,
              createdAt: DateTime(2026, 8, 24),
            ),
        ],
      );
      expect(s.avgScore, 4.3);
      expect(s.count, 3);
    });

    test('평가가 없으면 null — D1 지시서', () {
      const s = model.EvaluationSummary(items: []);
      expect(s.avgScore, isNull);
      expect(s.count, 0);
    });

    test('점수 분포를 센다', () {
      final s = model.EvaluationSummary(
        items: [
          for (final score in [5, 4, 4])
            model.Evaluation(
              id: score,
              applicationId: 1,
              evaluatorName: '평가자',
              score: score,
              createdAt: DateTime(2026, 8, 24),
            ),
        ],
      );
      expect(s.distribution[5], 1);
      expect(s.distribution[4], 2);
      expect(s.distribution[3], 0);
    });
  });

  testWidgets('상세에서 단계 이력으로 들어간다', (tester) async {
    await openKimDohyun(tester);

    await tester.tap(find.text('단계 이력'));
    await tester.pumpAndSettle();

    // 최신이 위 — 최종 합격이 첫 항목
    expect(find.text('최종 합격'), findsOneWidget);
    // "어디에서 왔는지"를 같이 적는다
    expect(find.text('면접에서'), findsOneWidget);
    // 메일 발송 여부
    expect(find.text('최종 합격 안내 메일 발송됨'), findsOneWidget);
    // 최초 접수는 from_stage 가 NULL, changed_by 도 NULL(시스템)
    expect(find.textContaining('지원자 제출'), findsOneWidget);
  });

  testWidgets('상세에서 평가로 들어간다', (tester) async {
    await openKimDohyun(tester);

    await tester.tap(find.text('평가'));
    await tester.pumpAndSettle();

    // 평균을 먼저, 개별을 다음에
    expect(find.text('4.3'), findsOneWidget);
    expect(find.text('3명이 평가했습니다'), findsOneWidget);
    expect(find.text('이지훈'), findsOneWidget);
  });

  testWidgets('두 화면 모두 뒤로가기로 상세로 돌아온다', (tester) async {
    await openKimDohyun(tester);

    await tester.tap(find.text('평가'));
    await tester.pumpAndSettle();
    await tester.tap(find.bySemanticsLabel('뒤로'));
    await tester.pumpAndSettle();

    expect(find.text('단계 변경'), findsOneWidget); // 상세로 돌아옴
  });
}
