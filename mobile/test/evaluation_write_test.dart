// 평가 쓰기 — 큐 8 3단계 (2026-09-03).
//
// **핵심은 중복이다.** 서버도 웹도 같은 사람이 여러 번 평가하는 것을 막지
// 않아서, 그냥 POST 하면 한 사람이 여러 줄을 남기고 평균과 "n명이 평가함" 이
// 둘 다 틀어진다. 앱은 내가 쓴 것이 있으면 PATCH 로 고친다.

import 'package:arda/api/api_error.dart';
import 'package:arda/auth/current_user.dart';
import 'package:arda/data/mock_data.dart';
import 'package:arda/models/app_user.dart';
import 'package:arda/models/evaluation.dart' as model;
import 'package:arda/screens/evaluations_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'fake_repos.dart';

final dohyun = mockApplicants.firstWhere((a) => a.name == '김도현');

/// 나 — id 7. 평가에 붙는 `evaluator_id` 와 맞춰 본다
const myId = 7;

model.Evaluation eval({
  required int id,
  required int score,
  int? evaluatorId,
  String? comment,
}) => model.Evaluation(
  id: id,
  applicationId: dohyun.id,
  evaluatorId: evaluatorId,
  score: score,
  comment: comment,
  createdAt: DateTime(2026, 9, 1),
);

Future<void> open(
  WidgetTester tester,
  FakeApplicantRepository repo, {
  bool loggedIn = true,
}) async {
  final user = CurrentUser(
    loggedIn
        ? const AppUser(
            id: myId,
            email: 'me@example.com',
            name: '김민아',
            role: UserRole.member,
          )
        : null,
  );

  await tester.pumpWidget(
    CurrentUserScope(
      notifier: user,
      child: MaterialApp(
        home: EvaluationsScreen(applicant: dohyun, repository: repo),
      ),
    ),
  );
  await tester.pumpAndSettle();
}

Future<void> pickAndSave(WidgetTester tester, int score, String label) async {
  await tester.tap(find.bySemanticsLabel('$score점'));
  await tester.pumpAndSettle();
  await tester.tap(find.widgetWithText(FilledButton, label));
  await tester.pumpAndSettle();
}

void main() {
  group('처음 쓰는 평가', () {
    testWidgets('점수를 안 고르면 저장이 잠겨 있다', (tester) async {
      final repo = FakeApplicantRepository(
        evaluationSummary: const model.EvaluationSummary(items: []),
      );
      await open(tester, repo);

      final save = tester.widget<FilledButton>(
        find.widgetWithText(FilledButton, '저장'),
      );
      // 서버도 422 로 막지만 헛걸음을 만들지 않는다
      expect(save.onPressed, isNull);
      expect(repo.addedScore, isNull);
    });

    testWidgets('고른 점수와 코멘트가 그대로 간다', (tester) async {
      final repo = FakeApplicantRepository(
        evaluationSummary: const model.EvaluationSummary(items: []),
      );
      await open(tester, repo);

      await tester.enterText(find.byType(TextField), '아키텍처 이해가 좋다');
      await tester.pumpAndSettle();
      await pickAndSave(tester, 4, '저장');

      expect(repo.addedScore, 4);
      expect(repo.addedComment, '아키텍처 이해가 좋다');
      // 새로 쓰는 것이니 고치기는 안 불린다
      expect(repo.updatedEvaluationId, isNull);
    });

    testWidgets('코멘트는 선택 — 비면 null 로 보낸다 (웹과 같다)', (tester) async {
      final repo = FakeApplicantRepository(
        evaluationSummary: const model.EvaluationSummary(items: []),
      );
      await open(tester, repo);

      await pickAndSave(tester, 5, '저장');

      expect(repo.addedScore, 5);
      // 빈 문자열을 저장하면 "안 썼다" 와 "빈 줄을 썼다" 가 구별되지 않는다
      expect(repo.addedComment, isNull);
    });

    testWidgets('성공하면 그렇게 말한다 (§6)', (tester) async {
      await open(
        tester,
        FakeApplicantRepository(
          evaluationSummary: const model.EvaluationSummary(items: []),
        ),
      );

      await pickAndSave(tester, 3, '저장');
      expect(find.textContaining('평가를 남겼습니다'), findsOneWidget);
    });
  });

  group('이미 쓴 평가가 있으면 — 새로 만들지 않고 고친다', () {
    FakeApplicantRepository repoWithMine() => FakeApplicantRepository(
      evaluationSummary: model.EvaluationSummary(
        items: [
          eval(id: 11, score: 4, evaluatorId: myId, comment: '내가 쓴 것'),
          eval(id: 12, score: 5, evaluatorId: 99),
        ],
      ),
    );

    testWidgets('내 점수·코멘트가 채워진 채로 열린다', (tester) async {
      await open(tester, repoWithMine());

      expect(find.text('내 평가 수정'), findsOneWidget);
      expect(find.text('내가 쓴 것'), findsWidgets);
      expect(find.widgetWithText(FilledButton, '수정'), findsOneWidget);
      expect(find.widgetWithText(FilledButton, '저장'), findsNothing);
    });

    testWidgets('저장하면 POST 가 아니라 PATCH 다 — 평균이 틀어지면 안 된다', (tester) async {
      final repo = repoWithMine();
      await open(tester, repo);

      await pickAndSave(tester, 2, '수정');

      // 내 평가 id 로 고쳐야 한다. 새로 만들면 한 사람이 두 줄이 된다
      expect(repo.updatedEvaluationId, 11);
      expect(repo.updatedScore, 2);
      expect(repo.addedScore, isNull);
    });

    testWidgets('고쳤다는 문구의 어미가 성하다', (tester) async {
      await open(tester, repoWithMine());
      await pickAndSave(tester, 3, '수정');

      // 앞부분만 갈아 끼우다 "수정습니다" 가 나갔다 (2026-09-03 실기기)
      expect(find.text('3점 — 평가를 수정했습니다'), findsOneWidget);
    });

    testWidgets('남의 평가는 내 것으로 열지 않는다', (tester) async {
      final repo = FakeApplicantRepository(
        // 전부 남이 쓴 것
        evaluationSummary: model.EvaluationSummary(
          items: [eval(id: 12, score: 5, evaluatorId: 99)],
        ),
      );
      await open(tester, repo);

      expect(find.text('내 평가'), findsOneWidget);
      expect(find.widgetWithText(FilledButton, '저장'), findsOneWidget);
    });

    testWidgets('로그인 정보가 없으면 늘 새로 쓰기다', (tester) async {
      await open(tester, repoWithMine(), loggedIn: false);

      // 내가 누군지 모르면 어느 것이 내 평가인지도 모른다
      expect(find.widgetWithText(FilledButton, '저장'), findsOneWidget);
    });

    testWidgets('목록에서 내 것에만 "나" 가 붙는다 — 서버가 이름을 안 준다', (tester) async {
      await open(tester, repoWithMine());

      expect(find.text('나'), findsOneWidget);
    });
  });

  group('실패', () {
    testWidgets('배정 안 된 지원자면 서버 문구를 그대로 보여 준다 (403)', (tester) async {
      final repo = FakeApplicantRepository(
        evaluationSummary: const model.EvaluationSummary(items: []),
        writeError: const Forbidden('본인에게 배정된 지원자만 평가할 수 있습니다'),
      );
      await open(tester, repo);

      await pickAndSave(tester, 4, '저장');

      expect(find.text('본인에게 배정된 지원자만 평가할 수 있습니다'), findsOneWidget);
    });

    testWidgets('네트워크가 끊기면 적은 것을 지우지 않는다', (tester) async {
      final repo = FakeApplicantRepository(
        evaluationSummary: const model.EvaluationSummary(items: []),
        writeError: const NetworkError(),
      );
      await open(tester, repo);

      await tester.enterText(find.byType(TextField), '지우면 안 되는 코멘트');
      await tester.pumpAndSettle();
      await pickAndSave(tester, 4, '저장');

      expect(find.textContaining('네트워크를 확인'), findsOneWidget);
      expect(find.text('지우면 안 되는 코멘트'), findsOneWidget);
    });
  });
}
