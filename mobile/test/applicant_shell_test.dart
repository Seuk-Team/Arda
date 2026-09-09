// 지원자 셸 — 탭 다섯 칸 + 각 탭 (2026-09-08).
//
// 여기서 못 박는 것:
//   ① 탭 순서와 이름. 홈이 가운데다(담당자 셸과 같은 규칙).
//   ② **요청 한 번이다.** `GET /applicant/me` 가 지원 현황과 탭 넷의 토큰을
//      한꺼번에 준다 — 탭마다 서버를 다시 부르면 안 된다.
//   ③ **안 연 탭은 자기 링크도 안 부른다.** IndexedStack 이 자식을 다 만들어
//      두는 성질을 그대로 두면 앱을 켜는 순간 네 화면이 각자 요청을 낸다.
//   ④ 링크를 못 받은 탭은 **오류가 아니라 "아직 없다"** 로 그린다.
//   ⑤ 토큰이 만료되면(401) 로그인 화면으로 보낸다.

import 'package:arda/api/api_error.dart';
import 'package:arda/models/applicant_extra.dart';
import 'package:arda/models/applicant_me.dart';
import 'package:arda/models/applicant_portal.dart';
import 'package:arda/routes.dart';
import 'package:arda/screens/applicant_more_screen.dart';
import 'package:arda/screens/applicant_shell.dart';
import 'package:arda/screens/applicant_summary_screen.dart';
import 'package:arda/screens/aptitude_screen.dart';
import 'package:arda/screens/schedule_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'fake_applicant.dart';

const _interviewToken = 'i1';
const _aptitudeToken = 'a1';
const _scheduleToken = 's1';

/// 곽민재 — 백엔드가 준 기본 테스트 계정과 같은 모양으로 둔다
ApplicantMe meWith({
  bool interview = true,
  bool aptitude = true,
  bool schedule = true,
  String scheduleStatus = 'proposed',
  String interviewStatus = 'pending',
  String aptitudeStatus = 'pending',
  int applications = 1,
}) => ApplicantMe(
  email: 'dnwjdwkd145@naver.com',
  name: '곽민재',
  applications: [
    for (var i = 0; i < applications; i++)
      MyApplication(
        id: 18 + i,
        postingTitle: i == 0 ? '백엔드 — 시연' : '프론트엔드 — 시연',
        stageLabel: '서류 검토 중',
        appliedAt: DateTime(2026, 9, 2),
        interviews: interview && i == 0
            ? [TokenLink(token: _interviewToken, status: interviewStatus)]
            : const [],
        aptitudes: aptitude && i == 0
            ? [TokenLink(token: _aptitudeToken, status: aptitudeStatus)]
            : const [],
        schedules: schedule && i == 0
            ? [TokenLink(token: _scheduleToken, status: scheduleStatus)]
            : const [],
      ),
  ],
);

const _interview = InterviewPublic(
  token: _interviewToken,
  status: InterviewStatus.pending,
  applicantName: '곽민재',
  postingTitle: '백엔드 — 시연',
  consentRequired: true,
);

const _aptitude = AptitudePublic(
  token: _aptitudeToken,
  status: AptitudeStatus.pending,
  applicantName: '곽민재',
  postingTitle: '백엔드 — 시연',
  questions: [
    AptitudeQuestion(key: 'q1', text: '새로운 방식을 시도하는 것을 즐긴다.'),
    AptitudeQuestion(key: 'q2', text: '맡은 일은 기한 안에 끝내는 편이다.'),
  ],
  likertLabels: {1: '전혀 아니다', 3: '보통', 5: '매우 그렇다'},
);

final _schedule = SchedulePublic(
  token: _scheduleToken,
  status: ScheduleStatus.proposed,
  applicantName: '곽민재',
  postingTitle: '백엔드 — 시연',
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

FakeApplicantPortalRepository portalWith({ApplicantMe? me}) =>
    FakeApplicantPortalRepository(
      me_: me ?? meWith(),
      interviews: {_interviewToken: _interview},
      aptitudes: {_aptitudeToken: _aptitude},
      schedules: {_scheduleToken: _schedule},
    );

Widget shell(FakeApplicantPortalRepository portal) => MaterialApp(
  home: ApplicantShell(portal: portal),
  routes: {Routes.login: (_) => const Scaffold(body: Text('로그인 화면'))},
);

/// 탭 본문만 따로 띄운다 — 셸을 거치지 않고 화면 하나를 볼 때
Widget only(Widget child) => MaterialApp(home: Scaffold(body: child));

void main() {
  group('탭바', () {
    testWidgets('다섯 칸이 순서대로 — 홈이 가운데', (tester) async {
      await tester.pumpWidget(shell(portalWith()));
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
      await tester.pumpWidget(shell(portalWith()));
      await tester.pumpAndSettle();

      for (final label in ['공고', '지원자', '캘린더']) {
        expect(find.text(label), findsNothing);
      }
    });

    testWidgets('탭을 옮기면 제목이 따라 바뀐다', (tester) async {
      await tester.pumpWidget(shell(portalWith()));
      await tester.pumpAndSettle();
      expect(find.text('내 지원'), findsOneWidget);

      await tester.tap(find.text('인적성'));
      await tester.pumpAndSettle();

      expect(find.text('인적성 검사'), findsWidgets);
    });
  });

  group('요청 한 번', () {
    testWidgets('/applicant/me 만 부르고 탭 화면은 안 만든다', (tester) async {
      final portal = portalWith();
      await tester.pumpWidget(shell(portal));
      await tester.pumpAndSettle();

      // 홈만 열려 있다 — 나머지 탭은 만들어지지도 않아야 한다.
      // skipOffstage: false — IndexedStack 이 들고만 있는 것도 세야 한다
      expect(find.byType(AptitudeScreen, skipOffstage: false), findsNothing);
      expect(find.byType(ScheduleScreen, skipOffstage: false), findsNothing);
      expect(
        find.byType(ApplicantMoreScreen, skipOffstage: false),
        findsNothing,
      );
      // 홈은 셸이 받아 둔 것으로 그린다 — 자기 요청이 없다
      expect(portal.calls, ['me']);
    });

    testWidgets('탭을 열면 그때 자기 링크를 부른다', (tester) async {
      final portal = portalWith();
      await tester.pumpWidget(shell(portal));
      await tester.pumpAndSettle();

      await tester.tap(find.text('인적성'));
      await tester.pumpAndSettle();

      expect(portal.calls, ['me', 'aptitude:$_aptitudeToken']);
    });

    testWidgets('돌아와도 살아 있다 — 다시 안 받는다', (tester) async {
      final portal = portalWith();
      await tester.pumpWidget(shell(portal));
      await tester.pumpAndSettle();

      await tester.tap(find.text('인적성'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('홈'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('인적성'));
      await tester.pumpAndSettle();

      // 인적성은 한 번만 불렸다
      expect(portal.calls.where((c) => c.startsWith('aptitude:')).length, 1);
      expect(find.byType(AptitudeScreen, skipOffstage: false), findsOneWidget);
    });
  });

  group('토큰 만료', () {
    testWidgets('401 이면 로그인 화면으로 보낸다', (tester) async {
      final portal = FakeApplicantPortalRepository(
        meError: const AuthExpired(),
      );
      await tester.pumpWidget(shell(portal));
      await tester.pumpAndSettle();

      expect(find.text('로그인 화면'), findsOneWidget);
    });

    testWidgets('로그아웃하면 토큰을 지우고 로그인으로', (tester) async {
      final portal = portalWith()..token = 'x';
      await tester.pumpWidget(shell(portal));
      await tester.pumpAndSettle();

      await tester.tap(find.text('더보기'));
      await tester.pumpAndSettle();
      await tester.ensureVisible(find.text('로그아웃'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('로그아웃'));
      await tester.pumpAndSettle();

      expect(portal.calls, contains('logout'));
      expect(portal.token, isNull);
      expect(find.text('로그인 화면'), findsOneWidget);
    });
  });

  group('링크가 없을 때', () {
    testWidgets('오류가 아니라 아직 없다고 말한다', (tester) async {
      final portal = portalWith(me: meWith(aptitude: false));
      await tester.pumpWidget(shell(portal));
      await tester.pumpAndSettle();

      await tester.tap(find.text('인적성'));
      await tester.pumpAndSettle();

      // 조사가 낱말을 따라간다 — '검사이' 가 아니라 '검사가'
      expect(find.textContaining('아직 인적성 검사가 없습니다'), findsOneWidget);
      expect(find.textContaining('담당자가 보내면'), findsOneWidget);
      // 없으면 부르지도 않는다
      expect(portal.calls, ['me']);
    });
  });

  group('홈 요약', () {
    testWidgets('이름·공고·단계와 할 일 줄 셋', (tester) async {
      await tester.pumpWidget(shell(portalWith()));
      await tester.pumpAndSettle();

      expect(find.text('곽민재님'), findsOneWidget);
      expect(find.text('dnwjdwkd145@naver.com'), findsOneWidget);
      expect(find.text('백엔드 — 시연'), findsOneWidget);
      expect(find.text('서류 검토 중'), findsOneWidget);
      for (final label in ['인적성 검사', '면접 시간', 'AI 면접']) {
        expect(find.text(label), findsOneWidget);
      }
    });

    testWidgets('할 일이 있는 줄에 무엇을 하게 되는지 적는다', (tester) async {
      await tester.pumpWidget(shell(portalWith()));
      await tester.pumpAndSettle();

      expect(find.text('검사하기'), findsOneWidget);
      expect(find.text('시간 고르기'), findsOneWidget);
      expect(find.text('면접 보기'), findsOneWidget);
    });

    testWidgets('일정이 확정되면 그 줄만 조용해진다', (tester) async {
      final portal = portalWith(me: meWith(scheduleStatus: 'confirmed'));
      await tester.pumpWidget(shell(portal));
      await tester.pumpAndSettle();

      expect(find.text('확정됐습니다'), findsOneWidget);
      expect(find.text('시간 고르기'), findsNothing);
    });

    // 2026-09-09. 서버가 끝난 것도 내려주게 바뀌었다(02-api.md). 그 전에는
    // 면접을 마치면 목록에서 사라져 **"완료"와 "아직 안 잡힘"이 같은 화면**이었다.
    testWidgets('AI 면접을 마쳤으면 완료라고 말한다', (tester) async {
      final portal = portalWith(me: meWith(interviewStatus: 'done'));
      await tester.pumpWidget(shell(portal));
      await tester.pumpAndSettle();

      expect(find.text('완료했습니다'), findsOneWidget);
      // 끝난 면접은 다시 들어갈 수 없다 — 문을 그리지 않는다
      expect(find.text('면접 보기'), findsNothing);
      expect(find.text('이어서 보기'), findsNothing);
      // **사라지지 않는다** — 줄은 그대로 있어야 마쳤다는 것을 알 수 있다
      expect(find.text('AI 면접'), findsOneWidget);
      expect(find.text('아직 없습니다'), findsNothing);
    });

    testWidgets('인적성을 냈으면 제출했다고 말한다', (tester) async {
      final portal = portalWith(me: meWith(aptitudeStatus: 'done'));
      await tester.pumpWidget(shell(portal));
      await tester.pumpAndSettle();

      expect(find.text('제출했습니다'), findsOneWidget);
      expect(find.text('검사하기'), findsNothing);
    });

    testWidgets('없는 것은 눌리지 않는다 — 눌러도 아무 일 없는 카드는 고장 같다', (tester) async {
      final portal = portalWith(me: meWith(aptitude: false));
      await tester.pumpWidget(shell(portal));
      await tester.pumpAndSettle();

      expect(find.text('아직 없습니다'), findsOneWidget);
      expect(find.text('검사하기'), findsNothing);
    });

    testWidgets('지원이 여럿이면 전부 보여 준다 — 한 사람이 여러 공고에 낸다', (tester) async {
      final portal = portalWith(me: meWith(applications: 2));
      await tester.pumpWidget(shell(portal));
      await tester.pumpAndSettle();

      expect(find.byType(ApplicantSummaryScreen), findsOneWidget);
      expect(find.text('백엔드 — 시연'), findsOneWidget);
      expect(find.text('프론트엔드 — 시연'), findsOneWidget);
    });

    testWidgets('지원이 하나도 없으면 그렇다고 말한다', (tester) async {
      final portal = FakeApplicantPortalRepository(
        me_: const ApplicantMe(email: 'a@b.com', name: '아무개'),
      );
      await tester.pumpWidget(shell(portal));
      await tester.pumpAndSettle();

      expect(find.textContaining('아직 지원 내역이 없습니다'), findsOneWidget);
    });
  });

  group('인적성', () {
    testWidgets('다 안 고르면 제출이 잠기고 몇 개 남았는지 적는다', (tester) async {
      await tester.pumpWidget(
        only(AptitudeScreen(token: _aptitudeToken, portal: portalWith())),
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
        only(AptitudeScreen(token: _aptitudeToken, portal: portalWith())),
      );
      await tester.pumpAndSettle();

      expect(find.text('1. 새로운 방식을 시도하는 것을 즐긴다.'), findsOneWidget);
      expect(find.text('전혀 아니다'), findsNWidgets(2)); // 문항마다 한 줄씩
    });

    testWidgets('다 고르면 제출되고 다시 못 고친다', (tester) async {
      final portal = portalWith();
      await tester.pumpWidget(
        only(AptitudeScreen(token: _aptitudeToken, portal: portal)),
      );
      await tester.pumpAndSettle();

      await tester.tap(find.text('3').first);
      await tester.pumpAndSettle();
      await tester.tap(find.text('3').last);
      await tester.pumpAndSettle();
      await tester.tap(find.text('제출하기'));
      await tester.pumpAndSettle();

      expect(portal.calls, contains('submitAptitude:$_aptitudeToken:2'));
      expect(find.textContaining('제출했습니다'), findsOneWidget);
    });
  });

  group('면접 시간 조율', () {
    testWidgets('후보 시간을 보여 준다', (tester) async {
      await tester.pumpWidget(
        only(ScheduleScreen(token: _scheduleToken, portal: portalWith())),
      );
      await tester.pumpAndSettle();

      expect(find.text('2026.09.10'), findsOneWidget);
      expect(find.text('14:00 – 15:00'), findsNWidgets(2));
    });

    testWidgets('고르면 확인부터 묻는다 — 되돌릴 수 없다', (tester) async {
      final portal = portalWith();
      await tester.pumpWidget(
        only(ScheduleScreen(token: _scheduleToken, portal: portal)),
      );
      await tester.pumpAndSettle();

      await tester.tap(find.text('2026.09.10'));
      await tester.pumpAndSettle();
      expect(find.textContaining('누르면 바로 확정됩니다'), findsOneWidget);

      await tester.tap(find.text('취소'));
      await tester.pumpAndSettle();
      expect(portal.calls, isNot(contains('confirmSlot:$_scheduleToken:100')));
    });

    testWidgets('확정하면 확정 시각이 남는다', (tester) async {
      final portal = portalWith();
      await tester.pumpWidget(
        only(ScheduleScreen(token: _scheduleToken, portal: portal)),
      );
      await tester.pumpAndSettle();

      await tester.tap(find.text('2026.09.10'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('확정'));
      await tester.pumpAndSettle();

      expect(portal.calls, contains('confirmSlot:$_scheduleToken:100'));
      expect(find.text('면접 시간이 확정됐습니다'), findsOneWidget);
    });

    testWidgets('아르에게 물으면 질문과 답이 남는다', (tester) async {
      final portal = FakeApplicantPortalRepository(
        schedules: {_scheduleToken: _schedule},
        arAnswer: '면접은 약 30분 진행됩니다.',
      );
      await tester.pumpWidget(
        only(ScheduleScreen(token: _scheduleToken, portal: portal)),
      );
      await tester.pumpAndSettle();

      await tester.enterText(find.byType(TextField), '면접은 얼마나 걸리나요?');
      await tester.pumpAndSettle();
      await tester.ensureVisible(find.text('물어보기'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('물어보기'));
      await tester.pumpAndSettle();

      expect(portal.calls, contains('askAr:$_scheduleToken:면접은 얼마나 걸리나요?'));
      expect(find.text('면접은 약 30분 진행됩니다.'), findsOneWidget);
    });
  });

  group('더보기', () {
    testWidgets('이름·이메일·단계와 로그아웃', (tester) async {
      await tester.pumpWidget(shell(portalWith()));
      await tester.pumpAndSettle();
      await tester.tap(find.text('더보기'));
      await tester.pumpAndSettle();

      expect(find.text('곽민재'), findsOneWidget);
      expect(find.text('서류 검토 중'), findsOneWidget);
      expect(find.text('2026.09.02 접수'), findsOneWidget);
      expect(find.text('로그아웃'), findsOneWidget);
    });
  });
}
