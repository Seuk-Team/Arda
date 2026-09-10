/// 실시간 면접 지원자 화면 — AI 면접 UX + WebRTC 스트리밍 (2026-09-09).
///
/// **한 화면에서 세 가지가 같이 돈다**:
/// - AI 면접 UX (지원자 본인 카메라 크게, 현재 질문 배너, 아르 안내)
/// - **WebRTC 로 담당자에게 카메라 영상 실시간 스트림** — 담당자는
///   [InterviewRoom] 에서 얼굴을 본다. 오디오는 흘리지 않는다.
/// - **lie-detection 소켓으로 마이크 흘림** — 서버가 소리를 듣고 전사(STT)
///   하고, 그 결과가 담당자에게 텍스트로 붙는다.
///
/// **카메라와 마이크를 다른 파이프에 나눠 잡는 이유**: 안드로이드는 앱 안에서도
/// AudioRecord 인스턴스가 하나뿐이라 flutter_webrtc 와 record 가 마이크를 같이
/// 잡을 수 없다. 카메라는 flutter_webrtc 가 잡고, 마이크는 record 가 잡는다.
///
/// ## AI 면접 상태 흐름
///
/// - `pending` + consent_required: "동의하고 시작" 한 번에 [consent] → [start]
///   → 카메라·소켓 연결까지 밟는다.
/// - `in_progress`: 질문 배너 뜨고 실시간 두 파이프가 산다
/// - `done` / `expired`: 안내만
library;

import 'dart:async';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_webrtc/flutter_webrtc.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:wakelock_plus/wakelock_plus.dart';

import '../api/api_error.dart';
import '../data/applicant_portal_repository.dart';
import '../data/interview_room_service.dart';
import '../data/interview_socket.dart';
import '../data/mic_service.dart';
import '../models/applicant_portal.dart';
import '../theme/tokens.dart';

class InterviewLiveScreen extends StatefulWidget {
  const InterviewLiveScreen({
    super.key,
    required this.token,
    this.portal,
    this.serviceOverride,
  });

  final String? token;
  final ApplicantPortalRepository? portal;
  final InterviewRoomService? serviceOverride;

  @override
  State<InterviewLiveScreen> createState() => _InterviewLiveScreenState();
}

class _InterviewLiveScreenState extends State<InterviewLiveScreen> {
  late final ApplicantPortalRepository _portal =
      widget.portal ?? ApplicantPortalRepository();

  InterviewRoomService? _service;
  final _localRenderer = RTCVideoRenderer();
  final _remoteRenderer = RTCVideoRenderer();
  bool _renderersReady = false;

  InterviewPublic? _info;
  String? _error;
  bool _sending = false;

  // ── lie-detection 오디오 파이프 ─────────────────────────────
  //
  // 마이크 → 16kHz PCM → 소켓 → 서버 STT → 다음 질문. WebRTC 가 카메라를 잡아
  // 담당자에게 얼굴을 보내는 동안, 이쪽은 소리와 질문을 나른다.
  final MicService _mic = DeviceMicService();
  InterviewSocket? _liveSocket;
  StreamSubscription<InterviewEvent>? _liveEvents;
  StreamSubscription<Uint8List>? _audio;

  /// 소켓이 알려 주는 현재 질문. REST 의 [InterviewPublic.currentQuestion] 보다
  /// 최신이다 — 답변이 저장되면 소켓이 바로 다음 질문을 보내지만 REST 는 조회
  /// 해야만 갱신된다.
  String? _liveQuestion;
  int? _liveSeq;

  /// 소켓 이벤트로 잡은 안내 문구 (`retry`, `done` 등).
  String? _liveNote;

  /// 서버가 지금 지원자의 말을 듣고 있는가.
  ///
  /// `listening` 이벤트가 오면 `true`, `processing`·`question` 이 오면 `false`.
  /// **화면에 배지로 뜬다** — 지원자가 자기 소리가 서버까지 닿는지 확인할 수
  /// 있어야 한다. 이 배지가 안 뜨면 마이크가 너무 멀거나 소리가 작다는 뜻이다.
  bool _listening = false;

  /// STT 소켓을 다시 붙어 본 횟수. **한없이 시도하지 않는다** — 서버가 정말
  /// 죽었으면 지원자에게 그렇다고 말해 줘야 한다 ([InterviewScreen] 과 같은 규칙).
  ///
  /// 2026-09-09 실기기: 전사가 길어지면 서버가 ping 응답을 못 넘겨 소켓을 닫았고,
  /// 이 화면은 "다시 잇는 중…" 이라 적어 놓고 실제로는 안 이었다 — 지원자가
  /// 화면을 나갔다 들어와야 이어졌다. 답변은 이미 저장된 뒤라, 다시 붙기만 하면
  /// 서버가 **아직 답하지 않은 다음 질문**을 바로 준다(PROTOCOL.md 「끊겼을 때」).
  int _retries = 0;
  static const int _retryMax = 5;

  // ── [답변 완료] 버튼 (2026-09-09) ────────────────────────────
  //
  // 서버 감지기는 "3초 연속 무음" 으로 말 끝을 잡는데, 50ms 조각 하나만 임계를
  // 넘어도 타이머가 0 으로 돌아간다. WebRTC 가 마이크를 같이 잡아 AGC 로 바닥이
  // 올라간 환경(실기기: 조용한 방의 25배)에선 그 3초가 거의 안 나와 답변이
  // 영영 안 넘어갔다. 지원자가 스스로 끝을 알리는 길을 둔다.
  //
  // 두 갈래로 보낸다: ① `{"type":"end"}` — 서버가 알면 즉시 전사.
  // ② 3.5초 동안 마이크 조각을 **무음(0)** 으로 바꿔 보낸다 — 서버가 ① 을 모르는
  // 동안에도 감지기의 자연 종료(3초 무음)가 걸린다. 조각의 길이·박자는 그대로라
  // 서버가 시간을 세는 방식(조각 길이 합)에 어긋나지 않는다.

  /// [답변 완료] 를 눌러 서버 응답(다음 질문·retry·done)을 기다리는 중
  bool _submitting = false;

  /// 이 시각까지는 마이크 조각 대신 무음을 보낸다 (② 폴백)
  DateTime? _muteUntil;
  static const Duration _muteFor = Duration(milliseconds: 3500);

  /// [답변 완료] 를 누른 질문 번호. 재접속 직후 서버는 "아직 답 없는 질문" 을
  /// 다시 보내는데, 그게 이 번호면 전사가 아직 도는 중인 것 — 화면을 되돌려
  /// 다시 답하게 하지 않는다 (2026-09-09: 그렇게 1번 답변이 2번에 중복 저장됐다).
  int? _submittedSeq;
  DateTime? _submittedAt;

  /// 제출 뒤 REST 로 현재 질문을 주기적으로 확인한다. 소켓이 전사 도중 죽으면
  /// 서버는 다음 질문을 새 소켓으로 밀어 줄 길이 없다 — 답변은 늘 첫 미답
  /// 질문에 붙으므로, REST 의 `question_seq` 가 넘어간 순간이 곧 "저장됐다" 다.
  Timer? _submitPoll;
  static const Duration _submitPollEvery = Duration(seconds: 4);

  /// 이 시간이 지나도 번호가 안 넘어가면 버튼을 되살린다. 전사 상한(45초)보다
  /// 길어야 정상 전사 중에 "확인 안 됨" 이 안 뜬다.
  static const Duration _submitGiveUp = Duration(seconds: 60);

  @override
  void initState() {
    super.initState();
    // 화면이 열려 있는 동안 화면이 꺼지지 않게 한다 — 안드로이드 기본 3분 뒤
    // 화면이 꺼지면 카메라·마이크가 다 끊긴다. 나가면 dispose 에서 놓는다.
    WakelockPlus.enable().ignore();
    unawaited(_bootstrap());
  }

  Future<void> _bootstrap() async {
    final token = widget.token;
    if (token == null) return;
    await _localRenderer.initialize();
    await _remoteRenderer.initialize();
    if (!mounted) return;
    setState(() => _renderersReady = true);
    await _load();
  }

  Future<void> _load() async {
    final token = widget.token;
    if (token == null) return;
    setState(() => _error = null);
    try {
      final info = await _portal.interview(token);
      if (!mounted) return;
      setState(() => _info = info);
      if (info.status == InterviewStatus.inProgress) {
        await _startCall();
      }
    } on ApiError catch (e) {
      if (!mounted) return;
      setState(() => _error = e.message);
    }
  }

  /// 동의 + 시작 + 연결을 한 번에 밟는다. 지원자에게는 버튼 하나로 보인다.
  Future<void> _consentAndStart() async {
    final token = widget.token;
    if (token == null) return;
    setState(() {
      _sending = true;
      _error = null;
    });
    try {
      // 카메라·마이크 권한을 **함께** 묻는다 — 순차로 물으면 두 번째가 조용히
      // 실패해 마이크가 안 열리는 사고가 있다 (interview_screen.dart §289–303).
      final perms = await [
        Permission.camera,
        Permission.microphone,
      ].request();
      final camOk =
          perms[Permission.camera]?.isGranted ?? false;
      final micOk =
          perms[Permission.microphone]?.isGranted ?? false;
      if (!camOk || !micOk) {
        setState(() {
          _error = '면접을 보려면 카메라와 마이크가 필요합니다. 권한을 허용해 주세요.';
          _sending = false;
        });
        return;
      }

      if (_info?.consentRequired == true) {
        await _portal.consent(token);
      }
      final started = await _portal.start(token);
      if (!mounted) return;
      setState(() {
        _info = started;
        _liveQuestion = started.currentQuestion;
        _liveSeq = started.questionSeq;
      });
      await _startCall();
    } on ApiError catch (e) {
      if (!mounted) return;
      setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _sending = false);
    }
  }

  /// 두 파이프를 연다. **두 번 불러도 안전하다** — 이미 열린 쪽은 건너뛴다.
  Future<void> _startCall() async {
    final token = widget.token;
    if (token == null) return;

    // **WebRTC 먼저**. Android 는 새 AudioRecord 를 열면 앞서 열려 있던 것을
    // 죽인다 — flutter_webrtc 의 PeerConnectionFactory 초기화 안에서 오디오
    // 서브시스템을 건드리므로, 이걸 mic(record) 뒤에 두면 mic 가 조용히 끊긴다
    // (2026-09-09 재현: mic 를 먼저 열었더니 실제로는 아무 조각도 안 도착).
    // 순서를 바꿔 WebRTC 초기화 뒤에 mic 를 열면 마지막 AudioRecord 가 mic 라
    // 조각이 살아 도착한다.
    if (_service == null) {
      final service = widget.serviceOverride ?? InterviewRoomService(token);
      service.addListener(_onServiceChange);
      _service = service;
      if (widget.serviceOverride == null) {
        await service.start();
      }
      _onServiceChange();
    }

    // lie-detection 소켓 — WebRTC 초기화가 끝난 뒤에 mic 를 잡는다.
    // 소켓만 닫힌 채 상태를 다시 읽고 들어온 경우(서버가 이유를 말하고 닫은 뒤
    // `_load`)엔 이쪽만 다시 연다 — 카메라는 그대로.
    if (_liveSocket == null) await _startLive(token);
  }

  Future<void> _startLive(String token) async {
    if (_liveSocket != null) return;
    final socket = LiveInterviewSocket(token);
    _liveSocket = socket;
    _liveEvents = socket.events.listen(_onLive);
    try {
      final pcm = await _mic.start();
      if (!mounted) return;
      _audio = pcm.listen(
        (chunk) {
          // [답변 완료] 직후엔 조각을 무음으로 바꿔 보낸다 (② 폴백)
          final until = _muteUntil;
          final muted = until != null && DateTime.now().isBefore(until);
          _liveSocket?.sendAudio(muted ? Uint8List(chunk.length) : chunk);
        },
        onError: (Object _) {},
        cancelOnError: false,
      );
    } on MicUnavailable catch (e) {
      // 마이크가 막혔다. 서버는 소리를 못 들으니 답변이 넘어가지 않는다 —
      // 지원자에게 사유를 그대로 알린다.
      if (!mounted) return;
      setState(() => _liveNote = e.message);
    }
  }

  /// [답변 완료]. 서버에 끝을 알리고, 번호가 넘어갈 때까지 버튼을 잠근다.
  void _submitAnswer() {
    if (_submitting || _liveSocket == null) return;
    setState(() {
      _submitting = true;
      _submittedSeq = _liveSeq ?? _info?.questionSeq;
      _submittedAt = DateTime.now();
      _listening = false;
      _liveNote = '답변을 저장하고 있어요…';
    });
    _liveSocket?.sendEnd();
    _muteUntil = DateTime.now().add(_muteFor);
    _submitPoll?.cancel();
    _submitPoll = Timer.periodic(_submitPollEvery, (_) => _pollAfterSubmit());
  }

  /// 제출 뒤 REST 로 "번호가 넘어갔나" 를 본다. 소켓이 그 사이 죽어도 여기서
  /// 다음 질문을 잡는다 — 서버는 새 소켓으로 다음 질문을 밀어 주지 못한다.
  Future<void> _pollAfterSubmit() async {
    final token = widget.token;
    if (!mounted || !_submitting || token == null) return;
    try {
      final info = await _portal.interview(token);
      if (!mounted || !_submitting) return;
      final moved = info.status != InterviewStatus.inProgress ||
          (info.questionSeq != null && info.questionSeq != _submittedSeq);
      if (moved) {
        _settleSubmit();
        setState(() {
          _info = info;
          _liveQuestion = info.currentQuestion;
          _liveSeq = info.questionSeq;
          _liveNote = null;
          _listening = false;
        });
        return;
      }
    } on ApiError {
      // 한 번 실패는 다음 주기에 다시 본다
    }
    final since = _submittedAt;
    if (since != null && DateTime.now().difference(since) > _submitGiveUp) {
      _settleSubmit();
      setState(() {
        _liveNote = '저장이 확인되지 않았어요. 다시 답변하거나 [답변 완료] 를 한 번 더 눌러 주세요.';
      });
    }
  }

  /// 제출 대기를 푼다 — 번호가 넘어갔거나, 서버가 retry·done·오류로 답했거나
  void _settleSubmit() {
    _submitPoll?.cancel();
    _submitPoll = null;
    _submitting = false;
    _submittedSeq = null;
    _submittedAt = null;
  }

  Future<void> _stopLive() async {
    _submitPoll?.cancel();
    _submitPoll = null;
    await _audio?.cancel();
    _audio = null;
    await _mic.stop();
    await _liveEvents?.cancel();
    _liveEvents = null;
    await _liveSocket?.close();
    _liveSocket = null;
  }

  /// 소켓만 갈아 끼운다. **마이크·카메라는 그대로 둔다** — 마이크 스트림의
  /// 리스너가 `_liveSocket?.sendAudio` 로 늦게 묶여 있어, 새 소켓이 자리에
  /// 들어오는 순간부터 소리가 그쪽으로 간다.
  Future<void> _reconnect() async {
    final token = widget.token;
    if (!mounted || token == null) return;
    _retries += 1;
    setState(() {
      _listening = false;
      _liveNote = '연결이 끊겨 다시 잇는 중… ($_retries/$_retryMax)';
    });

    // 치우는 것을 기다리지 않는다 — 자리를 먼저 비우고 닫히는 건 알아서 닫히게
    final old = _liveSocket;
    final events = _liveEvents;
    _liveSocket = null;
    _liveEvents = null;
    events?.cancel().ignore();
    old?.close().ignore();

    // 워커가 다시 뜨는 데 몇 초가 걸린다. 1·2·3…초로 늘려 가며 기다린다
    await Future<void>.delayed(Duration(seconds: _retries));
    if (!mounted || _liveSocket != null) return;

    final socket = LiveInterviewSocket(token);
    _liveSocket = socket;
    _liveEvents = socket.events.listen(_onLive);
  }

  void _onLive(InterviewEvent event) {
    if (!mounted) return;
    switch (event) {
      case InterviewQuestion(:final text, :final seq):
        // 재접속 직후 서버는 "아직 답 없는 질문" 을 다시 보낸다. 방금 [답변 완료]
        // 한 번호가 그대로 오면 전사가 아직 도는 중인 것 — 화면을 되돌리지 않고
        // REST 폴링이 번호가 넘어가는 것을 잡게 둔다.
        if (_submitting && seq != null && seq == _submittedSeq) {
          setState(() => _retries = 0);
          return;
        }
        _settleSubmit();
        setState(() {
          _liveQuestion = text;
          _liveSeq = seq;
          _liveNote = null;
          _listening = false;
          // 질문이 왔다 = 잘 붙었다. 다음 사고를 위해 횟수를 되돌린다
          _retries = 0;
        });
      case InterviewListening():
        // 서버가 말을 듣기 시작한 순간. **화면에 보여야** 지원자가
        // "내 소리가 서버에 닿는가" 를 안다 — 마이크가 멀어 안 잡히면
        // 이 배지가 안 뜬다는 것으로 알아채고 폰을 가까이 든다.
        setState(() {
          _listening = true;
          _liveNote = null;
        });
      case InterviewProcessing():
        setState(() {
          _listening = false;
          _liveNote = '답변을 저장하고 있어요…';
        });
      case InterviewRetry(:final message):
        // 서버가 못 들었다고 했다 — 같은 질문에 다시 답해야 하므로 대기를 푼다
        _settleSubmit();
        setState(() {
          _listening = false;
          _liveNote = message;
        });
      case InterviewDone():
        // 서버가 세션을 닫는다. finish REST 는 부르지 않는다 (PROTOCOL.md)
        _settleSubmit();
        setState(() {
          _liveQuestion = null;
          _liveNote = null;
          _listening = false;
        });
        _load();
      case InterviewFailed(:final message, :final retryable):
        // 다시 붙어 볼 만하면 붙는다 — **제출 대기는 유지한다.** 전사 도중 소켓이
        // 죽은 경우가 바로 이것이고, 답변은 서버에 이미 가 있다.
        if (retryable && _retries < _retryMax) {
          _reconnect().ignore();
          return;
        }
        // 서버가 이유를 말하고 닫았다("이미 끝난 면접" 이 흔하다). 상태를 다시
        // 읽어 끝났으면 완료 화면을, 아니면 소켓만 다시 연다(`_startCall`)
        _settleSubmit();
        setState(() {
          _listening = false;
          _error = message;
        });
        _stopLive().then((_) => _load()).ignore();
    }
  }

  void _onServiceChange() {
    if (!mounted) return;
    final s = _service;
    if (s == null) return;
    _localRenderer.srcObject = s.localStream;
    _remoteRenderer.srcObject = s.remoteStream;
    setState(() {});
  }

  Future<void> _finish() async {
    final token = widget.token;
    if (token == null) return;
    setState(() => _sending = true);
    try {
      final done = await _portal.finish(token);
      if (!mounted) return;
      setState(() => _info = done);
    } on ApiError catch (e) {
      if (!mounted) return;
      setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _sending = false);
    }
  }

  @override
  void dispose() {
    _stopLive().ignore();
    _mic.dispose().ignore();
    _service?.removeListener(_onServiceChange);
    _service?.dispose();
    _localRenderer.dispose();
    _remoteRenderer.dispose();
    WakelockPlus.disable().ignore();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (widget.token == null) {
      return const _Message(title: '유효하지 않은 링크',
          body: '안내 메일의 링크를 다시 확인해 주세요.');
    }
    if (!_renderersReady) {
      return const Scaffold(
        backgroundColor: AppColors.bg,
        body: Center(child: CircularProgressIndicator()),
      );
    }

    final info = _info;
    if (info == null && _error == null) {
      return const Scaffold(
        backgroundColor: AppColors.bg,
        body: Center(child: CircularProgressIndicator()),
      );
    }

    return Scaffold(
      backgroundColor: AppColors.bg,
      body: SafeArea(
        child: Column(
          children: [
            // 카메라 — 화면 위쪽 1/3 이 채운다. **본인 얼굴 확인 정도**로 충분
            // 하므로 예전처럼 배경 전체를 차지하지 않는다 — 아래 문구·질문이
            // 잘 읽히는 편이 면접 진행에 도움이 된다.
            AspectRatio(
              aspectRatio: 4 / 3,
              child: Stack(
                children: [
                  Positioned.fill(
                    child: _service?.localStream != null
                        ? RTCVideoView(
                            _localRenderer,
                            mirror: true,
                            objectFit: RTCVideoViewObjectFit
                                .RTCVideoViewObjectFitCover,
                          )
                        : Container(color: AppColors.bgSunken),
                  ),
                  Positioned(
                    top: AppSpace.s3,
                    left: AppSpace.s4,
                    right: AppSpace.s4,
                    child: _TopStatus(
                      phase: _service?.phase,
                      remoteConnected: _service?.remoteStream != null,
                      listening: _listening,
                    ),
                  ),
                ],
              ),
            ),
            // 아래 패널 — 나머지 공간 전부. 문구·질문·버튼이 시원하게 자리 잡는다.
            Expanded(
              child: SingleChildScrollView(
                child: _BottomPanel(
                  info: info,
                  liveQuestion: _liveQuestion,
                  liveSeq: _liveSeq,
                  liveNote: _liveNote,
                  error: _error,
                  sending: _sending,
                  submitting: _submitting,
                  onConsentStart: _consentAndStart,
                  onSubmit: _submitAnswer,
                  onFinish: _finish,
                  onRetry: _load,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _TopStatus extends StatelessWidget {
  const _TopStatus({
    required this.phase,
    required this.remoteConnected,
    required this.listening,
  });

  final RoomPhase? phase;
  final bool remoteConnected;
  final bool listening;

  @override
  Widget build(BuildContext context) {
    String label;
    Color dot;
    // 지원자가 말하고 있는 상태를 **우선해서** 보여 준다. 이 배지가 뜨면
    // 마이크가 서버까지 닿고 있다는 뜻이라 지원자가 확신을 갖고 이야기한다.
    if (listening) {
      label = '듣고 있어요';
      dot = AppColors.accent;
    } else if (phase == null) {
      label = '준비 중';
      dot = AppColors.neutral;
    } else if (remoteConnected) {
      label = '담당자 연결됨 · 면접 중';
      dot = AppColors.ok;
    } else {
      label = phaseLabel(phase!);
      dot = phase == RoomPhase.error ? AppColors.danger : AppColors.warn;
    }
    return Container(
      padding: const EdgeInsets.symmetric(
        horizontal: AppSpace.s3,
        vertical: AppSpace.s2,
      ),
      decoration: BoxDecoration(
        color: const Color(0xB3070B14),
        borderRadius: AppShape.pill,
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            width: 8,
            height: 8,
            margin: const EdgeInsets.only(right: AppSpace.s2),
            decoration: BoxDecoration(shape: BoxShape.circle, color: dot),
          ),
          Text(
            label,
            style: const TextStyle(
              fontFamily: AppType.fontFamily,
              fontSize: AppType.sm,
              color: AppColors.text,
            ),
          ),
        ],
      ),
    );
  }
}

class _BottomPanel extends StatelessWidget {
  const _BottomPanel({
    required this.info,
    required this.liveQuestion,
    required this.liveSeq,
    required this.liveNote,
    required this.error,
    required this.sending,
    required this.submitting,
    required this.onConsentStart,
    required this.onSubmit,
    required this.onFinish,
    required this.onRetry,
  });

  final InterviewPublic? info;
  final String? liveQuestion;
  final int? liveSeq;
  final String? liveNote;
  final String? error;
  final bool sending;
  final bool submitting;
  final VoidCallback onConsentStart;
  final VoidCallback onSubmit;
  final VoidCallback onFinish;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.all(AppSpace.s3),
      padding: const EdgeInsets.all(AppSpace.s4),
      decoration: BoxDecoration(
        color: const Color(0xE60D1322),
        borderRadius: AppShape.card,
        border: Border.all(color: AppColors.borderSoft),
      ),
      child: _content(context),
    );
  }

  Widget _content(BuildContext context) {
    if (error != null) {
      return Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        mainAxisSize: MainAxisSize.min,
        children: [
          _text(error!, AppColors.danger),
          const SizedBox(height: AppSpace.s3),
          _button('다시 시도', onRetry, false),
        ],
      );
    }
    final d = info;
    if (d == null) {
      return const SizedBox(
        height: 40,
        child: Center(child: CircularProgressIndicator()),
      );
    }
    switch (d.status) {
      case InterviewStatus.expired:
        return _text('면접 링크의 유효 기간이 지났습니다. 담당자에게 문의해 주세요.', AppColors.textSub);
      case InterviewStatus.done:
        return _text('${d.applicantName}님, 면접이 완료되었습니다. 참여해 주셔서 감사합니다.',
            AppColors.textSub);
      case InterviewStatus.pending:
        return Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          mainAxisSize: MainAxisSize.min,
          children: [
            _title('${d.applicantName}님, 준비되셨나요?'),
            const SizedBox(height: AppSpace.s2),
            _text(
              '${d.postingTitle} 채용 면접입니다. 시작하면 담당자가 실시간으로 참여합니다. '
              '면접 내용은 채용 검토 목적으로만 활용됩니다.',
              AppColors.textSub,
            ),
            const SizedBox(height: AppSpace.s3),
            _button(sending ? '시작 중…' : '동의하고 면접 시작', onConsentStart, sending),
          ],
        );
      case InterviewStatus.inProgress:
        // 소켓이 준 값이 있으면 그것을 먼저 쓴다 — REST 는 답변 저장 뒤에 새로
        // 부르지 않아 옛 질문이 남는다. 소켓은 저장이 끝나면 다음 질문을 즉시 보낸다
        final seq = liveSeq ?? d.questionSeq;
        final question = liveQuestion ?? d.currentQuestion;
        return Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          mainAxisSize: MainAxisSize.min,
          children: [
            if (seq != null)
              Padding(
                padding: const EdgeInsets.only(bottom: AppSpace.s1),
                child: Text(
                  '질문 $seq',
                  style: const TextStyle(
                    fontFamily: AppType.fontFamily,
                    fontSize: AppType.caption,
                    color: AppColors.accentText,
                    fontWeight: AppType.wSemiBold,
                  ),
                ),
              ),
            _title(question ?? '질문을 준비하는 중…'),
            if (liveNote != null) ...[
              const SizedBox(height: AppSpace.s3),
              _text(liveNote!, AppColors.warnText),
            ],
            const SizedBox(height: AppSpace.s4),
            // 주 동작 = 답변 완료. 종료는 되돌릴 수 없는 쪽이라 2차 버튼으로 둔다
            _button(submitting ? '저장 중…' : '답변 완료', onSubmit,
                submitting || question == null),
            const SizedBox(height: AppSpace.s2),
            _button(sending ? '종료 중…' : '면접 종료', onFinish, sending,
                secondary: true),
          ],
        );
    }
  }

  // 카메라 축소 후 여백이 크게 남는다 — 문구를 예전 h2 보다 한 단계씩 키운다.
  // 질문은 특히 크게 (display 급) — 지원자가 카메라와 화면을 오가며 봐야 한다.
  Widget _title(String s) => Text(
    s,
    style: const TextStyle(
      fontFamily: AppType.fontFamily,
      fontSize: AppType.display,
      fontWeight: AppType.wSemiBold,
      color: AppColors.text,
      height: 1.35,
    ),
  );

  Widget _text(String s, Color c) => Text(
    s,
    style: TextStyle(
      fontFamily: AppType.fontFamily,
      fontSize: AppType.body + 2,
      color: c,
      height: 1.55,
    ),
  );

  Widget _button(String label, VoidCallback onPressed, bool disabled,
      {bool secondary = false}) {
    return FilledButton(
      onPressed: disabled ? null : onPressed,
      style: FilledButton.styleFrom(
        minimumSize: const Size.fromHeight(AppLayout.minTouchTarget),
        backgroundColor:
            secondary ? AppColors.bgSunken : AppColors.accentFill,
        foregroundColor: secondary ? AppColors.text : AppColors.onAccent,
        shape: const RoundedRectangleBorder(borderRadius: AppShape.ctl),
        textStyle: const TextStyle(
          fontFamily: AppType.fontFamily,
          fontSize: AppType.body,
          fontWeight: AppType.wSemiBold,
        ),
      ),
      child: Text(label),
    );
  }
}

class _Message extends StatelessWidget {
  const _Message({required this.title, required this.body});

  final String title;
  final String body;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.bg,
      body: SafeArea(
        child: Center(
          child: Padding(
            padding: const EdgeInsets.all(AppSpace.s5),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(
                  title,
                  textAlign: TextAlign.center,
                  style: const TextStyle(
                    fontFamily: AppType.fontFamily,
                    fontSize: AppType.h1,
                    fontWeight: AppType.wSemiBold,
                    color: AppColors.text,
                  ),
                ),
                const SizedBox(height: AppSpace.s3),
                Text(
                  body,
                  textAlign: TextAlign.center,
                  style: const TextStyle(
                    fontFamily: AppType.fontFamily,
                    fontSize: AppType.body,
                    color: AppColors.textSub,
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
