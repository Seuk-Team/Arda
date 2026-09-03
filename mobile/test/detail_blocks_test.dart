// 지원자 상세의 새 블록들 — 아르의 요약 · 시스템(메일) · 메모.
// 05-design §1 이 2026-09-01 에 확정한 "앰버는 확정 대기에만" 을 지키는지가 핵심이다.

import 'package:arda/data/mock_data.dart';
import 'package:arda/models/ai_summary.dart';
import 'package:arda/models/applicant.dart';
import 'package:arda/models/email_log.dart';
import 'package:arda/models/stage.dart';
import 'package:arda/screens/applicant_detail_screen.dart';
import 'package:arda/screens/mail_compose_screen.dart';
import 'package:arda/theme/tokens.dart';
import 'package:arda/widgets/detail_blocks.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'fake_repos.dart';

/// 김도현 — AI 요약·메일 이력·메모를 모두 가진 유일한 목데이터
final dohyun = mockApplicants.firstWhere((a) => a.name == '김도현');

/// 상세는 서버에서 받아 온다(큐 8) — 넘긴 사람 하나만 아는 가짜를 물린다.
/// 목데이터에 없는 사람(요약 없음·규격밖 등)도 그대로 그려진다.
Widget _host(Applicant a) => MaterialApp(
  home: ApplicantDetailScreen(
    applicant: a,
    postingTitle: mockPostings.first.title,
    repository: FakeApplicantRepository(applicants: [a]),
  ),
);

/// 상세가 서버에서 오므로 한 번 정착시켜야 그려진다 (큐 8)
Future<void> open(WidgetTester tester, Applicant a) async {
  await tester.pumpWidget(_host(a));
  await tester.pumpAndSettle();
}

void main() {
  group('아르의 요약', () {
    testWidgets('앰버가 아니라 정보 블록이다 (§1 2026-09-01 확정)', (tester) async {
      await open(tester, dohyun);

      final box = tester.widget<Container>(
        find
            .ancestor(of: find.text('아르의 요약'), matching: find.byType(Container))
            .last,
      );
      final deco = box.decoration! as BoxDecoration;

      // 문서가 못 박은 값 그대로
      expect(deco.color, AppColors.bgSunken);
      expect((deco.border! as Border).top.color, AppColors.borderSoft);
      expect((deco.border! as Border).top.style, BorderStyle.solid);

      // 앰버는 어디에도 쓰지 않는다 — 액션을 요구하지 않는 블록이다
      expect(deco.color, isNot(AppColors.aiSoft));
      final title = tester.widget<Text>(find.text('아르의 요약'));
      expect(title.style!.color, isNot(AppColors.ai));
      expect(title.style!.color, AppColors.text);
    });

    testWidgets('지원 정보보다 위에 온다 (§0.5 "상세 패널 상단")', (tester) async {
      await open(tester, dohyun);

      expect(
        tester.getRect(find.text('아르의 요약')).top,
        lessThan(tester.getRect(find.text('학력')).top),
      );
    });

    testWidgets('생성 시각과 모델을 남긴다 — 발표 근거', (tester) async {
      await open(tester, dohyun);
      expect(find.textContaining('생성 · claude-haiku'), findsOneWidget);
    });

    testWidgets('요지·강점·확인 필요로 나눠 그린다 — 웹과 같은 라벨', (tester) async {
      await open(tester, dohyun);

      expect(find.textContaining('초당 처리량을 3배로'), findsOneWidget);
      expect(find.text('강점'), findsOneWidget);
      expect(find.text('확인 필요'), findsOneWidget);
      expect(find.text('팀 협업 사례가 한 건뿐'), findsOneWidget);

      // 05-design §0.5: 면접 확인 포인트는 이 자리에 그리지 않는다 (6905c37)
      expect(find.text('면접 확인 포인트'), findsNothing);
    });

    testWidgets('저장된 값은 JSON 이다 — 통짜 문단이 그대로 보이면 안 된다', (tester) async {
      for (final a in mockApplicants) {
        final parsed = AiSummary.parse(a.aiSummary!);
        expect(parsed.isRawText, isFalse, reason: '${a.name} 요약이 JSON 이 아님');
        expect(parsed.gist, isNotNull, reason: '${a.name} 요지 없음');

        // 에이전트 스키마 상한 (35ba4b5) — gist 160자 · 리스트 항목 40자.
        // 목데이터가 규격을 넘으면 실제 응답도 그럴 것처럼 보인다
        expect(parsed.gist!.length, lessThanOrEqualTo(160), reason: a.name);
        expect(parsed.fit.length, lessThanOrEqualTo(2));
        expect(parsed.concerns.length, lessThanOrEqualTo(2));
        for (final line in [...parsed.fit, ...parsed.concerns]) {
          expect(line.length, lessThanOrEqualTo(40), reason: '"$line" 40자 초과');
        }
      }
    });

    testWidgets('JSON 이 아니면 원문을 그대로 보여 준다 — 웹과 같은 처리', (tester) async {
      final odd = Applicant(
        id: 997,
        jobPostingId: 1,
        name: '규격밖',
        email: 'odd@example.com',
        aiSummary: '모델이 그냥 문장으로 답한 경우입니다.',
        aiSummaryAt: DateTime(2026, 9, 1),
        currentStage: Stage.applied,
        createdAt: DateTime(2026, 9, 1),
      );
      await open(tester, odd);

      expect(find.text('모델이 그냥 문장으로 답한 경우입니다.'), findsOneWidget);
      expect(find.text('강점'), findsNothing);
    });

    testWidgets('자료가 부족하면 그 사실을 적는다', (tester) async {
      final thin = Applicant(
        id: 996,
        jobPostingId: 1,
        name: '자료부족',
        email: 'thin@example.com',
        aiSummary: '{"insufficient": true}',
        aiSummaryAt: DateTime(2026, 9, 1),
        currentStage: Stage.applied,
        createdAt: DateTime(2026, 9, 1),
      );
      await open(tester, thin);

      expect(find.text('자기소개 등 자료가 부족해 요약을 만들지 못했습니다.'), findsOneWidget);
    });

    testWidgets('여섯 명 모두 요약을 가진다 — 접수 시 1회 생성 (§0.5)', (tester) async {
      for (final a in mockApplicants) {
        expect(a.aiSummary, isNotNull, reason: '${a.name} 요약 없음');
        expect(a.aiSummaryAt, isNotNull, reason: '${a.name} 생성 시각 없음');
        expect(a.aiSummaryModel, isNotNull, reason: '${a.name} 모델 없음');
      }
    });

    testWidgets('요약이 없으면(NULL = 미생성) 자리를 만들지 않는다', (tester) async {
      // 목데이터는 전원 요약을 갖지만 컬럼은 NULL 가능하다(ERD) — 생성 실패나
      // 큐 8 이전 데이터가 그렇다. 그 경우를 직접 만들어 확인한다
      final noSummary = Applicant(
        id: 998,
        jobPostingId: 1,
        name: '요약없음',
        email: 'nosummary@example.com',
        currentStage: Stage.applied,
        createdAt: DateTime(2026, 9, 1),
      );
      await open(tester, noSummary);

      expect(find.text('아르의 요약'), findsNothing);
      expect(find.byType(ArSummaryBlock), findsNothing);
    });
  });

  group('시스템 — 메일 이력', () {
    testWidgets('실패만 적갈, 발송은 잎초록 (§1 색은 판단에만)', (tester) async {
      await open(tester, dohyun);

      final failed = tester.widget<Text>(find.text(EmailStatus.failed.label));
      expect(failed.style!.color, AppColors.danger);

      final sent = tester.widget<Text>(find.text(EmailStatus.sent.label));
      expect(sent.style!.color, AppColors.leaf);
    });

    testWidgets('제목과 날짜가 함께 나온다', (tester) async {
      await open(tester, dohyun);

      expect(find.text('지원 접수 자동 안내'), findsOneWidget);
      expect(find.text('2026.09.01'), findsOneWidget);
    });
  });

  group('메모', () {
    testWidgets('"작성자 · 날짜 + 본문" 시간순 — 최신이 위', (tester) async {
      await open(tester, dohyun);

      final notes = mockNotes[dohyun.id]!;
      expect(
        find.text('${notes.first.authorName} · 2026.08.27'),
        findsOneWidget,
      );
      expect(find.text(notes.first.body), findsOneWidget);

      // ERD 인덱스가 created_at DESC — 최신이 먼저
      expect(
        tester.getRect(find.text(notes.first.body)).top,
        lessThan(tester.getRect(find.text(notes.last.body)).top),
      );
    });

    testWidgets('살아 있는 입력칸이다 — 큐 8(2026-09-02)에서 잠금을 풀었다', (tester) async {
      await open(tester, dohyun);

      expect(find.widgetWithText(TextField, '메모 남기기'), findsOneWidget);

      // 빈 칸이면 보내기가 잠겨 있다
      final send = tester.widget<FilledButton>(
        find.widgetWithText(FilledButton, '남기기'),
      );
      expect(send.onPressed, isNull);
    });
  });

  group('메일', () {
    testWidgets('초안의 네 개가 다 있다', (tester) async {
      await open(tester, dohyun);

      for (final label in ['면접 안내', '접수 확인', '최종 합격', '불합격']) {
        expect(find.widgetWithText(MailBlock, label), findsOneWidget);
      }
    });

    testWidgets('버튼 폭은 글자에 맞는다 — 한 줄에 하나씩 깔리지 않는다', (tester) async {
      await open(tester, dohyun);

      final invite = tester.getRect(find.text('면접 안내'));
      final confirm = tester.getRect(find.text('접수 확인'));

      // 같은 줄에 나란히
      expect(invite.top, confirm.top);
      expect(invite.right, lessThan(confirm.left));
    });

    testWidgets('불합격만 적갈 — 되돌릴 수 없는 메일이다 (§1)', (tester) async {
      await open(tester, dohyun);

      final reject = tester.widget<Text>(
        find.descendant(of: find.byType(MailBlock), matching: find.text('불합격')),
      );
      expect(reject.style!.color, AppColors.danger);

      final invite = tester.widget<Text>(find.text('면접 안내'));
      expect(invite.style!.color, AppColors.text);
    });

    testWidgets('누르면 메일 쓰기 화면으로 간다 — 여기서 바로 안 보낸다', (tester) async {
      await open(tester, dohyun);

      final button = find.widgetWithText(MailBlock, '면접 안내');
      await tester.ensureVisible(button);
      await tester.pumpAndSettle();
      await tester.tap(button);
      await tester.pumpAndSettle();

      // 프리셋 → 편집 → 확인 순이다(웹과 같다). 버튼 한 번에 나가면 안 된다
      expect(find.byType(MailComposeScreen), findsOneWidget);
      expect(find.widgetWithText(FilledButton, '보내기'), findsOneWidget);
      // 큐 8 전의 "아직 발송되지 않음" 은 사라졌다 (2026-09-03)
      expect(find.textContaining('아직 발송되지 않음'), findsNothing);
    });
  });

  group('지원 정보', () {
    testWidgets('연락처·이메일·기술이 들어왔다', (tester) async {
      await open(tester, dohyun);

      expect(find.text('연락처'), findsOneWidget);
      expect(find.text(dohyun.phone!), findsOneWidget);
      expect(find.text(dohyun.email), findsOneWidget);
      expect(find.text(dohyun.skills.join(' · ')), findsOneWidget);
    });

    testWidgets('평점은 한 줄로 — 초안 "4.3 / 5.0 · 3명"', (tester) async {
      await open(tester, dohyun);

      expect(find.text('평점'), findsOneWidget);
      expect(find.text('4.3 / 5.0 · 3명'), findsOneWidget);
    });

    testWidgets('평가가 없으면 평점 줄이 없다 — "0.0" 은 나쁜 점수로 읽힌다', (tester) async {
      final unrated = mockApplicants.firstWhere(
        (a) => !mockEvaluations.containsKey(a.id),
      );
      await open(tester, unrated);

      expect(find.text('평점'), findsNothing);
    });

    testWidgets('없는 값은 줄을 만들지 않는다', (tester) async {
      final bare = Applicant(
        id: 999,
        jobPostingId: 1,
        name: '연락처없음',
        email: 'none@example.com',
        currentStage: Stage.applied,
        createdAt: DateTime(2026, 9, 1),
      );
      await tester.pumpWidget(
        MaterialApp(
          home: ApplicantDetailScreen(
            applicant: bare,
            postingTitle: '테스트',
            repository: FakeApplicantRepository(applicants: [bare]),
          ),
        ),
      );

      expect(find.text('연락처'), findsNothing);
      expect(find.text('기술'), findsNothing);
    });
  });
}
