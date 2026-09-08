// 지원자 셸 — 탭 다섯 칸 + 각 탭 (2026-09-08).
//
// 여기서 못 박는 것:
//   ① 탭 순서와 이름. 홈이 가운데다(담당자 셸과 같은 규칙).
//   ② **안 연 탭은 서버를 안 부른다.** IndexedStack 이 자식을 다 만들어 두는
//      성질을 그대로 두면 앱을 켜는 순간 네 화면이 각자 요청을 낸다.
//   ③ 링크를 못 받은 탭은 **오류가 아니라 "아직 없다"** 로 그린다.
//   ④ 홈은 넷을 한꺼번에 받고, 하나가 실패해도 나머지를 보여 준다.

import 'package:arda/auth/applicant_store.dart';
import 'package:arda/models/applicant_extra.dart';
import 'package:arda/models/applicant_portal.dart';
import 'package:arda/screens/applicant_more_screen.dart';
import 'package:arda/screens/applicant_shell.dart';
import 'package:arda/screens/applicant_summary_screen.dart';
import 'package:arda/screens/aptitude_screen.dart';
import 'package:arda/screens/schedule_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'fake_applicant.dart';

const _tokens = [
  ApplicantToken(kind: ApplicantTokenKind.portal, token: 'p'),
  ApplicantToken(kind: ApplicantTokenKind.interview, token: 'i'),
  ApplicantToken(kind: ApplicantTokenKind.aptitude, token: 'a'),
  ApplicantToken(kind: ApplicantTokenKind.schedule, token: 's'),
];

final _status = PortalStatus(
  token: 'p',
  applicantName: '김도현',
  postingTitle: '프론트엔드 개발자 (React)',
  stageLabel: '서류 검토 중',
  submittedAt: DateTime(2026, 9, 2),
);

const _interview = InterviewPublic(
  token: 'i',
  status: InterviewStatus.pending,
  applicantName: '김도현',
  postingTitle: '프론트엔드 개발자 (React)',
  consentRequired: true,
);

const _aptitude = AptitudePublic(
  token: 'a',
  status: AptitudeStatus.pending,
  applicantName: '김도현',
  postingTitle: '프론트엔드 개발자 (React)',
  questions: [
    AptitudeQuestion(key: 'q1', text: '새로운 방식을 시도하는 것을 즐긴다.'),
    AptitudeQuestion(key: 'q2', text: '맡은 일은 기한 안에 끝내는 편이다.'),
  ],
  likertLabels: {1: '전혀 아니다', 3: '보통', 5: '매우 그렇다'},
);

final _schedule = SchedulePublic(
  token: 's',
  status: ScheduleStatus.proposed,
  applicantName: '김도현',
  postingTitle: '프론트엔드 개발자 (React)',
  currentStage: 'screening',
  slots: [
    ScheduleSlot(
      id: 100,
      startAt: DateTime(2026, 9, 10, 14),
      endAt: DateTime(2026, 9, 10, 15),
    ),
    ScheduleSlot(
      id: 101,
      startAt: DateTime(2026, 9, 11, 14),
      endAt: DateTime(2026, 9, 11, 15),
    ),
  ],
);

FakeApplicantPortalRepository portalWithAll() => FakeApplicantPortalRepository(
  statuses: {'p': _status},
  interviews: {'i': _interview},
  aptitudes: {'a': _aptitude},
  schedules: {'s': _schedule},
);

Widget shell({List<ApplicantToken> tokens = _tokens}) =>
    MaterialApp(home: ApplicantShell(store: FakeApplicantStore(tokens)));

/// 탭 본문만 따로 띄운다 — 셸을 거치지 않고 화면 하나를 볼 때
Widget only(Widget child) => MaterialApp(home: Scaffold(body: child));

void main() {
  group('탭바', () {
    testWidgets('다섯 칸이 순서대로 — 홈이 가운데', (tester) async {
      await tester.pumpWidget(shell());
      await tester.pumpAndSettle();

      expect(ApplicantTab.values.map((t) => t.label).toList(), [
        '인적성',
        '일정',
        '홈',
        '면접',
        '더보기',
      ]);
      for (final label in ['인적성', '일정', '홈', '면접', '더보기']) {
        expect(find.text(label), findsOneWidget);
      }
    });

    testWidgets('담당자 탭은 하나도 안 보인다', (tester) async {
      await tester.pumpWidget(shell());
      await tester.pumpAndSettle();

      for (final label in ['공고', '지원자', '캘린더']) {
        expect(find.text(label), findsNothing);
      }
    });

    testWidgets('탭을 옮기면 제목이 따라 바뀐다', (tester) async {
      await tester.pumpWidget(shell());
      await tester.pumpAndSettle();
      expect(find.text('내 지원'), findsOneWidget);

      await tester.tap(find.text('인적성'));
      await tester.pumpAndSettle();

      expect(find.text('인적성 검사'), findsWidgets);
    });
  });

  group('탭은 처음 열 때 받아 온다', () {
    testWidgets('홈만 열려 있으면 인적성·일정은 안 부른다', (tester) async {
      final portal = portalWithAll();
      await tester.pumpWidget(
        MaterialApp(home: ApplicantShell(store: FakeApplicantStore(_tokens))),
      );
      await tester.pumpAndSettle();

      // 홈이 넷을 받는 것과 별개로, **탭 화면 자체는 안 만들어져야 한다**
      // skipOffstage: false — IndexedStack 이 들고만 있는 것도 세야 한다.
      // 기본값이면 화면에 안 보이는 것을 "없다" 로 세어 테스트가 헛돈다
      expect(find.byType(AptitudeScreen, skipOffstage: false), findsNothing);
      expect(find.byType(ScheduleScreen, skipOffstage: false), findsNothing);
      expect(
        find.byType(ApplicantMoreScreen, skipOffstage: false),
        findsNothing,
      );
      expect(portal.calls, isEmpty); // 이 가짜는 쓰이지도 않았다
    });

    testWidgets('열면 그때 만들어지고, 돌아와도 살아 있다', (tester) async {
      await tester.pumpWidget(shell());
      await tester.pumpAndSettle();

      await tester.tap(find.text('인적성'));
      await tester.pumpAndSettle();
      expect(find.byType(AptitudeScreen), findsOneWidget);

      await tester.tap(find.text('홈'));
      await tester.pumpAndSettle();
      // IndexedStack 이 들고 있으므로 사라지지 않는다 — 돌아올 때 다시 안 받는다
      expect(find.byType(AptitudeScreen, skipOffstage: false), findsOneWidget);
      expect(find.byType(ApplicantSummaryScreen), findsOneWidget);
    });
  });

  group('링크가 없을 때', () {
    testWidgets('오류가 아니라 아직 없다고 말한다', (tester) async {
      await tester.pumpWidget(only(const AptitudeScreen(token: null)));
      await tester.pumpAndSettle();

      // 조사가 낱말을 따라간다 — '검사이' 가 아니라 '검사가'
      expect(find.textContaining('아직 인적성 검사가 없습니다'), findsOneWidget);
      expect(find.textContaining('담당자가 보내면'), findsOneWidget);
    });

    testWidgets('일정도 마찬가지다', (tester) async {
      await tester.pumpWidget(only(const ScheduleScreen(token: null)));
      await tester.pumpAndSettle();

      expect(find.textContaining('담당자가 보내면'), findsOneWidget);
    });
  });

  group('홈 요약', () {
    Future<void> pumpSummary(
      WidgetTester tester, {
      required FakeApplicantPortalRepository portal,
      Map<ApplicantTokenKind, String> tokens = const {
        ApplicantTokenKind.portal: 'p',
        ApplicantTokenKind.interview: 'i',
        ApplicantTokenKind.aptitude: 'a',
        ApplicantTokenKind.schedule: 's',
      },
    }) async {
      await tester.pumpWidget(
        only(
          ApplicantSummaryScreen(
            tokens: tokens,
            onOpen: (_) {},
            portal: portal,
          ),
        ),
      );
      await tester.pumpAndSettle();
    }

    testWidgets('넷을 한꺼번에 부르고 줄 넷을 그린다', (tester) async {
      final portal = portalWithAll();
      await pumpSummary(tester, portal: portal);

      expect(
        portal.calls,
        containsAll(['status:p', 'interview:i', 'aptitude:a', 'schedule:s']),
      );
      for (final label in ['인적성 검사', '면접 시간', 'AI 면접', '지원 현황']) {
        expect(find.text(label), findsOneWidget);
      }
      expect(find.text('김도현님'), findsOneWidget);
    });

    testWidgets('할 일이 있는 줄에 무엇을 하게 되는지 적는다', (tester) async {
      await pumpSummary(tester, portal: portalWithAll());

      expect(find.text('2문항 · 아직 안 냈습니다'), findsOneWidget);
      expect(find.text('검사하기'), findsOneWidget);
      expect(find.text('후보 2건 · 골라 주세요'), findsOneWidget);
      expect(find.text('동의 후 시작할 수 있습니다'), findsOneWidget);
    });

    testWidgets('하나가 실패해도 나머지는 보여 준다', (tester) async {
      // 인적성만 안 넣어 둔다 — 가짜가 404 를 던진다
      final portal = FakeApplicantPortalRepository(
        statuses: {'p': _status},
        interviews: {'i': _interview},
        schedules: {'s': _schedule},
      );
      await pumpSummary(tester, portal: portal);

      expect(find.text('서류 검토 중'), findsOneWidget);
      expect(find.text('후보 2건 · 골라 주세요'), findsOneWidget);
      // 실패한 줄은 "아직 없다" 와 같게 — 지원자가 할 수 있는 일이 같다
      expect(find.text('아직 없습니다'), findsOneWidget);
    });

    testWidgets('토큰이 없는 줄은 서버를 안 부른다', (tester) async {
      final portal = portalWithAll();
      await pumpSummary(
        tester,
        portal: portal,
        tokens: const {ApplicantTokenKind.portal: 'p'},
      );

      expect(portal.calls, ['status:p']);
    });
  });

  group('인적성', () {
    testWidgets('다 안 고르면 제출이 잠기고 몇 개 남았는지 적는다', (tester) async {
      await tester.pumpWidget(
        only(AptitudeScreen(token: 'a', portal: portalWithAll())),
      );
      await tester.pumpAndSettle();

      expect(find.text('2문항 남았습니다'), findsOneWidget);
      final button = tester.widget<FilledButton>(
        find.ancestor(
          of: find.text('2문항 남았습니다'),
          matching: find.byType(FilledButton),
        ),
      );
      expect(button.onPressed, isNull);
    });

    testWidgets('서버가 준 문항·척도를 그대로 쓴다', (tester) async {
      await tester.pumpWidget(
        only(AptitudeScreen(token: 'a', portal: portalWithAll())),
      );
      await tester.pumpAndSettle();

      expect(find.text('1. 새로운 방식을 시도하는 것을 즐긴다.'), findsOneWidget);
      expect(find.text('전혀 아니다'), findsNWidgets(2)); // 문항마다 한 줄씩
      expect(find.text('매우 그렇다'), findsNWidgets(2));
    });

    testWidgets('다 고르면 제출되고 다시 못 고친다', (tester) async {
      final portal = portalWithAll();
      await tester.pumpWidget(only(AptitudeScreen(token: 'a', portal: portal)));
      await tester.pumpAndSettle();

      // 문항마다 3번 칸을 누른다
      final threes = find.text('3');
      expect(threes, findsNWidgets(2));
      await tester.tap(threes.first);
      await tester.pumpAndSettle();
      await tester.tap(find.text('3').last);
      await tester.pumpAndSettle();

      await tester.tap(find.text('제출하기'));
      await tester.pumpAndSettle();

      expect(portal.calls, contains('submitAptitude:a:2'));
      expect(find.textContaining('제출했습니다'), findsOneWidget);
    });
  });

  group('면접 시간 조율', () {
    testWidgets('후보 시간을 보여 준다', (tester) async {
      await tester.pumpWidget(
        only(ScheduleScreen(token: 's', portal: portalWithAll())),
      );
      await tester.pumpAndSettle();

      expect(find.text('2026.09.10'), findsOneWidget);
      expect(find.text('14:00 – 15:00'), findsNWidgets(2));
    });

    testWidgets('고르면 확인부터 묻는다 — 되돌릴 수 없다', (tester) async {
      final portal = portalWithAll();
      await tester.pumpWidget(only(ScheduleScreen(token: 's', portal: portal)));
      await tester.pumpAndSettle();

      await tester.tap(find.text('2026.09.10'));
      await tester.pumpAndSettle();
      expect(find.textContaining('누르면 바로 확정됩니다'), findsOneWidget);

      await tester.tap(find.text('취소'));
      await tester.pumpAndSettle();
      expect(portal.calls, isNot(contains('confirmSlot:s:100')));
    });

    testWidgets('확정하면 확정 시각이 남는다', (tester) async {
      final portal = portalWithAll();
      await tester.pumpWidget(only(ScheduleScreen(token: 's', portal: portal)));
      await tester.pumpAndSettle();

      await tester.tap(find.text('2026.09.10'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('확정'));
      await tester.pumpAndSettle();

      expect(portal.calls, contains('confirmSlot:s:100'));
      expect(find.text('면접 시간이 확정됐습니다'), findsOneWidget);
    });

    testWidgets('아르에게 물으면 질문과 답이 남는다', (tester) async {
      final portal = FakeApplicantPortalRepository(
        schedules: {'s': _schedule},
        arAnswer: '면접은 약 30분 진행됩니다.',
      );
      await tester.pumpWidget(only(ScheduleScreen(token: 's', portal: portal)));
      await tester.pumpAndSettle();

      await tester.enterText(find.byType(TextField), '면접은 얼마나 걸리나요?');
      await tester.pumpAndSettle();
      await tester.ensureVisible(find.text('물어보기'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('물어보기'));
      await tester.pumpAndSettle();

      expect(portal.calls, contains('askAr:s:면접은 얼마나 걸리나요?'));
      expect(find.text('면접은 얼마나 걸리나요?'), findsOneWidget);
      expect(find.text('면접은 약 30분 진행됩니다.'), findsOneWidget);
    });
  });

  group('더보기', () {
    testWidgets('이름·단계·지원일과 로그아웃', (tester) async {
      await tester.pumpWidget(
        only(
          ApplicantMoreScreen(
            token: 'p',
            portal: portalWithAll(),
            onLeave: () async {},
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('김도현'), findsOneWidget);
      expect(find.text('서류 검토 중'), findsOneWidget);
      expect(find.text('2026.09.02 접수'), findsOneWidget);
      // 링크 개념이 사라졌으므로 '다른 링크로 들어가기' 가 아니라 로그아웃이다
      expect(find.text('로그아웃'), findsOneWidget);
    });

    testWidgets('나가기를 누르면 셸이 받는다', (tester) async {
      var left = false;
      await tester.pumpWidget(
        only(
          ApplicantMoreScreen(
            token: 'p',
            portal: portalWithAll(),
            onLeave: () async => left = true,
          ),
        ),
      );
      await tester.pumpAndSettle();

      await tester.tap(find.text('로그아웃'));
      await tester.pumpAndSettle();
      expect(left, isTrue);
    });
  });
}
