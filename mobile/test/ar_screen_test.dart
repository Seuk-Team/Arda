// 아르 — 05-design §1 의 AI 규약이 화면에 실제로 지켜지는지가 핵심이다.
// 앰버는 사람의 확정을 기다리는 것에만 쓴다(2026-09-01 개정). 앱의 아르는
// 찾아 주기까지만 하고 확정 버튼이 없으므로 명단 카드는 정보 블록이어야 한다.

import 'package:arda/data/mock_data.dart';
import 'package:arda/models/ai_summary.dart';
import 'package:arda/models/ar_message.dart';
import 'package:arda/screens/ar_screen.dart';
import 'package:arda/theme/tokens.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'app_boot.dart';

/// 명단 카드 같은 화면 규칙을 보려면 대화가 있어야 한다. 큐 8 5단계로 서버에
/// 붙으면서 기본 대화가 사라졌으므로(시트를 열면 빈 화면이다) 목 대화를 넣는다
Widget host({List<ArMessage>? messages}) =>
    MaterialApp(home: ArScreen(messages: messages ?? mockArThread));

void main() {
  group('진입점 — 전 화면 공통 (§0.5)', () {
    testWidgets('탭이 있는 화면에는 오른쪽 아래 아르 버튼', (tester) async {
      await bootToShell(tester);

      final button = find.bySemanticsLabel('아르에게 물어보기');
      expect(button, findsOneWidget);

      final screen = tester.getSize(find.byType(MaterialApp));
      final box = tester.getRect(button);
      expect(box.right, greaterThan(screen.width / 2), reason: '오른쪽');
      expect(box.top, greaterThan(screen.height / 2), reason: '아래쪽');
      expect(box.width, greaterThanOrEqualTo(AppLayout.minTouchTarget));
    });

    testWidgets('누르면 아르 시트가 열린다', (tester) async {
      await bootToShell(tester);

      await tester.tap(find.bySemanticsLabel('아르에게 물어보기'));
      await tester.pumpAndSettle();

      expect(find.byType(ArScreen), findsOneWidget);
      expect(find.text('아르'), findsOneWidget);
      expect(find.text('에이전트'), findsOneWidget);
    });

    testWidgets('닫으면 원래 화면으로 돌아온다', (tester) async {
      await bootToShell(tester);

      await tester.tap(find.bySemanticsLabel('아르에게 물어보기'));
      await tester.pumpAndSettle();
      await tester.tap(find.bySemanticsLabel('닫기'));
      await tester.pumpAndSettle();

      expect(find.byType(ArScreen), findsNothing);
    });
  });

  group('§1 AI 규약 — 확정 대기가 아니면 앰버가 아니다', () {
    testWidgets('명단 카드는 앰버가 아니라 정보 블록이다', (tester) async {
      await tester.pumpWidget(host());

      final card = tester.widget<Container>(
        find
            .ancestor(
              of: find.text('아르가 찾은 지원자'),
              matching: find.byType(Container),
            )
            .first,
      );
      final deco = card.decoration! as BoxDecoration;

      // 상세의 아르의 요약과 같은 값 — 두 AI 블록이 같은 옷을 입는다
      expect(deco.color, AppColors.bgSunken);
      expect((deco.border! as Border).top.color, AppColors.borderSoft);
      expect((deco.border! as Border).top.style, BorderStyle.solid);

      expect(deco.color, isNot(AppColors.aiSoft));
      final title = tester.widget<Text>(find.text('아르가 찾은 지원자'));
      expect(title.style!.color, isNot(AppColors.ai));
    });

    testWidgets('단계를 바꾸는 버튼이 없다 — 그건 상세 하나로 모은다', (tester) async {
      await tester.pumpWidget(host());

      for (final label in ['면접으로 옮기기', '단계 변경', '승인']) {
        expect(find.text(label), findsNothing, reason: '$label 이 카드에 있다');
      }
    });

    testWidgets('[지원자 정보 보기] 는 살아 있다 — 상세로 간다', (tester) async {
      await tester.pumpWidget(host());

      final inkWell = tester.widget<InkWell>(
        find
            .ancestor(
              of: find.text('지원자 정보 보기'),
              matching: find.byType(InkWell),
            )
            .first,
      );
      expect(inkWell.onTap, isNotNull);
    });

    testWidgets('사람마다 아르의 요지가 함께 나온다', (tester) async {
      await tester.pumpWidget(host());

      final found = mockArThread
          .firstWhere((m) => m.findings != null)
          .findings!
          .applicants;

      for (final a in found) {
        expect(a.gist, isNotNull, reason: '${a.name} 요지 없음');
        expect(find.text(a.gist!), findsOneWidget);
      }
    });
  });

  group('대화', () {
    testWidgets('아르와 내 말풍선이 좌우로 갈린다', (tester) async {
      await tester.pumpWidget(
        host(
          messages: const [
            ArMessage(speaker: ArSpeaker.ar, text: '아르 말'),
            ArMessage(speaker: ArSpeaker.me, text: '내 말'),
          ],
        ),
      );

      final width = tester.getSize(find.byType(MaterialApp)).width;
      expect(tester.getRect(find.text('아르 말')).left, lessThan(width / 2));
      expect(tester.getRect(find.text('내 말')).right, greaterThan(width / 2));
    });

    testWidgets('내 말풍선은 잎초록 + onFill 그림자 (§2)', (tester) async {
      await tester.pumpWidget(
        host(
          messages: const [ArMessage(speaker: ArSpeaker.me, text: '내 말')],
        ),
      );

      final text = tester.widget<Text>(find.text('내 말'));
      expect(text.style!.color, AppColors.bgElev);
      expect(text.style!.shadows, AppTextShadow.onFill);
    });

    testWidgets('명단은 목데이터의 실제 지원자다 — 지어내지 않았다', (tester) async {
      await tester.pumpWidget(host());

      final findings = mockArThread
          .firstWhere((m) => m.findings != null)
          .findings!;
      expect(findings.applicants, isNotEmpty);

      for (final found in findings.applicants) {
        final real = mockApplicants.where((a) => a.id == found.applicationId);
        expect(real, hasLength(1), reason: '${found.name} 이 목데이터에 없다');
        expect(real.single.name, found.name);
        // 요지도 상세와 같은 값이어야 한다 — 두 화면이 다른 말을 하면 안 된다
        expect(found.gist, AiSummary.parse(real.single.aiSummary!).gist);
        expect(find.text(found.name), findsOneWidget);
      }
    });
  });

  testWidgets('입력칸이 살아 있다 — 큐 8 5단계(2026-09-03)에서 잠금을 풀었다', (tester) async {
    await tester.pumpWidget(host());

    expect(find.widgetWithText(TextField, '아르에게 물어보기'), findsOneWidget);
  });
}
