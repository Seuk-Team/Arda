// 앱 UI 초안(2026-09-01)이 **기존 화면**에 더한 것들 — 전형 레일 · 공고 카드
// 범례 · 로그인 아르 마크. 새로 만든 화면은 각자의 테스트가 본다.

import 'package:arda/data/mock_data.dart';
import 'package:arda/models/stage.dart';
import 'package:arda/screens/applicant_detail_screen.dart';
import 'package:arda/screens/login_screen.dart';
import 'package:arda/theme/tokens.dart';
import 'package:arda/widgets/funnel_bar.dart';
import 'package:arda/widgets/funnel_legend.dart';
import 'package:arda/widgets/posting_card.dart';
import 'package:arda/widgets/stage_rail.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'app_boot.dart';

Widget detailOf(String name) {
  final applicant = mockApplicants.firstWhere((a) => a.name == name);
  return MaterialApp(
    home: ApplicantDetailScreen(
      applicant: applicant,
      postingTitle: mockPostings.first.title,
    ),
  );
}

void main() {
  group('전형 레일 (지원자 상세)', () {
    testWidgets('접수~합격 4단만 그린다 — 불합격은 레일 밖', (tester) async {
      await tester.pumpWidget(detailOf('정우진')); // 서류 검토

      expect(find.byType(StageRail), findsOneWidget);
      expect(StageRail.stages, [
        Stage.applied,
        Stage.screening,
        Stage.interview,
        Stage.accepted,
      ]);
      expect(StageRail.stages, isNot(contains(Stage.rejected)));
    });

    testWidgets('지난 단계는 체크, 지금 단계는 번호', (tester) async {
      await tester.pumpWidget(detailOf('김도현')); // 면접 = 3번째

      // 접수·서류를 지나왔으므로 체크 2개
      expect(
        find.descendant(
          of: find.byType(StageRail),
          matching: find.byIcon(Icons.check),
        ),
        findsNWidgets(2),
      );
      // 지금은 3번
      expect(
        find.descendant(of: find.byType(StageRail), matching: find.text('3')),
        findsOneWidget,
      );
    });

    testWidgets('지금 단계 라벨만 잎색 + w600 (§1)', (tester) async {
      await tester.pumpWidget(detailOf('김도현'));

      final now = tester.widget<Text>(
        find.descendant(of: find.byType(StageRail), matching: find.text('면접')),
      );
      expect(now.style!.color, AppColors.leaf);
      expect(now.style!.fontWeight, AppType.wSemiBold);

      final other = tester.widget<Text>(
        find.descendant(
          of: find.byType(StageRail),
          matching: find.text('최종 합격'),
        ),
      );
      expect(other.style!.color, AppColors.textSub);
    });

    testWidgets('불합격이면 레일을 아예 그리지 않는다', (tester) async {
      await tester.pumpWidget(detailOf('강민수')); // 불합격

      expect(StageRail.showsFor(Stage.rejected), isFalse);
      expect(find.byType(StageRail), findsNothing);
    });
  });

  group('공고 카드 퍼널 (레일 + 범례)', () {
    testWidgets('레일과 범례가 같은 단계를 쓴다', (tester) async {
      await bootToShell(tester);
      // 첫 화면은 홈(대시보드)이다 — 공고를 보려면 탭을 먼저 누른다
      await tester.tap(find.text('공고'));
      await tester.pumpAndSettle();

      final bar = tester.widget<FunnelBar>(find.byType(FunnelBar).first);
      final legend = tester.widget<FunnelLegend>(
        find.byType(FunnelLegend).first,
      );

      expect(bar.stages, PostingCard.railStages);
      // 색과 숫자가 따로 놀지 않으려면 같은 목록이어야 한다
      expect(legend.stages, bar.stages);
      expect(bar.keepEmptySegments, isTrue);
    });

    testWidgets('범례에 단계 이름과 건수가 함께 있다', (tester) async {
      await bootToShell(tester);
      // 첫 화면은 홈(대시보드)이다 — 공고를 보려면 탭을 먼저 누른다
      await tester.tap(find.text('공고'));
      await tester.pumpAndSettle();

      for (final stage in PostingCard.railStages) {
        expect(
          find.descendant(
            of: find.byType(FunnelLegend).first,
            matching: find.text(stage.label),
          ),
          findsOneWidget,
        );
      }
    });
  });

  group('로그인 아르 마크', () {
    testWidgets('로고 위에 아르가 있다', (tester) async {
      await tester.pumpWidget(const MaterialApp(home: LoginScreen()));

      final mark = find.byType(Image);
      expect(mark, findsOneWidget);
      expect(
        tester.getRect(mark).bottom,
        lessThan(tester.getRect(find.textContaining('rda')).top),
        reason: '로고보다 위',
      );
    });

    testWidgets('장식이라 낭독기에서 읽지 않는다', (tester) async {
      await tester.pumpWidget(const MaterialApp(home: LoginScreen()));

      final image = tester.widget<Image>(find.byType(Image));
      expect(image.excludeFromSemantics, isTrue);
    });
  });

  group('회귀 — 버그로 드러난 것', () {
    testWidgets('공고 카드: 총원과 범례 합이 같다', (tester) async {
      await bootToShell(tester);
      // 첫 화면은 홈(대시보드)이다 — 공고를 보려면 탭을 먼저 누른다
      await tester.tap(find.text('공고'));
      await tester.pumpAndSettle();

      final legend = tester.widget<FunnelLegend>(
        find.byType(FunnelLegend).first,
      );
      final legendSum = legend.stages.fold(
        0,
        (sum, s) => sum + (legend.counts[s] ?? 0),
      );
      final total = legend.counts.values.fold(0, (a, b) => a + b);

      expect(legendSum, total, reason: '레일이 사람을 빠뜨리면 카드 위 "N명"과 어긋나 보인다');
    });

    test('캘린더: "내 면접만" 이 실제로 거를 것이 있다', () {
      // 전부 내 면접이면 토글이 아무 일도 안 해 고장으로 보인다
      final week = mockInterviewsInWeek(DateTime(2026, 9, 1));
      final all = week.values.expand((e) => e).toList();

      expect(all.any((i) => i.interviewerName == mockMyName), isTrue);
      expect(
        all.any((i) => i.interviewerName != mockMyName),
        isTrue,
        reason: '남의 면접이 하나도 없으면 필터를 확인할 수 없다',
      );
    });
  });
}
