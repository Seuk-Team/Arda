// 아르 서버 연동 — 큐 8 5단계 (2026-09-03).
//
// **쓰기 도구는 아르가 스스로 실행하지 않는다.** 서버가 pending_action 을 주고
// 사람이 눌러야 POST /agent/confirm 이 돈다 — 05-design §1 의 "앰버 점선 = 제안 /
// 사람이 확정" 이 API 수준에서 갈려 있고, 화면이 그걸 지키는지가 핵심이다.

import 'package:arda/api/api_error.dart';
import 'package:arda/data/agent_repository.dart';
import 'package:arda/screens/ar_screen.dart';
import 'package:arda/theme/tokens.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'fake_repos.dart';

Future<void> open(WidgetTester tester, FakeAgentRepository repo) async {
  await tester.pumpWidget(MaterialApp(home: ArScreen(repository: repo)));
  await tester.pumpAndSettle();
}

Future<void> ask(WidgetTester tester, String text) async {
  await tester.enterText(find.byType(TextField), text);
  await tester.pumpAndSettle();
  await tester.tap(find.bySemanticsLabel('보내기'));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('열면 빈 화면이다 — 대화는 서버가 저장하지 않는다', (tester) async {
    await open(tester, FakeAgentRepository());

    expect(find.text('무엇을 찾아 드릴까요?'), findsOneWidget);
  });

  testWidgets('빈 칸이면 못 보낸다', (tester) async {
    final repo = FakeAgentRepository();
    await open(tester, repo);

    await tester.tap(find.bySemanticsLabel('보내기'));
    await tester.pumpAndSettle();

    expect(repo.chatCalls, 0);
  });

  testWidgets('보내면 내 말과 아르의 답이 함께 남는다', (tester) async {
    final repo = FakeAgentRepository(
      reply: const ArReply(text: '면접 단계에 2명 있습니다.'),
    );
    await open(tester, repo);
    await ask(tester, '면접 단계 지원자 보여줘');

    expect(repo.sentMessage, '면접 단계 지원자 보여줘');
    expect(find.text('면접 단계 지원자 보여줘'), findsOneWidget);
    expect(find.text('면접 단계에 2명 있습니다.'), findsOneWidget);
  });

  testWidgets('이력이 쌓여 다음 요청에 함께 간다 — 서버가 저장하지 않는다', (tester) async {
    final repo = FakeAgentRepository();
    await open(tester, repo);

    await ask(tester, '첫 질문');
    expect(repo.sentHistory, isEmpty, reason: '첫 번째는 보낼 이력이 없다');

    await ask(tester, '두 번째 질문');
    expect(repo.sentHistory.length, 2);
    expect(repo.sentHistory.first.role, 'user');
    expect(repo.sentHistory.first.content, '첫 질문');
    expect(repo.sentHistory.last.role, 'assistant');
  });

  testWidgets('무엇을 했는지 도구 줄로 적는다', (tester) async {
    await open(
      tester,
      FakeAgentRepository(
        reply: const ArReply(
          text: '2명입니다.',
          toolCalls: [
            ArToolCall(name: 'search_applications', input: {'stage': '면접'}),
          ],
        ),
      ),
    );
    await ask(tester, '면접 지원자');

    expect(find.textContaining('search_applications'), findsOneWidget);
    expect(find.textContaining('stage: 면접'), findsOneWidget);
  });

  group('확인 카드 — §1 앰버는 확정 대기에만', () {
    const pending = ArPendingAction(
      toolName: 'change_stage',
      arguments: {'application_id': 1, 'to_stage': 'interview'},
      description: '김도현을 면접 단계로 옮깁니다',
    );

    testWidgets('제안이 오면 앰버 카드가 뜬다 — 아직 실행되지 않았다', (tester) async {
      final repo = FakeAgentRepository(
        reply: const ArReply(text: '', pending: pending),
      );
      await open(tester, repo);
      await ask(tester, '김도현 면접으로 옮겨줘');

      expect(find.text('아르의 제안'), findsOneWidget);
      // 서버가 만든 문장 그대로 — 앱이 지어내면 실제와 갈린다
      expect(find.text('김도현을 면접 단계로 옮깁니다'), findsOneWidget);
      expect(repo.confirmed, isNull, reason: '누르기 전에는 실행되지 않는다');

      final box = tester.widget<Container>(
        find
            .ancestor(of: find.text('아르의 제안'), matching: find.byType(Container))
            .first,
      );
      final deco = box.decoration! as BoxDecoration;
      expect(deco.color, AppColors.aiSoft, reason: '§1 앰버');
    });

    testWidgets('[확인] 을 눌러야 실행된다', (tester) async {
      final repo = FakeAgentRepository(
        reply: const ArReply(text: '', pending: pending),
      );
      await open(tester, repo);
      await ask(tester, '옮겨줘');

      await tester.tap(find.widgetWithText(FilledButton, '확인'));
      await tester.pumpAndSettle();

      expect(repo.confirmed?.toolName, 'change_stage');
      expect(find.textContaining('실행했습니다'), findsOneWidget);
      // 실행했으면 카드가 사라진다 — 두 번 누를 자리를 남기지 않는다
      expect(find.text('아르의 제안'), findsNothing);
    });

    testWidgets('[취소] 하면 실행되지 않고 카드만 닫힌다', (tester) async {
      final repo = FakeAgentRepository(
        reply: const ArReply(text: '', pending: pending),
      );
      await open(tester, repo);
      await ask(tester, '옮겨줘');

      await tester.tap(find.widgetWithText(OutlinedButton, '취소'));
      await tester.pumpAndSettle();

      expect(repo.confirmed, isNull);
      expect(find.text('아르의 제안'), findsNothing);
    });
  });

  testWidgets('실패하면 그 줄에 적는다 — 아르가 한 말처럼 보이면 안 된다', (tester) async {
    await open(tester, FakeAgentRepository(error: const NetworkError()));
    await ask(tester, '아무거나');

    final line = tester.widget<Text>(find.textContaining('네트워크를 확인'));
    // §1: 적갈은 판단에만 — 실패가 그 판단이다
    expect(line.style!.color, AppColors.danger);
  });
}
