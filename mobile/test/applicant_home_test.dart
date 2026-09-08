// 지원자 홈 — 내 지원 현황 · 내 면접 (2026-09-08).
//
// 여기서 지켜야 할 것 둘:
//   ① 서버가 준 단계 문장을 **그대로** 쓴다. 내부 단계값으로 되돌려 우리 색을
//      칠하면 담당자가 통보하기 전에 화면이 먼저 말하게 된다.
//   ② 못 여는 링크가 멀쩡한 링크까지 가리지 않는다.

import 'package:arda/auth/applicant_store.dart';
import 'package:arda/models/applicant_portal.dart';
import 'package:arda/routes.dart';
import 'package:arda/screens/applicant_home_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'fake_applicant.dart';

const _portalToken = ApplicantToken(
  kind: ApplicantTokenKind.portal,
  token: 'p1',
);
const _interviewToken = ApplicantToken(
  kind: ApplicantTokenKind.interview,
  token: 'i1',
);

final _status = PortalStatus(
  token: 'p1',
  applicantName: '김도현',
  postingTitle: '프론트엔드 개발자 (React)',
  stageLabel: '서류 검토 중',
  submittedAt: DateTime(2026, 9, 2),
);

InterviewPublic interviewOf({
  InterviewStatus status = InterviewStatus.pending,
  bool consentRequired = false,
}) => InterviewPublic(
  token: 'i1',
  status: status,
  applicantName: '김도현',
  postingTitle: '프론트엔드 개발자 (React)',
  consentRequired: consentRequired,
);

Widget host({
  required FakeApplicantStore store,
  required FakeApplicantPortalRepository portal,
}) => MaterialApp(
  home: ApplicantHomeScreen(store: store, portal: portal),
  routes: {
    Routes.login: (_) => const Scaffold(body: Text('로그인 화면')),
    Routes.interview: (_) => const Scaffold(body: Text('면접 화면')),
  },
);

void main() {
  testWidgets('저장된 링크가 없으면 그렇다고 말한다', (tester) async {
    await tester.pumpWidget(
      host(
        store: FakeApplicantStore(),
        portal: FakeApplicantPortalRepository(),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.textContaining('저장된 링크가 없습니다'), findsOneWidget);
  });

  testWidgets('지원 현황은 서버가 준 문장을 그대로 쓴다', (tester) async {
    await tester.pumpWidget(
      host(
        store: FakeApplicantStore([_portalToken]),
        portal: FakeApplicantPortalRepository(statuses: {'p1': _status}),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('프론트엔드 개발자 (React)'), findsOneWidget);
    expect(find.text('서류 검토 중'), findsOneWidget);
    expect(find.text('2026.09.02 접수'), findsOneWidget);
  });

  testWidgets('면접 카드에서 면접 화면으로 간다', (tester) async {
    await tester.pumpWidget(
      host(
        store: FakeApplicantStore([_interviewToken]),
        portal: FakeApplicantPortalRepository(
          interviews: {'i1': interviewOf()},
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('면접 보러 가기'), findsOneWidget);
    await tester.tap(find.text('면접 보러 가기'));
    await tester.pumpAndSettle();

    expect(find.text('면접 화면'), findsOneWidget);
  });

  testWidgets('진행 중이면 이어서 보기다', (tester) async {
    await tester.pumpWidget(
      host(
        store: FakeApplicantStore([_interviewToken]),
        portal: FakeApplicantPortalRepository(
          interviews: {'i1': interviewOf(status: InterviewStatus.inProgress)},
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('이어서 보기'), findsOneWidget);
    expect(find.text('진행 중입니다'), findsOneWidget);
  });

  testWidgets('끝났거나 만료된 면접에는 들어갈 버튼이 없다', (tester) async {
    await tester.pumpWidget(
      host(
        store: FakeApplicantStore([_interviewToken]),
        portal: FakeApplicantPortalRepository(
          interviews: {'i1': interviewOf(status: InterviewStatus.done)},
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('완료했습니다'), findsOneWidget);
    expect(find.text('면접 보러 가기'), findsNothing);
    expect(find.text('이어서 보기'), findsNothing);
  });

  testWidgets('못 연 링크가 멀쩡한 링크를 가리지 않는다', (tester) async {
    // 'p1' 은 넣어 두고 'i1' 은 안 넣어 둔다 — 면접 쪽이 404 로 떨어진다
    await tester.pumpWidget(
      host(
        store: FakeApplicantStore([_portalToken, _interviewToken]),
        portal: FakeApplicantPortalRepository(statuses: {'p1': _status}),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('서류 검토 중'), findsOneWidget);
    expect(find.text('유효하지 않은 링크입니다'), findsOneWidget);
  });

  testWidgets('못 연 링크는 지울 수 있다 — 안 그러면 켤 때마다 쌓인다', (tester) async {
    final store = FakeApplicantStore([_interviewToken]);
    await tester.pumpWidget(
      host(store: store, portal: FakeApplicantPortalRepository()),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.text('지우기'));
    await tester.pumpAndSettle();

    expect(store.tokens, isEmpty);
    expect(find.textContaining('저장된 링크가 없습니다'), findsOneWidget);
  });

  testWidgets('나가면 지원자 토큰만 지우고 로그인으로 간다', (tester) async {
    final store = FakeApplicantStore([_portalToken]);
    await tester.pumpWidget(
      host(
        store: store,
        portal: FakeApplicantPortalRepository(statuses: {'p1': _status}),
      ),
    );
    await tester.pumpAndSettle();

    await tester.ensureVisible(find.text('다른 링크로 들어가기'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('다른 링크로 들어가기'));
    await tester.pumpAndSettle();

    expect(store.tokens, isEmpty);
    expect(find.text('로그인 화면'), findsOneWidget);
  });

  testWidgets('링크가 여럿이면 한꺼번에 물어본다 — 왕복을 줄줄이 쌓지 않는다', (tester) async {
    final portal = FakeApplicantPortalRepository(
      statuses: {'p1': _status},
      interviews: {'i1': interviewOf()},
    );
    await tester.pumpWidget(
      host(
        store: FakeApplicantStore([_portalToken, _interviewToken]),
        portal: portal,
      ),
    );
    await tester.pumpAndSettle();

    expect(portal.calls, containsAll(['status:p1', 'interview:i1']));
    expect(find.text('서류 검토 중'), findsOneWidget);
    expect(find.text('면접 보러 가기'), findsOneWidget);
  });
}
