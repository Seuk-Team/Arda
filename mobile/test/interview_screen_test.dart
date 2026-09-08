// AI 면접 화면 — 동의 → 준비 → 진행 → 완료 + 카메라 (2026-09-08).
//
// **카메라 수명이 이 화면의 핵심이다.** 요청서(에이전트 도메인 2026-09-07)가
// 요구한 것은 "면접 내내 켜져 있을 것" 이고, 한 번 찍어 올리는 방식과 결과가
// 다른 이유가 거기 있다. 그래서 언제 켜고 언제 놓는지를 여기서 못 박는다:
//
//   동의 전   → 안 켠다 (무슨 앱인지도 모르는 채 권한을 요구하지 않는다)
//   동의 후   → 켠다
//   진행 중   → 계속 켜져 있다 (질문마다 껐다 켜지 않는다)
//   끝나면    → 놓는다
//   앱을 벗어나면 → 놓고, 돌아오면 다시 연다

import 'package:arda/data/camera_service.dart';
import 'package:arda/models/applicant_portal.dart';
import 'package:arda/screens/interview_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'fake_applicant.dart';

InterviewPublic interviewOf({
  InterviewStatus status = InterviewStatus.pending,
  bool consentRequired = true,
  String? question,
  int? seq,
}) => InterviewPublic(
  token: 'tok',
  status: status,
  applicantName: '김도현',
  postingTitle: '프론트엔드 개발자 (React)',
  consentRequired: consentRequired,
  currentQuestion: question,
  questionSeq: seq,
);

({
  Widget widget,
  FakeApplicantPortalRepository portal,
  FakeCameraService camera,
})
host({InterviewPublic? interview, CameraStatus opensAs = CameraStatus.live}) {
  final portal = FakeApplicantPortalRepository(
    interviews: {'tok': interview ?? interviewOf()},
  );
  final camera = FakeCameraService(opensAs: opensAs);
  return (
    widget: MaterialApp(
      home: InterviewScreen(token: 'tok', portal: portal, camera: camera),
    ),
    portal: portal,
    camera: camera,
  );
}

/// 앱을 벗어난다. **한 칸씩 옮겨야 한다** — resumed 에서 paused 로 건너뛰면
/// 프레임워크가 단언에 걸린다
Future<void> _leaveApp(WidgetTester tester) async {
  for (final s in [
    AppLifecycleState.inactive,
    AppLifecycleState.hidden,
    AppLifecycleState.paused,
  ]) {
    tester.binding.handleAppLifecycleStateChanged(s);
  }
  await tester.pumpAndSettle();
}

Future<void> _returnToApp(WidgetTester tester) async {
  for (final s in [
    AppLifecycleState.hidden,
    AppLifecycleState.inactive,
    AppLifecycleState.resumed,
  ]) {
    tester.binding.handleAppLifecycleStateChanged(s);
  }
  await tester.pumpAndSettle();
}

void main() {
  group('동의', () {
    testWidgets('동의 전에는 카메라를 켜지 않는다', (tester) async {
      final h = host();
      await tester.pumpWidget(h.widget);
      await tester.pumpAndSettle();

      expect(find.text('동의하고 계속하기'), findsOneWidget);
      expect(h.camera.starts, 0);
      expect(find.text('촬영 중'), findsNothing);
    });

    testWidgets('안내에 카메라 이야기가 있다 — 실제 동작과 맞아야 한다', (tester) async {
      final h = host();
      await tester.pumpWidget(h.widget);
      await tester.pumpAndSettle();

      expect(find.textContaining('카메라가 켜져 있습니다'), findsOneWidget);
    });

    testWidgets('동의하면 바로 카메라를 켠다', (tester) async {
      final h = host();
      await tester.pumpWidget(h.widget);
      await tester.pumpAndSettle();

      await tester.tap(find.text('동의하고 계속하기'));
      await tester.pumpAndSettle();

      expect(h.portal.calls, contains('consent:tok'));
      expect(h.camera.starts, 1);
      expect(find.text('촬영 중'), findsOneWidget);
    });
  });

  group('준비', () {
    testWidgets('카메라가 켜져야 시작할 수 있다', (tester) async {
      final h = host(
        interview: interviewOf(consentRequired: false),
        opensAs: CameraStatus.denied,
      );
      await tester.pumpWidget(h.widget);
      await tester.pumpAndSettle();

      // 시작하면 첫 질문이 나오고 그때부터는 다시 찍기가 없다 —
      // 꺼진 채로 들어가게 두지 않는다
      final button = tester.widget<FilledButton>(
        find.ancestor(
          of: find.text('면접 시작'),
          matching: find.byType(FilledButton),
        ),
      );
      expect(button.onPressed, isNull);
      expect(find.textContaining('카메라가 켜지면'), findsOneWidget);
    });

    testWidgets('카메라가 켜지면 시작할 수 있다', (tester) async {
      final h = host(interview: interviewOf(consentRequired: false));
      await tester.pumpWidget(h.widget);
      await tester.pumpAndSettle();

      await tester.tap(find.text('면접 시작'));
      await tester.pumpAndSettle();

      expect(h.portal.calls, contains('start:tok'));
      expect(find.text('질문 1'), findsOneWidget);
      expect(find.text('자기소개를 해 주세요.'), findsOneWidget);
    });

    testWidgets('영구 거부면 설정으로 보낸다 — 다시 물어도 창이 안 뜬다', (tester) async {
      final h = host(
        interview: interviewOf(consentRequired: false),
        opensAs: CameraStatus.deniedForever,
      );
      await tester.pumpWidget(h.widget);
      await tester.pumpAndSettle();

      expect(find.text('설정 열기'), findsOneWidget);
      await tester.tap(find.text('설정 열기'));
      await tester.pumpAndSettle();
      expect(h.camera.settingsOpened, 1);
    });

    testWidgets('한 번 거부한 것은 다시 물을 수 있다', (tester) async {
      final h = host(
        interview: interviewOf(consentRequired: false),
        opensAs: CameraStatus.denied,
      );
      await tester.pumpWidget(h.widget);
      await tester.pumpAndSettle();

      expect(find.text('다시 시도'), findsOneWidget);
      expect(find.text('설정 열기'), findsNothing);
    });
  });

  group('진행', () {
    Future<FakeCameraService> startedAt(WidgetTester tester) async {
      final h = host(
        interview: interviewOf(
          status: InterviewStatus.inProgress,
          consentRequired: false,
          question: '자기소개를 해 주세요.',
          seq: 1,
        ),
      );
      await tester.pumpWidget(h.widget);
      await tester.pumpAndSettle();
      return h.camera;
    }

    testWidgets('질문과 미리보기가 같이 있다', (tester) async {
      await startedAt(tester);

      expect(find.text('질문 1'), findsOneWidget);
      expect(find.text('자기소개를 해 주세요.'), findsOneWidget);
      expect(find.text('촬영 중'), findsOneWidget);
    });

    testWidgets('답변이 비면 제출할 수 없다', (tester) async {
      await startedAt(tester);

      final button = tester.widget<FilledButton>(
        find.ancestor(
          of: find.text('답변 제출'),
          matching: find.byType(FilledButton),
        ),
      );
      expect(button.onPressed, isNull);
    });

    testWidgets('답변을 내면 다음 질문으로 넘어간다 — 카메라는 그대로 켜져 있다', (tester) async {
      final h = host(
        interview: interviewOf(
          status: InterviewStatus.inProgress,
          consentRequired: false,
          question: '자기소개를 해 주세요.',
          seq: 1,
        ),
      );
      await tester.pumpWidget(h.widget);
      await tester.pumpAndSettle();
      final startsBefore = h.camera.starts;

      await tester.enterText(find.byType(TextField), '3년차 프론트엔드 개발자입니다.');
      await tester.pumpAndSettle();
      await tester.tap(find.text('답변 제출'));
      await tester.pumpAndSettle();

      expect(h.portal.calls, contains('answer:tok:3년차 프론트엔드 개발자입니다.'));
      expect(find.text('질문 2'), findsOneWidget);
      // **질문마다 껐다 켜지 않는다** — 그러면 다시 찍기가 없다는 전제가 무너진다
      expect(h.camera.stops, 0);
      expect(h.camera.starts, startsBefore);
      expect(find.text('촬영 중'), findsOneWidget);
    });

    testWidgets('제출하면 입력창이 비워진다 — 앞 답이 남으면 다음 답에 섞인다', (tester) async {
      await startedAt(tester);

      await tester.enterText(find.byType(TextField), '답변입니다');
      await tester.pumpAndSettle();
      await tester.tap(find.text('답변 제출'));
      await tester.pumpAndSettle();

      expect(
        tester.widget<TextField>(find.byType(TextField)).controller!.text,
        '',
      );
    });

    testWidgets('진행 보조가 뜬다 — 경고가 아니라 배려다', (tester) async {
      await startedAt(tester);

      await tester.enterText(find.byType(TextField), '짧은 답');
      await tester.pumpAndSettle();
      await tester.tap(find.text('답변 제출'));
      await tester.pumpAndSettle();

      expect(find.text('조금 더 자세히 말씀해 주셔도 좋습니다.'), findsOneWidget);
    });

    testWidgets('면접 중에 카메라가 끊기면 조용히 넘기지 않는다', (tester) async {
      final camera = await startedAt(tester);

      camera.push(CameraStatus.failed);
      await tester.pumpAndSettle();

      expect(find.text('촬영 중'), findsNothing);
      expect(find.text('카메라를 쓸 수 없습니다'), findsOneWidget);
    });
  });

  group('종료', () {
    testWidgets('확인 시트를 거치고, 취소하면 아무 일도 없다', (tester) async {
      final h = host(
        interview: interviewOf(
          status: InterviewStatus.inProgress,
          consentRequired: false,
          question: '질문',
          seq: 1,
        ),
      );
      await tester.pumpWidget(h.widget);
      await tester.pumpAndSettle();

      await tester.ensureVisible(find.text('면접 종료'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('면접 종료'));
      await tester.pumpAndSettle();
      expect(find.textContaining('남은 질문에는 답할 수 없습니다'), findsOneWidget);

      await tester.tap(find.text('취소'));
      await tester.pumpAndSettle();
      expect(h.portal.calls, isNot(contains('finish:tok')));
    });

    testWidgets('종료하면 카메라를 놓는다', (tester) async {
      final h = host(
        interview: interviewOf(
          status: InterviewStatus.inProgress,
          consentRequired: false,
          question: '질문',
          seq: 1,
        ),
      );
      await tester.pumpWidget(h.widget);
      await tester.pumpAndSettle();

      await tester.ensureVisible(find.text('면접 종료'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('면접 종료'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('종료'));
      await tester.pumpAndSettle();

      expect(h.portal.calls, contains('finish:tok'));
      expect(h.camera.stops, greaterThan(0));
      expect(find.textContaining('면접이 완료되었습니다'), findsOneWidget);
      expect(find.text('촬영 중'), findsNothing);
    });
  });

  group('앱을 벗어날 때', () {
    testWidgets('나가면 놓고 돌아오면 다시 연다 — 안 그러면 검은 화면이 남는다', (tester) async {
      final h = host(
        interview: interviewOf(
          status: InterviewStatus.inProgress,
          consentRequired: false,
          question: '질문',
          seq: 1,
        ),
      );
      await tester.pumpWidget(h.widget);
      await tester.pumpAndSettle();
      final startsBefore = h.camera.starts;

      // 프레임워크가 건너뛰는 전이를 막는다 — resumed ↔ inactive ↔ hidden ↔ paused
      await _leaveApp(tester);
      expect(h.camera.stops, 1);

      await _returnToApp(tester);
      expect(h.camera.starts, startsBefore + 1);
      expect(find.text('촬영 중'), findsOneWidget);
    });

    testWidgets('동의 전이면 돌아와도 켜지 않는다', (tester) async {
      final h = host();
      await tester.pumpWidget(h.widget);
      await tester.pumpAndSettle();

      await _leaveApp(tester);
      await _returnToApp(tester);

      expect(h.camera.starts, 0);
    });
  });

  group('만료·오류', () {
    testWidgets('만료된 링크는 그렇다고 말하고 카메라를 안 켠다', (tester) async {
      final h = host(
        interview: interviewOf(
          status: InterviewStatus.expired,
          consentRequired: false,
        ),
      );
      await tester.pumpWidget(h.widget);
      await tester.pumpAndSettle();

      expect(find.textContaining('링크 유효 기간이 지났습니다'), findsOneWidget);
      expect(h.camera.starts, 0);
    });

    testWidgets('못 불러오면 다시 시도할 자리를 준다 — 앱엔 새로고침이 없다', (tester) async {
      // 'tok' 을 안 넣어 뒀으니 가짜가 404 를 던진다
      final portal = FakeApplicantPortalRepository();
      final camera = FakeCameraService();
      await tester.pumpWidget(
        MaterialApp(
          home: InterviewScreen(token: 'tok', portal: portal, camera: camera),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('유효하지 않은 링크입니다'), findsOneWidget);
      expect(find.text('다시 시도'), findsOneWidget);
    });
  });
}
