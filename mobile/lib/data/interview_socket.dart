/// AI 면접 실시간 연결 — 아르가 묻고, 앱이 소리와 얼굴을 보낸다 (2026-09-09).
///
/// 원본 규격은 `ai/lie-detection/PROTOCOL.md` 다. 웹은
/// `frontend/app/src/pages/useAiInterview.ts` 가 같은 일을 한다.
///
/// ```
/// wss://api.seuk.suvisdev.cloud/ai/ws/interview/{token}
/// ```
///
/// ## 소켓은 하나뿐이다
///
/// 소리·영상을 이 한 곳으로 보내고 질문을 여기서 받는다.
///
/// ## 판정은 이 기기를 지나가지 않는다
///
/// 웹에서 한 번 겪은 것이라 앱에서도 처음부터 그렇게 둔다 — 지원자 기기가
/// 판정을 받으면 화면에 안 그려도 **가로채면 보인다**(ADR-0029 위반).
/// 지금은 `워커 → 백엔드 → 담당자` 라, 이 파일에는 판정을 받는 코드가 없다.
/// 서버가 보내 주지 않으므로 화면이 그리고 싶어도 그럴 값이 없다.
///
/// ## 붙기 전에 REST 로 동의·시작을 끝내야 한다
///
/// 시작하지 않은 채 붙으면 서버가 `error` 를 보내고 닫는다. 화면이 순서를
/// 지킨다([InterviewScreen]).
library;

import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:web_socket_channel/web_socket_channel.dart';

import '../api/api_config.dart';

/// 바이너리 첫 바이트 — 무엇을 보내는지 (PROTOCOL.md)
const int kindAudio = 0x01;
const int kindVideo = 0x02;

/// 서버가 보내오는 것. `type` 하나로 갈리므로 sealed 로 둔다 —
/// 화면의 `switch` 가 새 종류를 빠뜨리면 컴파일이 잡아 준다
sealed class InterviewEvent {
  const InterviewEvent();
}

/// 새 질문. 접속 직후 한 번, 그리고 답변이 저장될 때마다
class InterviewQuestion extends InterviewEvent {
  const InterviewQuestion({required this.text, this.seq});

  final String text;
  final int? seq;
}

/// 말을 시작한 것을 서버가 알아챘다
class InterviewListening extends InterviewEvent {
  const InterviewListening();
}

/// 말이 끝나 전사·저장 중
class InterviewProcessing extends InterviewEvent {
  const InterviewProcessing();
}

/// 말이 안 담겨 답변으로 세지 않았다. **같은 질문을 그대로 두고 다시 답하게 한다**
class InterviewRetry extends InterviewEvent {
  const InterviewRetry(this.message);

  final String message;
}

/// 남은 질문이 없다. **서버가 세션도 닫는다** — 화면이 `finish` 를 또 부르지 않는다
class InterviewDone extends InterviewEvent {
  const InterviewDone();
}

/// 진행할 수 없다. 연결이 끊긴 것과 서버가 거절한 것을 여기서 합친다 —
/// 지원자가 할 일(다시 들어오기)이 같다
class InterviewFailed extends InterviewEvent {
  const InterviewFailed(this.message);

  final String message;
}

/// 면접 소켓 하나. 화면은 [WebSocketChannel] 을 직접 만들지 않고 이것만 안다 —
/// 실기기·서버 없이 테스트가 돌아야 한다([CameraService] 와 같은 이유).
abstract class InterviewSocket {
  /// 서버가 보내오는 것들. 닫히면 스트림도 끝난다
  Stream<InterviewEvent> get events;

  /// PCM 한 조각 (16kHz·16-bit·mono, 50ms). 닫힌 뒤에 부르면 조용히 버린다
  void sendAudio(Uint8List pcm);

  /// 영상 한 장 (JPEG)
  void sendVideo(Uint8List jpeg);

  Future<void> close();
}

/// 진짜 연결.
class LiveInterviewSocket implements InterviewSocket {
  LiveInterviewSocket(this.token, {WebSocketChannel? channel})
    : _channel = channel ?? WebSocketChannel.connect(socketUrl(token)) {
    _channel.stream.listen(
      _onMessage,
      onError: (Object e, StackTrace _) {
        if (kDebugMode) debugPrint('[면접소켓] 오류: $e');
        _fail('서버에 연결하지 못했습니다');
      },
      onDone: () {
        // 끝났다고 알린 뒤에 닫히는 것이 정상이다. 그 경우는 아무 말도 하지 않는다 —
        // "면접이 끝났습니다" 위에 "연결이 끊겼습니다" 를 덮어쓰면 놀란다
        if (!_closed && !_finished) _fail('연결이 끊겼습니다. 다시 들어와 주세요');
        _events.close();
      },
      cancelOnError: false,
    );
  }

  final String token;
  final WebSocketChannel _channel;
  final StreamController<InterviewEvent> _events =
      StreamController<InterviewEvent>.broadcast();

  bool _closed = false;
  bool _finished = false;

  /// `https://api…` → `wss://api…/ai/ws/interview/{token}`.
  ///
  /// **`/api/v1` 접두어를 붙이면 안 된다** — `/ai/*` 는 Caddy 가 거짓말 탐지
  /// 서비스로 바로 넘기는 경로라 백엔드 접두어와 자리가 다르다.
  static Uri socketUrl(String token) {
    final host = Uri.parse(ApiConfig.host);
    return host.replace(
      scheme: host.scheme == 'https' ? 'wss' : 'ws',
      path: '/ai/ws/interview/$token',
    );
  }

  @override
  Stream<InterviewEvent> get events => _events.stream;

  void _onMessage(dynamic raw) {
    if (raw is! String) return;
    final Object? decoded;
    try {
      decoded = jsonDecode(raw);
    } on FormatException {
      return;
    }
    if (decoded is! Map<String, dynamic>) return;

    switch (decoded['type']) {
      case 'question':
        final text = decoded['text'];
        if (text is! String) return;
        _add(InterviewQuestion(text: text, seq: decoded['seq'] as int?));
      case 'listening':
        _add(const InterviewListening());
      case 'processing':
        _add(const InterviewProcessing());
      case 'retry':
        _add(InterviewRetry(_messageOf(decoded, '말이 들리지 않았어요. 다시 답변해 주세요')));
      case 'done':
        _finished = true;
        _add(const InterviewDone());
      case 'error':
        _finished = true; // 서버가 이유를 말했다. 그 뒤의 끊김은 다시 말하지 않는다
        _fail(_messageOf(decoded, '면접을 진행하지 못했습니다'));
      case 'pong':
        break;
    }
  }

  static String _messageOf(Map<String, dynamic> m, String fallback) {
    final v = m['message'];
    return v is String && v.isNotEmpty ? v : fallback;
  }

  void _fail(String message) => _add(InterviewFailed(message));

  void _add(InterviewEvent event) {
    if (_events.isClosed) return;
    _events.add(event);
  }

  void _send(int kind, Uint8List payload) {
    if (_closed) return;
    // 첫 바이트가 종류, 나머지가 알맹이 (PROTOCOL.md)
    final packet = Uint8List(1 + payload.length);
    packet[0] = kind;
    packet.setRange(1, packet.length, payload);
    try {
      _channel.sink.add(packet);
    } on StateError {
      // 이미 닫힌 소켓에 넣었다. 마이크·카메라가 한 박자 늦게 멈추는 것은 정상이다
    }
  }

  @override
  void sendAudio(Uint8List pcm) => _send(kindAudio, pcm);

  @override
  void sendVideo(Uint8List jpeg) => _send(kindVideo, jpeg);

  @override
  Future<void> close() async {
    if (_closed) return;
    _closed = true;
    try {
      await _channel.sink.close();
    } on Exception {
      // 닫는 데 실패해도 화면은 나가야 한다
    }
  }
}
