// 아르 — 05-design §1 의 AI 규약(앰버 점선 = 제안 / 사람이 확정)이 화면에
// 실제로 지켜지는지가 핵심이다. 잘못 그리면 "AI가 이미 했다"로 읽힌다.

import 'package:arda/data/mock_data.dart';
import 'package:arda/models/ar_message.dart';
import 'package:arda/screens/ar_screen.dart';
import 'package:arda/theme/tokens.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'app_boot.dart';

Widget host({List<ArMessage>? messages}) =>
    MaterialApp(home: ArScreen(messages: messages));

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

  group('§1 AI 규약 — 앰버 점선', () {
    testWidgets('제안 카드는 앰버 워시 바탕', (tester) async {
      await tester.pumpWidget(host());

      final card = tester.widget<Container>(
        find
            .ancestor(
              of: find.text('아르 제안 · 확인 필요'),
              matching: find.byType(Container),
            )
            .first,
      );
      expect((card.decoration! as ShapeDecoration).color, AppColors.aiSoft);
    });

    testWidgets('제목 글자는 --ai 앰버', (tester) async {
      await tester.pumpWidget(host());

      final label = tester.widget<Text>(find.text('아르 제안 · 확인 필요'));
      expect(label.style!.color, AppColors.ai);
    });

    testWidgets('승인 버튼은 잎초록 — 사람이 확정하는 쪽', (tester) async {
      await tester.pumpWidget(host());

      final confirm = mockArThread
          .firstWhere((m) => m.pendingAction != null)
          .pendingAction!
          .confirmLabel;
      final material = tester.widget<Material>(
        find
            .ancestor(of: find.text(confirm), matching: find.byType(Material))
            .first,
      );
      expect(material.color, AppColors.leaf);
    });

    testWidgets('아직 실행되지 않았다 — 승인 버튼이 잠겨 있다', (tester) async {
      await tester.pumpWidget(host());

      final confirm = mockArThread
          .firstWhere((m) => m.pendingAction != null)
          .pendingAction!
          .confirmLabel;
      final inkWell = tester.widget<InkWell>(
        find
            .ancestor(of: find.text(confirm), matching: find.byType(InkWell))
            .first,
      );
      expect(inkWell.onTap, isNull, reason: '큐 8에서 /agent/confirm 에 붙는다');
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

    testWidgets('제안 대상은 목데이터의 실제 지원자다 — 지어내지 않았다', (tester) async {
      await tester.pumpWidget(host());

      final action = mockArThread
          .firstWhere((m) => m.pendingAction != null)
          .pendingAction!;
      expect(action.targets, isNotEmpty);
      for (final target in action.targets) {
        expect(
          mockApplicants.any((a) => a.name == target.name),
          isTrue,
          reason: '${target.name} 이 목데이터에 없다',
        );
        expect(find.text(target.name), findsOneWidget);
      }
    });
  });

  testWidgets('입력칸은 아직 잠겨 있다 — 서버에 안 붙었다', (tester) async {
    await tester.pumpWidget(host());

    expect(find.text('아르에게 물어보기'), findsOneWidget);
    // 살아 있는 입력칸이 아니다 — TextField 가 있으면 보내지는 것처럼 보인다
    expect(find.byType(TextField), findsNothing);
  });
}
