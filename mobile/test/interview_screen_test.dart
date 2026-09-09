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

import 'dart:async';
import 'dart:typed_data';

import 'package:arda/data/camera_service.dart';
import 'package:arda/data/interview_socket.dart';
import 'package:arda/data/mic_service.dart';
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
  FakeMicService mic,
  FakeInterviewSocket socket,
  List<FakeInterviewSocket> sockets,
})
host({
  InterviewPublic? interview,
  CameraStatus opensAs = CameraStatus.live,
  MicUnavailable? micFails,
  Completer<void>? cameraOpening,
}) {
  final portal = FakeApplicantPortalRepository(
    interviews: {'tok': interview ?? interviewOf()},
  );
  final camera = FakeCameraService(opensAs: opensAs, opening: cameraOpening);
  final mic = FakeMicService(failsWith: micFails);
  final sockets = <FakeInterviewSocket>[];
  FakeInterviewSocket open() {
    final s = FakeInterviewSocket();
    sockets.add(s);
    return s;
  }

  final socket = open();
  var opened = 0;
  return (
    widget: MaterialApp(
      home: InterviewScreen(
        token: 'tok',
        portal: portal,
        camera: camera,
        mic: mic,
        // 첫 번째는 미리 만들어 둔 것을, **두 번째부터는 새 것을** 준다 —
        // 다시 붙는 것을 시험이 볼 수 있게
        openSocket: (_) {
          opened += 1;
          return opened == 1 ? socket : open();
        },
      ),
    ),
    portal: portal,
    camera: camera,
    mic: mic,
    socket: socket,
    sockets: sockets,
  );
}

/// 화면을 폰 폭에 세로로 길게 잡는다.
///
/// 기본 테스트 화면(800x600)은 가로로 넓고 세로가 짧아, 카메라 미리보기가
/// 3:4 로 커진 뒤로는 그 아래 버튼이 리스트에 아예 안 만들어진다(ListView 는
/// 화면 밖을 늦게 만든다). **폭은 폰 그대로 두고 높이만 넉넉히** 잡아 한 화면에
/// 다 놓는다 — 여기서 보려는 것은 배치가 아니라 동작이다.
void usePhone(WidgetTester tester) {
  tester.view.physicalSize = const Size(390, 1400);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
}

/// 실시간이 붙기까지 기다린다.
///
/// 마이크를 열고 소켓을 잇는 데 비동기 단계가 몇 겹이라, `pumpAndSettle` 한 번은
/// **그리다 만 자리에서 멈춘다** — 화면이 다시 그려질 일이 없으면 그 시점에
/// 돌아와 버리고, 남은 단계는 다음 pump 때까지 안 돈다. 몇 번 더 돌려 준다.
Future<void> settleLive(WidgetTester tester) async {
  for (var i = 0; i < 2; i++) {
    await tester.pumpAndSettle();
  }
}

/// 다시 붙기를 기다린다.
///
/// 정리(구독 취소·소켓 닫기)가 몇 겹이고 그 뒤에 **초 단위로 기다렸다가** 다시
/// 붙는다. 시계를 몇 번 밀어 주지 않으면 그 자리를 못 지나간다.
Future<void> settleReconnect(WidgetTester tester) async {
  for (var i = 0; i < 5; i++) {
    await tester.pump(const Duration(seconds: 2));
  }
  await settleLive(tester);
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
      usePhone(tester);
      final h = host();
      await tester.pumpWidget(h.widget);
      await tester.pumpAndSettle();

      expect(find.text('동의하고 계속하기'), findsOneWidget);
      expect(h.camera.starts, 0);
      expect(find.text('촬영 중'), findsNothing);
    });

    testWidgets('안내에 카메라 이야기가 있다 — 실제 동작과 맞아야 한다', (tester) async {
      usePhone(tester);
      final h = host();
      await tester.pumpWidget(h.widget);
      await tester.pumpAndSettle();

      expect(find.textContaining('카메라가 켜져 있습니다'), findsOneWidget);
    });

    testWidgets('동의하면 바로 카메라를 켠다', (tester) async {
      usePhone(tester);
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
      usePhone(tester);
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
      usePhone(tester);
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
      usePhone(tester);
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
      usePhone(tester);
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

  // 말로 답하는 면접 (2026-09-09). **제출 버튼이 없다** — 지원자가 말을 멈추면
  // 서버가 알아채 다음 질문을 보낸다. 그래서 여기서 못 박는 것은 두 가지다:
  //   ① 소리와 얼굴이 실제로 소켓으로 나가는가
  //   ② 서버가 보낸 대목(듣는 중·정리 중·끝)이 화면에 그대로 뜨는가
  group('진행 — 말로 답한다', () {
    Future<
      ({
        FakeCameraService camera,
        FakeMicService mic,
        FakeInterviewSocket socket,
        List<FakeInterviewSocket> sockets,
        FakeApplicantPortalRepository portal,
      })
    >
    startedAt(WidgetTester tester) async {
      final h = host(
        interview: interviewOf(
          status: InterviewStatus.inProgress,
          consentRequired: false,
          question: '자기소개를 해 주세요.',
          seq: 1,
        ),
      );
      await tester.pumpWidget(h.widget);
      await settleLive(tester);
      // 진짜 서버는 붙자마자 지금 질문을 보내 준다. 그것까지가 "붙었다" 다
      h.socket.emit(const InterviewQuestion(text: '자기소개를 해 주세요.', seq: 1));
      await tester.pumpAndSettle();
      return (
        camera: h.camera,
        mic: h.mic,
        socket: h.socket,
        sockets: h.sockets,
        portal: h.portal,
      );
    }

    testWidgets('질문과 미리보기가 같이 있다', (tester) async {
      usePhone(tester);
      await startedAt(tester);

      expect(find.text('질문 1'), findsOneWidget);
      expect(find.text('자기소개를 해 주세요.'), findsOneWidget);
      expect(find.text('촬영 중'), findsOneWidget);
    });

    testWidgets('제출 버튼이 없다 — 말을 멈추면 서버가 알아서 넘긴다', (tester) async {
      usePhone(tester);
      await startedAt(tester);

      expect(find.text('답변 제출'), findsNothing);
      expect(find.byType(TextField), findsNothing);
      expect(find.text('말씀해 주세요'), findsOneWidget);
    });

    testWidgets('마이크 소리가 소켓으로 나간다 — 이게 안 되면 질문이 안 넘어간다', (tester) async {
      usePhone(tester);
      final h = await startedAt(tester);

      h.mic.sink.add(Uint8List(micChunkBytes));
      await tester.pumpAndSettle();

      expect(h.socket.audio, hasLength(1));
      expect(h.socket.audio.first, hasLength(micChunkBytes));
      expect(h.mic.starts, 1);
    });

    // 2026-09-09. 말은 하는데 질문이 안 넘어갈 때, 화면만 보고는 마이크가
    // 안 잡히는 것인지 서버가 안 받는 것인지 알 수 없었다.
    testWidgets('소리가 하나도 안 들어오면 그렇다고 말한다', (tester) async {
      usePhone(tester);
      await startedAt(tester);

      expect(
        find.textContaining('마이크에서 소리가 들어오지 않습니다'),
        findsOneWidget,
      );
    });

    testWidgets('소리가 들어오면 크기 막대로 바뀐다', (tester) async {
      usePhone(tester);
      final h = await startedAt(tester);

      h.mic.sink.add(Uint8List(micChunkBytes));
      await tester.pumpAndSettle();

      expect(find.textContaining('마이크에서 소리가 들어오지 않습니다'), findsNothing);
      expect(find.byType(LinearProgressIndicator), findsOneWidget);
    });

    testWidgets('얼굴 프레임도 같은 소켓으로 나간다', (tester) async {
      usePhone(tester);
      final h = await startedAt(tester);

      h.camera.frameSink.add(Uint8List.fromList([1, 2, 3]));
      await tester.pumpAndSettle();

      expect(h.socket.video, hasLength(1));
    });

    testWidgets('서버가 알려 주는 대목이 그대로 뜬다 — 공백에 지원자가 불안해진다', (tester) async {
      usePhone(tester);
      final h = await startedAt(tester);

      h.socket.emit(const InterviewListening());
      await tester.pumpAndSettle();
      expect(find.text('듣고 있습니다'), findsOneWidget);

      h.socket.emit(const InterviewProcessing());
      await tester.pumpAndSettle();
      expect(find.text('정리하는 중'), findsOneWidget);
    });

    testWidgets('다음 질문이 오면 갈아 끼운다 — 카메라는 그대로 켜져 있다', (tester) async {
      usePhone(tester);
      final h = await startedAt(tester);
      final startsBefore = h.camera.starts;

      h.socket.emit(const InterviewQuestion(text: '가장 어려웠던 일은?', seq: 2));
      await tester.pumpAndSettle();

      expect(find.text('질문 2'), findsOneWidget);
      expect(find.text('가장 어려웠던 일은?'), findsOneWidget);
      // **질문마다 껐다 켜지 않는다** — 그러면 다시 찍기가 없다는 전제가 무너진다
      expect(h.camera.stops, 0);
      expect(h.camera.starts, startsBefore);
      expect(find.text('촬영 중'), findsOneWidget);
    });

    // 2026-09-09. 전사가 켜진 뒤로 whisper 가 빈 결과를 내면 서버가 답변을
    // 저장하지 않고 다시 답하라고 한다. 계속 빈 결과면 **지원자는 같은 질문을
    // 영원히 본다** — 실기기에서 실제로 거기서 못 빠져나왔다.
    testWidgets('세 번 안 담기면 글로 답할 자리를 준다 — 막다른 길을 만들지 않는다', (tester) async {
      usePhone(tester);
      final h = await startedAt(tester);

      for (var i = 0; i < 3; i++) {
        h.socket.emit(const InterviewRetry('말이 들리지 않았어요. 다시 답변해 주세요'));
        await tester.pumpAndSettle();
      }
      await settleLive(tester);

      expect(find.textContaining('말이 잘 담기지 않습니다.'), findsOneWidget);
      expect(find.byType(TextField), findsOneWidget);
      expect(find.text('마이크로 다시 시도'), findsOneWidget);
    });

    testWidgets('두 번째부터는 왜 안 담기는지 같이 알려 준다', (tester) async {
      usePhone(tester);
      final h = await startedAt(tester);

      for (var i = 0; i < 2; i++) {
        h.socket.emit(const InterviewRetry('말이 들리지 않았어요'));
        await tester.pumpAndSettle();
      }

      expect(find.textContaining('마이크가 소리를 잘 못 잡고 있을 수 있습니다'), findsOneWidget);
    });

    testWidgets('다음 질문이 오면 안 담긴 횟수가 지워진다', (tester) async {
      usePhone(tester);
      final h = await startedAt(tester);

      h.socket.emit(const InterviewRetry('말이 들리지 않았어요'));
      await tester.pumpAndSettle();
      h.socket.emit(const InterviewQuestion(text: '다음 질문입니다.', seq: 2));
      await tester.pumpAndSettle();
      h.socket.emit(const InterviewRetry('말이 들리지 않았어요'));
      await tester.pumpAndSettle();

      // 앞 질문의 횟수가 이어지면 여기서 벌써 글로 물러섰을 것이다
      expect(find.byType(TextField), findsNothing);
    });

    testWidgets('말이 안 담겼으면 같은 질문을 두고 다시 답하게 한다', (tester) async {
      usePhone(tester);
      final h = await startedAt(tester);

      h.socket.emit(const InterviewRetry('말이 들리지 않았어요. 다시 답변해 주세요'));
      await tester.pumpAndSettle();

      expect(find.text('말이 들리지 않았어요. 다시 답변해 주세요'), findsOneWidget);
      // 질문은 그대로다 — 답한 것으로 세지 않았으므로
      expect(find.text('자기소개를 해 주세요.'), findsOneWidget);
    });

    testWidgets('끝나면 완료 화면으로 가고 마이크·카메라를 놓는다', (tester) async {
      usePhone(tester);
      final h = await startedAt(tester);

      h.socket.emit(const InterviewDone());
      await settleLive(tester);

      expect(find.text('면접이 완료되었습니다. 참여해 주셔서 감사합니다.'), findsOneWidget);
      expect(h.mic.stops, greaterThan(0));
      expect(h.camera.stops, greaterThan(0));
      // **`finish` 를 부르지 않는다** — 질문이 떨어진 것을 아는 워커가 이미 닫았다
      expect(h.portal.calls, isNot(contains('finish:tok')));
    });

    testWidgets('서버가 이유를 말하고 끊으면 그대로 알린다', (tester) async {
      usePhone(tester);
      final h = await startedAt(tester);

      // `retryable` 이 아니다 — 다시 붙어도 같은 답이 온다
      h.socket.emit(const InterviewFailed('진행 중인 면접이 아닙니다'));
      await settleLive(tester);

      expect(find.text('진행 중인 면접이 아닙니다'), findsOneWidget);
      expect(find.text('연결 실패'), findsOneWidget);
      // 다시 붙지 않는다
      expect(h.sockets, hasLength(1));
    });

    // 2026-09-09. 워커가 전사 문제로 재시작하면 소켓이 그냥 끊겼는데, 앱이
    // 거기서 포기했다. PROTOCOL.md 는 "재접속만 하면 아직 답하지 않은 가장 앞
    // 질문부터 이어진다" 고 적어 두었다 — 그걸 앱이 안 하고 있었다.
    testWidgets('그냥 끊긴 것이면 다시 붙는다 — 마이크·카메라는 놓지 않는다', (tester) async {
      usePhone(tester);
      final h = await startedAt(tester);
      final micStopsBefore = h.mic.stops;

      h.socket.emit(
        const InterviewFailed('연결이 끊겼습니다. 다시 잇는 중…', retryable: true),
      );
      await settleReconnect(tester);

      expect(h.sockets, hasLength(2));
      // **마이크를 놓지 않았다** — 놓으면 다시 붙어도 소리가 안 간다
      expect(h.mic.stops, micStopsBefore);
      expect(h.camera.stops, 0);
    });

    testWidgets('다시 붙어 질문이 오면 오류 표시가 사라진다', (tester) async {
      usePhone(tester);
      final h = await startedAt(tester);

      h.socket.emit(
        const InterviewFailed('연결이 끊겼습니다. 다시 잇는 중…', retryable: true),
      );
      await settleReconnect(tester);

      h.sockets.last.emit(const InterviewQuestion(text: '이어서 질문입니다.', seq: 2));
      await tester.pumpAndSettle();

      expect(find.text('이어서 질문입니다.'), findsOneWidget);
      expect(find.text('연결 실패'), findsNothing);
    });

    testWidgets('면접 중에 카메라가 끊기면 조용히 넘기지 않는다', (tester) async {
      usePhone(tester);
      final h = await startedAt(tester);

      h.camera.push(CameraStatus.failed);
      await tester.pumpAndSettle();

      expect(find.text('촬영 중'), findsNothing);
      expect(find.text('카메라를 쓸 수 없습니다'), findsOneWidget);
    });

    // 2026-09-09 실기기 회귀. 권한을 **허용한** 지원자에게 "마이크 권한이 꺼져
    // 있습니다" 가 떴다. 카메라가 권한 창을 띄우고 있는 동안 마이크를 열려고 해서,
    // 안드로이드가 요청 두 개를 동시에 못 받고 마이크 쪽에 거짓을 돌려준 것이다.
    testWidgets('권한 창이 닫히기 전에는 마이크를 열지 않는다', (tester) async {
      usePhone(tester);
      final gate = Completer<void>();
      final h = host(
        interview: interviewOf(
          status: InterviewStatus.inProgress,
          consentRequired: false,
          question: '자기소개를 해 주세요.',
          seq: 1,
        ),
        cameraOpening: gate,
      );
      await tester.pumpWidget(h.widget);
      await settleLive(tester);

      // 카메라가 아직 여는 중이다 — 마이크에 손대면 안 된다
      expect(h.camera.starts, 1);
      expect(h.mic.starts, 0);

      gate.complete();
      await settleLive(tester);

      expect(h.mic.starts, 1);
    });
  });

  // 마이크가 막힌 지원자. **면접을 못 보게 하지 않는다** — 기기 사정이 지원
  // 자격이 되면 안 된다. 말로 못 하면 글로 답한다(원래 있던 길이다).
  group('진행 — 마이크가 막히면 글로', () {
    Future<
      ({FakeApplicantPortalRepository portal, FakeInterviewSocket socket})
    >
    blockedAt(WidgetTester tester) async {
      final h = host(
        interview: interviewOf(
          status: InterviewStatus.inProgress,
          consentRequired: false,
          question: '자기소개를 해 주세요.',
          seq: 1,
        ),
        micFails: const MicUnavailable('마이크 권한이 꺼져 있습니다.', permanent: true),
      );
      await tester.pumpWidget(h.widget);
      await settleLive(tester);
      return (portal: h.portal, socket: h.socket);
    }

    testWidgets('왜 글로 쓰는지 말해 주고 입력창을 준다', (tester) async {
      usePhone(tester);
      await blockedAt(tester);

      expect(find.textContaining('마이크 권한이 꺼져 있습니다.'), findsOneWidget);
      expect(find.byType(TextField), findsOneWidget);
      expect(find.text('답변 제출'), findsOneWidget);
    });

    testWidgets('말로 못 하게 됐으면 소켓도 닫는다 — 소리 없는 연결을 붙들지 않는다', (tester) async {
      usePhone(tester);
      final h = await blockedAt(tester);

      expect(h.socket.closed, isTrue);
    });

    testWidgets('다시 시도할 자리를 준다 — 막다른 길로 두지 않는다', (tester) async {
      usePhone(tester);
      await blockedAt(tester);

      expect(find.text('마이크로 다시 시도'), findsOneWidget);
    });

    testWidgets('답변이 비면 제출할 수 없다', (tester) async {
      usePhone(tester);
      await blockedAt(tester);

      final button = tester.widget<FilledButton>(
        find.ancestor(
          of: find.text('답변 제출'),
          matching: find.byType(FilledButton),
        ),
      );
      expect(button.onPressed, isNull);
    });

    testWidgets('답변을 내면 다음 질문으로 넘어간다', (tester) async {
      usePhone(tester);
      final h = await blockedAt(tester);

      await tester.enterText(find.byType(TextField), '3년차 프론트엔드 개발자입니다.');
      await tester.pumpAndSettle();
      await tester.tap(find.text('답변 제출'));
      await tester.pumpAndSettle();

      expect(h.portal.calls, contains('answer:tok:3년차 프론트엔드 개발자입니다.'));
      expect(find.text('질문 2'), findsOneWidget);
    });

    testWidgets('제출하면 입력창이 비워진다 — 앞 답이 남으면 다음 답에 섞인다', (tester) async {
      usePhone(tester);
      await blockedAt(tester);

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
      usePhone(tester);
      await blockedAt(tester);

      await tester.enterText(find.byType(TextField), '짧은 답');
      await tester.pumpAndSettle();
      await tester.tap(find.text('답변 제출'));
      await tester.pumpAndSettle();

      expect(find.text('조금 더 자세히 말씀해 주셔도 좋습니다.'), findsOneWidget);
    });
  });

  group('종료', () {
    testWidgets('확인 시트를 거치고, 취소하면 아무 일도 없다', (tester) async {
      usePhone(tester);
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
      usePhone(tester);
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
      usePhone(tester);
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
      usePhone(tester);
      final h = host();
      await tester.pumpWidget(h.widget);
      await tester.pumpAndSettle();

      await _leaveApp(tester);
      await _returnToApp(tester);

      expect(h.camera.starts, 0);
    });
  });

  // 2026-09-08 실기기: 면접 탭에서 다른 탭으로 옮겨도 카메라가 잡혀 있었다.
  // 셸의 IndexedStack 이 화면을 살려 두는데 탭 전환은 앱 생명주기 신호가 안
  // 온다 — 그 사이 다른 앱이 카메라를 가져가면 돌아왔을 때 검은 화면이 남는다.
  group('탭이 가려질 때', () {
    Widget host({
      required bool active,
      required FakeApplicantPortalRepository portal,
      required FakeCameraService camera,
    }) => MaterialApp(
      home: Scaffold(
        body: InterviewScreen(
          token: 'tok',
          showChrome: false,
          active: active,
          portal: portal,
          camera: camera,
        ),
      ),
    );

    testWidgets('가려지면 놓고, 다시 보이면 연다', (tester) async {
      usePhone(tester);
      final portal = FakeApplicantPortalRepository(
        interviews: {
          'tok': interviewOf(
            status: InterviewStatus.inProgress,
            consentRequired: false,
            question: '질문',
            seq: 1,
          ),
        },
      );
      final camera = FakeCameraService();

      await tester.pumpWidget(
        host(active: true, portal: portal, camera: camera),
      );
      await tester.pumpAndSettle();
      expect(camera.status, CameraStatus.live);
      final startsBefore = camera.starts;

      await tester.pumpWidget(
        host(active: false, portal: portal, camera: camera),
      );
      await tester.pumpAndSettle();
      expect(camera.stops, 1);
      expect(camera.status, CameraStatus.idle);

      await tester.pumpWidget(
        host(active: true, portal: portal, camera: camera),
      );
      await tester.pumpAndSettle();
      expect(camera.starts, startsBefore + 1);
      expect(camera.status, CameraStatus.live);
    });

    testWidgets('가려진 채로 열리면 아예 안 켠다', (tester) async {
      usePhone(tester);
      final portal = FakeApplicantPortalRepository(
        interviews: {
          'tok': interviewOf(
            status: InterviewStatus.inProgress,
            consentRequired: false,
            question: '질문',
            seq: 1,
          ),
        },
      );
      final camera = FakeCameraService();

      await tester.pumpWidget(
        host(active: false, portal: portal, camera: camera),
      );
      await tester.pumpAndSettle();

      expect(camera.starts, 0);
    });
  });

  group('만료·오류', () {
    testWidgets('만료된 링크는 그렇다고 말하고 카메라를 안 켠다', (tester) async {
      usePhone(tester);
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
      usePhone(tester);
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
