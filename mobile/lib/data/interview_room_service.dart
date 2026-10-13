/// 실시간 면접(WebRTC) — 지원자 자리 (2026-09-09).
///
/// 웹의 [useInterviewRoom.ts]([frontend/app/src/pages/useInterviewRoom.ts])
/// 를 Dart 로 옮긴 것. **자리는 지원자 하나뿐이다** — 앱에서 담당자를 하지
/// 않는다(담당자는 노트북 웹). 그래서 입장권(rtc-ticket)도, offer 만들기도
/// 없다. 지원자는 받은 offer 에 answer 만 낸다.
///
/// 규격 원본은 [docs/02_tasks/실시간-면접-시그널링.md] 와
/// [backend/app/api/interview_rtc.py]. 값을 바꾸면 같이 고친다.
///
/// ## AI 면접([CameraService])과 카메라를 공유하지 않는다
///
/// AI 면접은 [CameraController] 로 카메라를 잡아 JPEG 프레임을 서버로 흘린다.
/// WebRTC 는 [navigator.mediaDevices.getUserMedia] 를 자기가 부른다.
/// **둘 다 카메라를 잡으면 안드로이드가 하나에게만 준다** — 같은 화면에서
/// 두 경로가 겹치지 않게 라우팅을 다르게 두었다.
library;

import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:flutter_webrtc/flutter_webrtc.dart';
import 'package:web_socket_channel/status.dart' as ws_status;
import 'package:web_socket_channel/web_socket_channel.dart';

import '../api/api_config.dart';

/// 면접방이 지금 어떤 자리에 있는지.
///
/// 화면이 문구를 정하는 자리는 [phaseLabel]. 여기서는 상태만 다룬다.
enum RoomPhase {
  /// 카메라를 켜고 서버에 붙는 중
  preparing,

  /// 붙었지만 담당자(상대)가 아직 안 들어옴
  waiting,

  /// 서로 쪽지(SDP·ICE)를 주고받는 중
  connecting,

  /// 영상·음성이 오간다
  live,

  /// 담당자가 나갔다 — 다시 들어오면 저절로 이어진다
  peerLeft,

  /// 되돌릴 수 없는 실패. [InterviewRoomService.errorMessage] 에 사유
  error,
}

/// 서버가 주는 error.code 중 화면이 말을 바꿔야 하는 것들.
/// 모르는 코드는 서버 message 를 그대로 보여 준다 — 서버가 늘려도 화면이
/// 안 깨지게.
const _fatalCodes = {'session_closed', 'replaced'};

const _pingEvery = Duration(seconds: 25);

/// PeerConnection 과 WebSocket 과 카메라를 한 몸에 묶어 관리한다.
///
/// [ChangeNotifier] 인 이유는 화면이 phase 를 그림으로 반영해야 하고,
/// 서버가 [peer-leave] 같은 메시지를 스스로 보내오면 화면이 그것을 알아야
/// 하기 때문이다. 화면이 물어보는 구조로는 그 순간을 놓친다.
///
/// 수명 관리:
/// - [start] 는 한 번만 부른다 (재사용하지 않는다 — [dispose] 뒤 새로 만든다)
/// - 화면이 사라지면 반드시 [dispose] — 안 부르면 카메라 표시등이 남고
///   서버 방이 안 비워진다
class InterviewRoomService extends ChangeNotifier {
  InterviewRoomService(this.token);

  final String token;

  RoomPhase _phase = RoomPhase.preparing;
  String? _errorMessage;

  MediaStream? _localStream;
  MediaStream? _remoteStream;

  RTCPeerConnection? _pc;
  WebSocketChannel? _ws;
  StreamSubscription<dynamic>? _wsSub;
  List<Map<String, dynamic>> _iceServers = const [];
  Timer? _pingTimer;

  /// 언마운트/폐기 뒤에 도착한 응답이 다시 카메라를 켜지 않게 한다.
  bool _alive = true;

  RoomPhase get phase => _phase;
  String? get errorMessage => _errorMessage;
  MediaStream? get localStream => _localStream;
  MediaStream? get remoteStream => _remoteStream;

  void _setPhase(RoomPhase next) {
    if (_phase == next) return;
    _phase = next;
    notifyListeners();
  }

  void _fail(String message) {
    _errorMessage = message;
    _setPhase(RoomPhase.error);
  }

  /// 서버에 붙고 카메라를 켠다. 성공하면 [RoomPhase.waiting] 또는
  /// [RoomPhase.connecting] 으로 넘어간다.
  Future<void> start() async {
    _alive = true;

    // 0) **오디오 세션을 미디어 모드로 못 박는다** (2026-09-15 실기기 재현).
    //    flutter_webrtc 는 오디오를 안 잡아도 초기화 과정에서 안드로이드
    //    AudioManager 를 `MODE_IN_COMMUNICATION` 으로 바꾼다. 그 상태에서 record
    //    가 새 AudioRecord 를 default 소스로 열면 삼성 QCOM HAL 이 시작 직후
    //    두 번 close 시켜 조각이 하나도 안 도착한다 (logcat:
    //    `PCM_RECORD IoHandle:3518 stream was closed`, `updateVoiceBoosterState
    //    curDevice 2` = EARPIECE). `media` 로 명시하면 세션이 음악 재생 모드로
    //    남아 record 가 정상적으로 열린다.
    try {
      await AndroidNativeAudioManagement.setAndroidAudioConfiguration(
        AndroidAudioConfiguration.media,
      );
    } on Object catch (e) {
      // iOS 나 데스크톱 시뮬레이터에서는 무시한다 — Android 에서만 유효한 값이다
      if (kDebugMode) debugPrint('[rtc] 오디오 세션 설정 실패(무시): $e');
    }

    // 1) **카메라만** 잡는다. 마이크는 STT 파이프(`MicService` · record)가 혼자 연다.
    //
    //    09-09 ~ 09-14 까지는 여기서 마이크도 같이 잡았다(담당자가 목소리를 WebRTC
    //    로 듣게). 그러면 앱 안에 AudioRecord 가 둘(WebRTC VOICE_COMMUNICATION +
    //    record MIC)인데, 안드로이드는 이것을 보장하지 않는다 — 실기기(2026-09-15)
    //    에서 둘이 겹쳐 뜨는 순간 native 크래시("앱에 버그가 있어 종료"), 안 겹치면
    //    WebRTC 의 자동 이득이 바닥 소음을 끌어올려(서버 실측 바닥값 108 → 721)
    //    서버가 잡음을 말로 세거나 말을 못 알아듣는다. 마이크 하나로 둔다.
    //
    //    담당자 쪽 목소리는 서버가 STT 용으로 받는 PCM 을 담당자 화면으로 흘려
    //    주는 것으로 채운다(별도 작업) — 앱을 다시 만들지 않아도 된다.
    try {
      final stream = await navigator.mediaDevices.getUserMedia({
        'audio': false,
        'video': {
          'width': {'ideal': 1280},
          'height': {'ideal': 720},
          'facingMode': 'user',
        },
      });
      if (!_alive) {
        for (final t in stream.getTracks()) {
          await t.stop();
        }
        return;
      }
      _localStream = stream;
      notifyListeners();
    } on Object catch (e) {
      if (kDebugMode) debugPrint('[rtc] getUserMedia 실패: $e');
      _fail('카메라·마이크를 사용할 수 없습니다. 권한을 허용해 주세요');
      return;
    }

    // 2) WebSocket 시그널링. api.seuk.suvisdev.cloud → wss://.../ws/...
    final wsBase = ApiConfig.base
        .replaceFirst('https://', 'wss://')
        .replaceFirst('http://', 'ws://');
    final url = Uri.parse('$wsBase/ws/interview/$token/rtc');
    try {
      _ws = WebSocketChannel.connect(url);
    } on Object catch (e) {
      if (kDebugMode) debugPrint('[rtc] WS 연결 실패: $e');
      _fail('서버에 연결하지 못했습니다');
      return;
    }

    _wsSub = _ws!.stream.listen(
      _onMessage,
      onError: (Object err) {
        if (!_alive) return;
        if (kDebugMode) debugPrint('[rtc] WS 오류: $err');
        _fail('서버에 연결하지 못했습니다');
      },
      onDone: () {
        // 정상 종료면 그대로 두고, 붙기 전에 끊기면 오류로 본다.
        if (!_alive) return;
        if (_phase == RoomPhase.preparing || _phase == RoomPhase.waiting) {
          _fail('서버와의 연결이 끊겼습니다');
        }
      },
    );

    _pingTimer = Timer.periodic(_pingEvery, (_) => _send({'type': 'ping'}));
  }

  /// 사용자가 눌러 나간다. 서버에는 bye 를 먼저 보내고 닫는다 — 담당자가
  /// "끊겼나?" 하고 기다리지 않게.
  Future<void> leave() async {
    _send({'type': 'bye'});
    _setPhase(RoomPhase.peerLeft);
    await _cleanup();
  }

  Future<void> _cleanup() async {
    _pingTimer?.cancel();
    _pingTimer = null;

    await _teardownPeer();

    await _wsSub?.cancel();
    _wsSub = null;
    try {
      await _ws?.sink.close(ws_status.normalClosure);
    } on Object {
      // 이미 닫힌 소켓을 또 닫는 것은 실패해도 상관없다
    }
    _ws = null;

    final local = _localStream;
    _localStream = null;
    if (local != null) {
      for (final t in local.getTracks()) {
        await t.stop();
      }
      await local.dispose();
    }
    notifyListeners();
  }

  Future<void> _teardownPeer() async {
    final pc = _pc;
    _pc = null;
    if (pc != null) {
      await pc.close();
    }
    final remote = _remoteStream;
    _remoteStream = null;
    if (remote != null) {
      await remote.dispose();
    }
    notifyListeners();
  }

  void _send(Map<String, dynamic> msg) {
    final ws = _ws;
    if (ws == null) return;
    try {
      ws.sink.add(jsonEncode(msg));
    } on Object catch (e) {
      if (kDebugMode) debugPrint('[rtc] 송신 실패: $e');
    }
  }

  Future<void> _onMessage(dynamic raw) async {
    if (!_alive) return;
    Map<String, dynamic> msg;
    try {
      msg = jsonDecode(raw as String) as Map<String, dynamic>;
    } on Object {
      return;
    }

    switch (msg['type'] as String?) {
      case 'hello':
        final servers = msg['ice_servers'];
        if (servers is List) {
          _iceServers = servers.cast<Map<String, dynamic>>();
        }
        // 지원자는 offer 를 만들지 않는다. 담당자가 들어와 있으면
        // 상대의 offer 를 곧 받는다. 없으면 기다린다.
        final peerPresent = msg['peer_present'] == true;
        _setPhase(peerPresent ? RoomPhase.connecting : RoomPhase.waiting);
        break;

      case 'peer-join':
        // 담당자만 offer 를 낸다. 지원자는 그것을 기다린다.
        _setPhase(RoomPhase.connecting);
        break;

      case 'peer-leave':
        await _teardownPeer();
        _setPhase(RoomPhase.peerLeft);
        break;

      case 'offer':
        final sdp = msg['sdp'] as String?;
        if (sdp == null) break;
        final pc = await _newPeer();
        await pc.setRemoteDescription(RTCSessionDescription(sdp, 'offer'));
        final answer = await pc.createAnswer();
        await pc.setLocalDescription(answer);
        _send({'type': 'answer', 'sdp': answer.sdp});
        break;

      case 'answer':
        // 지원자 자리에서는 answer 가 오면 안 된다(우리가 offer 를 안 낸다).
        // 서버가 잘못 보내는 경우가 없어야 하지만, 왔다고 화면이 죽을 이유는 없다.
        break;

      case 'ice':
        final cand = msg['candidate'];
        final pc = _pc;
        if (pc != null && cand is Map) {
          try {
            await pc.addCandidate(RTCIceCandidate(
              cand['candidate'] as String?,
              cand['sdpMid'] as String?,
              (cand['sdpMLineIndex'] as num?)?.toInt(),
            ));
          } on Object catch (e) {
            // 아직 remoteDescription 이 없을 때 후보가 먼저 오는 일이 있다.
            // 치명적이지 않다 — 다음 후보로 붙는다.
            if (kDebugMode) debugPrint('[rtc] ICE 추가 실패: $e');
          }
        }
        break;

      case 'error':
        final code = msg['code'] as String?;
        final message =
            (msg['message'] as String?) ?? '면접방에 들어갈 수 없습니다';
        if (code != null && _fatalCodes.contains(code)) {
          _fail(message);
        }
        // `no_peer` 는 오류가 아니다 — 상대가 아직 안 들어온 것뿐이다.
        break;

      case 'pong':
        // 서버 왕복 확인. 아무것도 안 한다.
        break;
    }
  }

  /// PeerConnection 은 매번 새로 만든다. 상대가 나갔다 들어올 때 헌 것을
  /// 재활용하면 ICE 상태가 남아 안 붙는다.
  Future<RTCPeerConnection> _newPeer() async {
    await _teardownPeer();
    final pc = await createPeerConnection(
      {'iceServers': _iceServers},
      {},
    );
    _pc = pc;

    /* **오디오 모드를 여기서 한 번 더 못 박는다** (2026-10-13).

       [start] 맨 앞에서 `media` 로 맞춰 두는데, 피어 연결을 만드는 이 자리에서
       flutter_webrtc 가 안드로이드 AudioManager 를 다시 통화 모드로 돌린다.
       그러면 **이미 열려 있던 record 의 AudioRecord 가 그 자리에서 죽어** 조각이
       한 개도 안 온다 — 예외도 안 나고 권한 문제도 아니라 밖에서는 "말이 안
       들어간다" 로만 보인다(10-13 실측: 담당자가 방에 먼저 있으면 앱이 붙는 즉시
       offer 가 와서 이 자리가 `_mic.start()` 와 겹친다).

       화면 쪽에도 되보는 시계를 뒀지만(`interview_live_screen._watchMic`), 원인은
       여기라 여기서 먼저 막는다. */
    try {
      await AndroidNativeAudioManagement.setAndroidAudioConfiguration(
        AndroidAudioConfiguration.media,
      );
    } on Object catch (e) {
      if (kDebugMode) debugPrint('[rtc] 오디오 세션 재설정 실패(무시): $e');
    }

    // 내 카메라·마이크를 붙인다. 지원자는 [start] 에서 이미 켠 상태.
    final local = _localStream;
    if (local != null) {
      for (final t in local.getTracks()) {
        await pc.addTrack(t, local);
      }
    }

    pc.onIceCandidate = (RTCIceCandidate c) {
      _send({
        'type': 'ice',
        'candidate': {
          'candidate': c.candidate,
          'sdpMid': c.sdpMid,
          'sdpMLineIndex': c.sdpMLineIndex,
        },
      });
    };

    pc.onTrack = (RTCTrackEvent event) {
      if (event.streams.isEmpty) return;
      final stream = event.streams.first;
      // **담당자 목소리는 폰에서 재생하지 않는다** (2026-09-09 팀장 결정).
      // 면접은 아르가 진행하고 담당자는 관찰만 한다 — 지원자가 들을 것이 없다.
      // 실익이 하나 더 있다: 폰 스피커로 나온 담당자 소리가 폰 마이크로 되돌아가
      // 담당자에게 재순환하던 하울링이 원천에서 사라진다. 트랙을 끄면 되고
      // 수신 자체는 그대로라 SDP 협상은 건드리지 않는다.
      for (final t in stream.getAudioTracks()) {
        t.enabled = false;
      }
      _remoteStream = stream;
      _setPhase(RoomPhase.live);
      notifyListeners();
    };

    pc.onConnectionState = (RTCPeerConnectionState state) {
      if (state == RTCPeerConnectionState.RTCPeerConnectionStateFailed) {
        // 여기까지 왔는데 실패면 대개 망 문제다 — 서로 다른 망이면
        // TURN 없이는 못 붙는다. 사유를 지어내지 않고 사실만 적는다.
        _fail('연결하지 못했습니다. 서로 다른 망이면 붙지 않을 수 있습니다');
      }
    };

    return pc;
  }

  @override
  void dispose() {
    _alive = false;
    // dispose 는 비동기를 기다릴 수 없다 — 흘려보낸다.
    _cleanup().ignore();
    super.dispose();
  }
}

/// 자리마다 문구가 다르다. "상대" 라고만 쓰면 누가 안 왔는지 알 수 없다.
/// 앱은 지원자 자리만 있으므로 담당자 관점의 문구는 필요 없다.
String phaseLabel(RoomPhase phase) => switch (phase) {
  RoomPhase.preparing => '준비 중',
  RoomPhase.waiting => '면접관을 기다리는 중',
  RoomPhase.connecting => '연결하는 중',
  RoomPhase.live => '연결됨',
  RoomPhase.peerLeft => '면접관이 나갔습니다',
  RoomPhase.error => '연결 실패',
};
