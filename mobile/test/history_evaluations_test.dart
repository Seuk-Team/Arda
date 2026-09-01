// 단계 이력 · 평가 목록 — 시안(2026-08-28) 2·3번.
// 둘 다 상세에서 들어가는 별도 화면이다.

import 'package:arda/models/evaluation.dart' as model;
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'app_boot.dart';

/// 공고 → 지원자 → 김도현 상세까지 연다.
/// 김도현은 단계 이력 4건·평가 3건을 가진 유일한 목데이터다.
Future<void> openKimDohyun(WidgetTester tester) async {
  await bootToShell(tester);
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

/// 상세 아래쪽 링크까지 내려간다.
///
/// 아르의 요약·시스템·메모가 들어오면서 [단계 이력]·[평가] 가 화면 밖으로
/// 밀렸다. SingleChildScrollView 라 위젯은 만들어져 있지만 탭이 닿지 않는다.
Future<void> scrollToLinks(WidgetTester tester, String label) async {
  await tester.dragUntilVisible(
    find.text(label),
    find.byType(Scrollable).first,
    const Offset(0, -300),
  );
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

  testWidgets('상세의 단계 이력 미리보기가 최근 두 건을 보여 준다', (tester) async {
    await openKimDohyun(tester);
    await scrollToLinks(tester, '단계 이력');

    // 초안: 최신 두 건만. 08.24(서류→면접)·08.27(면접→최종 합격)
    expect(find.text('08.27'), findsOneWidget);
    expect(find.text('면접 → 최종 합격'), findsOneWidget);
    expect(find.text('08.24'), findsOneWidget);
    // 세 번째(08.21)부터는 [전체 →] 뒤에 있다
    expect(find.text('08.21'), findsNothing);
  });

  testWidgets('상세에서 단계 이력으로 들어간다', (tester) async {
    await openKimDohyun(tester);

    // 초안: 제목은 더 이상 링크가 아니고 오른쪽 [전체 →] 가 문이다
    await scrollToLinks(tester, '전체 →');
    await tester.tap(find.text('전체 →'));
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

    await scrollToLinks(tester, '평가');
    await tester.tap(find.text('평가'));
    await tester.pumpAndSettle();

    // 평균을 먼저, 개별을 다음에
    expect(find.text('4.3'), findsOneWidget);
    expect(find.text('3명이 평가했습니다'), findsOneWidget);
    expect(find.text('이지훈'), findsOneWidget);
  });

  testWidgets('두 화면 모두 뒤로가기로 상세로 돌아온다', (tester) async {
    await openKimDohyun(tester);

    await scrollToLinks(tester, '평가');
    await tester.tap(find.text('평가'));
    await tester.pumpAndSettle();
    await tester.tap(find.bySemanticsLabel('뒤로'));
    await tester.pumpAndSettle();

    expect(find.text('단계 변경'), findsOneWidget); // 상세로 돌아옴
  });
}
