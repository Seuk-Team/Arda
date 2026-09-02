// 단계 변경 — 큐 8 2단계. **W4 완료 기준**이라 여기가 발표의 핵심 동작이다.
//
// 시트는 그대로 두고(폰 오탭 방지) 안 돌던 것을 돌게 한 부분을 본다:
// 실제 호출 · 불합격 사유 필수 · 보내는 중 잠금 · 실패 문구.

import 'package:arda/api/api_error.dart';
import 'package:arda/data/applicant_repository.dart';
import 'package:arda/data/mock_data.dart';
import 'package:arda/models/stage.dart';
import 'package:arda/screens/applicant_detail_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'fake_repos.dart';

/// 김도현 — 면접 단계라 갈 곳이 여럿이다
final dohyun = mockApplicants.firstWhere((a) => a.name == '김도현');

/// 부른 내용을 기록하는 가짜.
class _RecordingRepository extends FakeApplicantRepository {
  _RecordingRepository({super.applicants, this.failWith, this.delay2});

  final ApiError? failWith;
  final Duration? delay2;

  Stage? calledStage;
  String? calledReason;
  int calls = 0;

  @override
  Future<void> changeStage(int id, Stage to, {String? reason}) async {
    calls++;
    calledStage = to;
    calledReason = reason;
    if (delay2 != null) await Future<void>.delayed(delay2!);
    if (failWith != null) throw failWith!;
  }
}

Future<void> open(WidgetTester tester, ApplicantRepository repo) async {
  await tester.pumpWidget(
    MaterialApp(
      home: ApplicantDetailScreen(
        applicant: dohyun,
        postingTitle: mockPostings.first.title,
        repository: repo,
      ),
    ),
  );
  await tester.pumpAndSettle();
}

/// 하단 [단계 변경] → 시트에서 단계 고르기 → [확정]
Future<void> pickStage(WidgetTester tester, String label) async {
  await tester.tap(find.widgetWithText(FilledButton, '단계 변경'));
  await tester.pumpAndSettle();

  await tester.tap(find.text(label).last);
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('고른 단계를 서버로 보낸다', (tester) async {
    final repo = _RecordingRepository(applicants: [dohyun]);
    await open(tester, repo);

    await pickStage(tester, '최종 합격');
    await tester.tap(find.text('최종 합격으로 변경'));
    await tester.pumpAndSettle();

    expect(repo.calledStage, Stage.accepted);
    // 불합격이 아니면 사유를 보내지 않는다
    expect(repo.calledReason, isNull);
  });

  testWidgets('성공하면 옮겼다고 말한다 — 조용히 지나가지 않는다 (§6)', (tester) async {
    await open(tester, _RecordingRepository(applicants: [dohyun]));

    await pickStage(tester, '최종 합격');
    await tester.tap(find.text('최종 합격으로 변경'));
    await tester.pumpAndSettle();

    expect(find.textContaining('옮겼습니다'), findsOneWidget);
    // 예전의 "아직 저장되지 않음" 은 사라져야 한다
    expect(find.textContaining('아직 저장되지 않음'), findsNothing);
  });

  group('불합격 — 사유가 필수다 (D8)', () {
    testWidgets('사유가 비면 확정이 잠겨 있다', (tester) async {
      final repo = _RecordingRepository(applicants: [dohyun]);
      await open(tester, repo);

      await pickStage(tester, '불합격');

      final confirm = tester.widget<FilledButton>(
        find.widgetWithText(FilledButton, '불합격으로 변경'),
      );
      expect(confirm.onPressed, isNull);
      expect(repo.calls, 0);
    });

    testWidgets('사유를 적으면 그 값이 함께 간다', (tester) async {
      final repo = _RecordingRepository(applicants: [dohyun]);
      await open(tester, repo);

      await pickStage(tester, '불합격');
      await tester.enterText(find.byType(TextField), '요건과 맞지 않음');
      await tester.pumpAndSettle();

      await tester.tap(find.text('불합격으로 변경'));
      await tester.pumpAndSettle();

      expect(repo.calledStage, Stage.rejected);
      expect(repo.calledReason, '요건과 맞지 않음');
    });
  });

  testWidgets('보내는 동안 버튼이 잠긴다 — 두 번 보내면 이력이 두 줄 남는다', (tester) async {
    final repo = _RecordingRepository(
      applicants: [dohyun],
      delay2: const Duration(milliseconds: 300),
    );
    await open(tester, repo);

    await pickStage(tester, '최종 합격');
    await tester.tap(find.text('최종 합격으로 변경'));
    await tester.pump(); // 보내기 시작

    // 버튼 자리에 스피너가 돈다 — 글자를 지우지 않고 그 자리에 둔다
    expect(find.byType(CircularProgressIndicator), findsWidgets);
    // 글자가 없으니 다시 누를 대상도 없다
    expect(find.widgetWithText(FilledButton, '단계 변경'), findsNothing);

    await tester.pumpAndSettle();
    expect(repo.calls, 1);
  });

  testWidgets('실패하면 서버가 준 이유를 그대로 보여 준다', (tester) async {
    final repo = _RecordingRepository(
      applicants: [dohyun],
      // 갈 수 없는 단계를 서버가 막는 경우
      failWith: const ServerError(409, '이 단계로는 옮길 수 없습니다.'),
    );
    await open(tester, repo);

    await pickStage(tester, '최종 합격');
    await tester.tap(find.text('최종 합격으로 변경'));
    await tester.pumpAndSettle();

    expect(find.text('이 단계로는 옮길 수 없습니다.'), findsOneWidget);
  });

  testWidgets('네트워크가 끊기면 다른 문구다', (tester) async {
    final repo = _RecordingRepository(
      applicants: [dohyun],
      failWith: const NetworkError(),
    );
    await open(tester, repo);

    await pickStage(tester, '최종 합격');
    await tester.tap(find.text('최종 합격으로 변경'));
    await tester.pumpAndSettle();

    expect(find.textContaining('네트워크를 확인'), findsOneWidget);
  });
}
