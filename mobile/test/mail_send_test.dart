// 메일 발송 — 큐 8 3단계의 마지막 (2026-09-03).
//
// **이 앱에서 유일하게 되돌릴 수 없는 동작이다.** SES 로 실제 발송된다.
// 그래서 확인 시트를 반드시 거치는지, 취소하면 정말 안 나가는지가 핵심이다.

import 'package:arda/api/api_error.dart';
import 'package:arda/data/mock_data.dart';
import 'package:arda/screens/mail_compose_screen.dart';
import 'package:arda/theme/tokens.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'fake_repos.dart';

final dohyun = mockApplicants.firstWhere((a) => a.name == '김도현');

Future<void> open(
  WidgetTester tester,
  FakeApplicantRepository repo, {
  MailPreset preset = MailPreset.applied,
}) async {
  await tester.pumpWidget(
    MaterialApp(
      home: MailComposeScreen(
        applicationId: dohyun.id,
        applicantName: dohyun.name,
        preset: preset,
        repository: repo,
      ),
    ),
  );
  await tester.pumpAndSettle();
}

Future<void> tapSend(WidgetTester tester) async {
  await tester.tap(find.widgetWithText(FilledButton, '보내기'));
  await tester.pumpAndSettle();
}

void main() {
  group('프리필', () {
    testWidgets('서버가 채워 준 제목·본문이 들어온다', (tester) async {
      await open(
        tester,
        FakeApplicantRepository(mailPreviewText: ('접수되었습니다', '김도현 님, 안녕하세요.')),
      );

      expect(find.text('접수되었습니다'), findsOneWidget);
      expect(find.text('김도현 님, 안녕하세요.'), findsOneWidget);
    });

    testWidgets('불러오지 못하면 [다시 시도] 다 (§6)', (tester) async {
      await open(tester, FakeApplicantRepository(error: const NetworkError()));

      expect(find.textContaining('네트워크를 확인'), findsOneWidget);
      expect(find.text('다시 시도'), findsOneWidget);
    });

    testWidgets('제목이나 본문을 비우면 [보내기] 가 잠긴다', (tester) async {
      final repo = FakeApplicantRepository();
      await open(tester, repo);

      await tester.enterText(find.byType(TextField).first, '');
      await tester.pumpAndSettle();

      final send = tester.widget<FilledButton>(
        find.widgetWithText(FilledButton, '보내기'),
      );
      expect(send.onPressed, isNull);
      expect(repo.mailsSent, 0);
    });
  });

  group('확인 시트 — 마지막 문', () {
    testWidgets('[보내기] 만으로는 안 나간다', (tester) async {
      final repo = FakeApplicantRepository();
      await open(tester, repo);
      await tapSend(tester);

      // 시트가 떴을 뿐 아직 아무것도 안 보냈다
      expect(repo.mailsSent, 0);
      expect(find.text('이 내용 그대로 지원자에게 발송됩니다. 되돌릴 수 없습니다.'), findsOneWidget);
    });

    testWidgets('누구에게 가는지 시트에 적는다 — 폰은 잘못 눌러 들어오기 쉽다', (tester) async {
      await open(tester, FakeApplicantRepository());
      await tapSend(tester);

      expect(find.text('김도현 님에게 발송'), findsOneWidget);
    });

    testWidgets('취소하면 안 나가고 쓰던 것도 그대로다', (tester) async {
      final repo = FakeApplicantRepository(
        mailPreviewText: ('접수 안내드립니다', '본문'),
      );
      await open(tester, repo);
      await tapSend(tester);

      await tester.tap(find.widgetWithText(OutlinedButton, '취소'));
      await tester.pumpAndSettle();

      expect(repo.mailsSent, 0);
      expect(find.text('접수 안내드립니다'), findsOneWidget);
    });

    testWidgets('[발송] 을 눌러야 나간다', (tester) async {
      final repo = FakeApplicantRepository(mailPreviewText: ('접수 안내', '본문입니다'));
      await open(tester, repo);
      await tapSend(tester);

      await tester.tap(find.widgetWithText(FilledButton, '발송'));
      await tester.pumpAndSettle();

      expect(repo.mailsSent, 1);
      expect(repo.sentSubject, '접수 안내');
      expect(repo.sentBody, '본문입니다');
    });

    testWidgets('고쳐 쓴 내용이 그대로 간다 — 프리필을 덮어쓰지 않는다', (tester) async {
      final repo = FakeApplicantRepository();
      await open(tester, repo);

      await tester.enterText(find.byType(TextField).last, '직접 고친 본문');
      await tester.pumpAndSettle();
      await tapSend(tester);
      await tester.tap(find.widgetWithText(FilledButton, '발송'));
      await tester.pumpAndSettle();

      expect(repo.sentBody, '직접 고친 본문');
    });
  });

  group('불합격 — 되돌릴 수 없는 쪽', () {
    testWidgets('보내기 버튼이 적갈이다 (§1 색은 판단에만)', (tester) async {
      await open(
        tester,
        FakeApplicantRepository(),
        preset: MailPreset.rejected,
      );

      final send = tester.widget<FilledButton>(
        find.widgetWithText(FilledButton, '보내기'),
      );
      final color = send.style!.backgroundColor!.resolve({});
      expect(color, AppColors.danger);
    });

    testWidgets('접수 확인은 무채다 — 넷이 다 빨가면 경고가 안 된다', (tester) async {
      await open(tester, FakeApplicantRepository());

      final send = tester.widget<FilledButton>(
        find.widgetWithText(FilledButton, '보내기'),
      );
      expect(send.style?.backgroundColor?.resolve({}), isNot(AppColors.danger));
    });
  });

  group('실패', () {
    testWidgets('화면을 닫지 않는다 — 고쳐 쓴 본문이 사라지면 안 된다', (tester) async {
      final repo = FakeApplicantRepository(
        mailPreviewText: ('접수 안내드립니다', '지우면 안 되는 본문'),
        writeError: const NetworkError(),
      );
      await open(tester, repo);
      await tapSend(tester);
      await tester.tap(find.widgetWithText(FilledButton, '발송'));
      await tester.pumpAndSettle();

      expect(find.textContaining('네트워크를 확인'), findsOneWidget);
      expect(find.byType(MailComposeScreen), findsOneWidget);
      expect(find.text('지우면 안 되는 본문'), findsOneWidget);
    });
  });
}
