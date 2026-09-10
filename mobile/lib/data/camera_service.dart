/// 면접용 카메라 한 대 (2026-09-08).
///
/// 화면은 [CameraController] 를 직접 만들지 않고 이 인터페이스만 안다.
/// **이유는 테스트다.** `camera` 플러그인은 실기기가 있어야 돌아서, 위젯
/// 테스트에서 컨트롤러를 만들면 플랫폼 채널이 없어 그 자리에서 죽는다.
/// 한 겹 감싸 두면 권한 거부·카메라 없음·중간에 끊김 세 상태를 테스트가 볼 수
/// 있다 — 안 그러면 이 화면만 테스트가 한 줄도 안 붙는다.
///
/// ## 왜 [ChangeNotifier] 인가
///
/// 카메라는 화면이 부르지 않아도 상태가 바뀐다: 전화가 오면 안드로이드가
/// 카메라를 뺏고, 사용자가 설정에서 권한을 끄면 다음 순간 죽는다. 화면이
/// 물어보는 구조로는 그 순간을 놓친다.
library;

import 'dart:async';

import 'package:camera/camera.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:image/image.dart' as img;
import 'package:permission_handler/permission_handler.dart';

/// 카메라가 지금 어떤가.
///
/// 실패를 하나로 뭉치지 않는다 — **지원자가 할 수 있는 일이 다르기 때문이다.**
/// 한 번 거부한 것은 다시 물으면 되지만, 영구 거부는 설정으로 가야 하고,
/// 카메라가 없는 기기는 아무것도 할 수 없다.
enum CameraStatus {
  /// 아직 안 켰다
  idle,

  /// 권한을 묻는 중이거나 여는 중
  starting,

  /// 켜졌다 — 미리보기가 나온다
  live,

  /// 이번에 거부했다. 다시 물을 수 있다
  denied,

  /// 다시 묻지 않음으로 거부했다. **설정으로 보내야 한다**
  deniedForever,

  /// 카메라가 없는 기기
  unavailable,

  /// 열다가 깨졌거나, 켜져 있다가 끊겼다
  failed,
}

abstract class CameraService extends ChangeNotifier {
  CameraStatus get status;

  /// 실패 사유 한 줄. 없으면 null
  String? get message;

  /// 권한을 묻고 카메라를 연다. 이미 켜져 있으면 아무것도 안 한다
  Future<void> start();

  /// 놓아 준다. **안 부르면 화면을 나가도 카메라가 잡혀 있다** —
  /// 상단 표시등이 계속 켜져 있고, 다른 앱이 카메라를 못 쓴다
  Future<void> stop();

  /// 앱 설정 화면 열기 ([CameraStatus.deniedForever] 일 때만 쓸모 있다)
  Future<void> openSettings();

  /// 얼굴 분석용 프레임 (JPEG). **미리보기와 별개다** — 미리보기는 화면에
  /// 그리는 것이고 이것은 서버로 보내는 것이다.
  ///
  /// 듣기 시작하면 흐르고, 구독을 끊으면 멈춘다. 카메라가 안 켜져 있으면
  /// 아무것도 안 나온다 — **면접이 그것 때문에 멈추지는 않는다**(얼굴 분석은
  /// 곁들이고, 질문·답변은 소리만으로 돈다).
  Stream<Uint8List> frames();

  /// 지금까지 서버로 보낸 얼굴 장수. 0 이면 **얼굴이 아예 안 가고 있다**
  int get framesSent;

  /// 미리보기. 켜져 있지 않으면 빈 것을 준다 — 부르는 쪽이 상태로 갈라
  /// 그리지만, 여기서도 안전하게 둔다
  Widget buildPreview();
}

/// 진짜 카메라.
class DeviceCameraService extends CameraService {
  CameraController? _controller;
  CameraStatus _status = CameraStatus.idle;
  String? _message;

  /// 두 번 겹쳐 들어오는 것을 막는다 — 화면 복귀와 사용자 탭이 같이 오면
  /// 컨트롤러를 두 개 만들어 하나가 영영 안 닫힌다
  bool _busy = false;

  @override
  CameraStatus get status => _status;

  @override
  String? get message => _message;

  void _set(CameraStatus next, [String? message]) {
    if (_status == next && _message == message) return;
    _status = next;
    _message = message;
    notifyListeners();
  }

  @override
  Future<void> start() async {
    if (_busy || _status == CameraStatus.live) return;
    _busy = true;
    _set(CameraStatus.starting);
    try {
      // 카메라와 마이크를 같이 묻는다 — 면접은 얼굴과 말이 같이 필요하고,
      // 나눠 물으면 권한 창이 두 번 떠서 두 번째를 그냥 닫아 버린다
      final granted = await _request();
      if (granted != null) {
        _set(granted, _messageFor(granted));
        return;
      }

      final cameras = await availableCameras();
      if (cameras.isEmpty) {
        _set(CameraStatus.unavailable, _messageFor(CameraStatus.unavailable));
        return;
      }

      // 앞 카메라. 없으면 첫 번째 — 면접이니 얼굴이 보여야 하지만, 앞
      // 카메라가 없다고 면접을 못 보게 할 이유는 없다
      final front = cameras.firstWhere(
        (c) => c.lensDirection == CameraLensDirection.front,
        orElse: () => cameras.first,
      );

      // medium(720p 안팎). 미리보기와 답변 녹음에 충분하고, high 로 올리면
      // 낮은 기기에서 열다가 실패하거나 발열이 는다
      //
      // **소리는 여기서 안 받는다**(2026-09-09). 면접 소리는 [MicService] 가
      // 16kHz PCM 으로 따로 흘리는데, 카메라가 마이크를 같이 잡으면 안드로이드가
      // 둘 중 하나에게만 준다 — 그러면 말이 서버까지 안 간다.
      //
      // `yuv420` 을 못 박는 이유: 안드로이드 기본은 yuv420 이지만 iOS 는
      // bgra8888 이라, 안 정하면 [frames] 의 첫 판이 기기마다 다른 뜻이 된다.
      final controller = CameraController(
        front,
        ResolutionPreset.medium,
        enableAudio: false,
        imageFormatGroup: ImageFormatGroup.yuv420,
      );
      await controller.initialize();
      _controller = controller;
      // `sensorOrientation` 은 "이만큼 시계 방향으로 돌리면 똑바로 선다" 는 값이다
      // (앞 카메라는 보통 270). 미리보기가 아니라 **보내는 프레임**에 그대로 적용한다.
      _quarterTurns = (front.sensorOrientation ~/ 90) % 4;
      _set(CameraStatus.live);
    } on CameraException catch (e) {
      await _release();
      _set(
        CameraStatus.failed,
        e.description ?? _messageFor(CameraStatus.failed),
      );
    } on Exception catch (e) {
      await _release();
      if (kDebugMode) debugPrint('[camera] 열지 못했다: $e');
      _set(CameraStatus.failed, _messageFor(CameraStatus.failed));
    } finally {
      _busy = false;
    }
  }

  /// 권한 결과. 통과하면 null, 막히면 그 상태를 준다
  Future<CameraStatus?> _request() async {
    final results = await [Permission.camera, Permission.microphone].request();
    final blocked = results.values.where((s) => !s.isGranted);
    if (blocked.isEmpty) return null;
    return blocked.any((s) => s.isPermanentlyDenied)
        ? CameraStatus.deniedForever
        : CameraStatus.denied;
  }

  @override
  Future<void> stop() async {
    await _release();
    _set(CameraStatus.idle);
  }

  Future<void> _release() async {
    final controller = _controller;
    _controller = null;
    // 프레임을 받던 중이면 먼저 끊는다 — 컨트롤러를 닫는 도중에 프레임이 들어오면
    // 플러그인이 죽은 컨트롤러를 부른다
    _frames?.close().ignore();
    _frames = null;
    if (controller == null) return;
    try {
      if (controller.value.isStreamingImages) await controller.stopImageStream();
      await controller.dispose();
    } on Exception {
      // 이미 죽은 컨트롤러를 닫는 것은 실패해도 상관없다
    }
  }

  @override
  Future<void> openSettings() => openAppSettings();

  // ── 얼굴 분석용 프레임 ────────────────────────────────────────
  //
  // 서버는 초당 5장을 권한다(PROTOCOL.md). 카메라는 초당 30장을 주므로 그대로
  // 다 바꾸면 폰이 그 일만 한다 — 시간으로 걸러 보낸다.
  //
  // **초당 5장으로는 모자랐다** (2026-09-09 실측). 서버는 받은 것의 3장에 1장만
  // 분석하고(`FRAME_STRIDE`), 판정에는 4초 창에 얼굴 5장이 필요하다. 5장/초로
  // 보내면 분석되는 것이 1.7장/초 — 창에 6~7장이라 아슬아슬한데, 폰에서 변환이
  // 밀리면 곧바로 5장 밑으로 떨어진다. 실제로 51번 판정 시도가 **전부** 실패했다.
  static const Duration _frameEvery = Duration(milliseconds: 100);

  /// 보낼 그림의 크기. **카메라 해상도 그대로 보내지 않는다** — 얼굴 특징을
  /// 잡는 데 720p 가 필요 없고, 크면 변환이 그만큼 느려진다. 웹이 480×360 을
  /// 보내므로 그 언저리로 맞춘다.
  static const int _sendWidth = 320;

  /// 보내기 전에 돌릴 각도 (90° 단위, 시계 방향).
  ///
  /// **스트림 프레임은 센서 방향 그대로 온다.** 폰을 세로로 들면 프레임은 90°
  /// 누운 채로 나오는데, [CameraPreview] 는 알아서 돌려 주므로 화면만 보면
  /// 멀쩡해 보인다. 서버로 가는 것은 안 돌아간 원본이다.
  ///
  /// **누운 얼굴은 MediaPipe 가 못 찾는다.** 2026-09-10 실측에서 앱 면접 두 번
  /// 동안 판정이 169번 시도돼 **0번 성공**했다(`/ai/health` 의 `live.ok`).
  /// 같은 서버가 웹(채용자 화면)에서는 판정을 냈는데, 그쪽은 `<video>` 를
  /// canvas 로 떠서 방향이 똑바르다. #133 이 초당 장수를 5→10 으로 올리고도
  /// 안 고쳐진 이유가 이것이다 — 장수가 아니라 방향이 문제였다.
  int _quarterTurns = 0;

  StreamController<Uint8List>? _frames;

  DateTime _lastFrame = DateTime.fromMillisecondsSinceEpoch(0);

  /// 지금까지 보낸 장수. **화면이 보여 준다** — 얼굴이 안 가고 있는지를
  /// 지원자도 담당자도 알 길이 없었다(2026-09-09)
  int _framesSent = 0;

  @override
  int get framesSent => _framesSent;

  @override
  Stream<Uint8List> frames() {
    final out = StreamController<Uint8List>();
    out.onListen = () => _startFrames(out);
    out.onCancel = () => _stopFrames(out);
    return out.stream;
  }

  Future<void> _startFrames(StreamController<Uint8List> out) async {
    final controller = _controller;
    if (controller == null || !controller.value.isInitialized) {
      // 카메라가 아직 안 열렸다. **오류로 만들지 않는다** — 소리만으로도 면접은 돈다
      await out.close();
      return;
    }
    _frames = out;
    if (controller.value.isStreamingImages) return;
    try {
      await controller.startImageStream(_onImage);
    } on CameraException catch (e) {
      if (kDebugMode) debugPrint('[camera] 프레임 스트림 실패: $e');
      _frames = null;
      await out.close();
    }
  }

  Future<void> _stopFrames(StreamController<Uint8List> out) async {
    if (!identical(_frames, out)) return;
    _frames = null;
    final controller = _controller;
    if (controller == null || !controller.value.isStreamingImages) return;
    try {
      await controller.stopImageStream();
    } on CameraException {
      // 이미 멈춘 것을 또 멈추는 것은 실패해도 상관없다
    }
  }

  void _onImage(CameraImage image) {
    final out = _frames;
    if (out == null || out.isClosed) return;
    final now = DateTime.now();
    if (now.difference(_lastFrame) < _frameEvery) return;
    _lastFrame = now;

    final plane = image.planes.first;
    try {
      // **줄이면서 바로 바꾼다.** 예전에는 원본 크기로 딴 일꾼(Isolate)에게
      // 시켰는데, 일꾼을 프레임마다 새로 만드는 값이 변환 자체만큼 들었다
      // (실측 33ms vs 34.6ms — 얻는 것이 없었다). 320×240 으로 줄이면 10ms 라
      // 이 자리에서 해도 미리보기가 안 밀린다.
      final jpeg = _grayJpeg(
        plane.bytes,
        image.width,
        image.height,
        plane.bytesPerRow,
        _quarterTurns,
      );
      _framesSent++;
      if (!out.isClosed) out.add(jpeg);
    } on Exception catch (e) {
      // 한 장 실패는 넘어간다. 얼굴 분석은 곁들이지 면접의 조건이 아니다
      if (kDebugMode) debugPrint('[camera] 프레임 변환 실패: $e');
    }
  }

  @override
  Widget buildPreview() {
    final controller = _controller;
    if (controller == null || !controller.value.isInitialized) {
      return const SizedBox.shrink();
    }
    return CameraPreview(controller);
  }

  @override
  void dispose() {
    // 화면이 사라질 때 마지막 그물. `stop()` 을 부르지 않고 나간 경로가
    // 있어도 여기서 놓아 준다. dispose 는 기다릴 수 없어 흘려보낸다
    _release().ignore();
    super.dispose();
  }
}

/// 밝기 평면(Y) 하나로 흑백 JPEG 을 만든다.
///
/// **색을 버린다.** 서버가 프레임에서 뽑는 것은 눈 뜬 정도·깜빡임·머리 움직임
/// 같은 모양이라 색이 필요 없다(`feature_extractor.face_row`). 색까지 옮기려면
/// yuv420 의 두 평면을 섞어야 하는데, 폰에서 그 계산이 프레임마다 수십 ms 다.
///
/// `rowStride` 를 그대로 넘긴다 — 카메라는 줄 끝에 여백을 넣어 주는 일이 잦고,
/// 그것을 무시하면 그림이 비스듬히 밀린다.
Uint8List _grayJpeg(
  Uint8List luma,
  int width,
  int height,
  int rowStride,
  int quarterTurns,
) {
  // **줄이면서 동시에 돌린다.** 줄인 뒤 다시 돌리면 그림을 두 번 만드는 값이
  // 든다. 읽어 오는 자리만 바꾸면 도는 값은 공짜다.
  final sideways = quarterTurns.isOdd;

  // 돌린 뒤 **가로가 될 쪽**을 기준으로 줄인다. 세로로 세울 그림을 원본 가로
  // (1280) 기준으로 줄이면 결과가 180px 폭이 되어 얼굴이 너무 작아진다.
  final source = sideways ? height : width;
  final step = (source / DeviceCameraService._sendWidth).ceil().clamp(1, 8);
  final w = width ~/ step;
  final h = height ~/ step;

  final outW = sideways ? h : w;
  final outH = sideways ? w : h;
  final small = Uint8List(outW * outH);

  // 한 칸 옆·한 줄 아래로 갈 때 원본에서 건너뛸 바이트 수
  final rowBytes = step * rowStride;
  final colBytes = step;

  var o = 0;
  for (var y = 0; y < outH; y++) {
    // 출력 한 줄은 원본에서도 직선이다 — 시작점과 증분만 정하면 안쪽 반복은
    // 방향을 몰라도 된다 (픽셀마다 분기하면 그 분기가 변환값을 다시 먹는다)
    final (int base, int inc) = switch (quarterTurns) {
      1 => ((h - 1) * rowBytes + y * colBytes, -rowBytes), // 90° 시계
      2 => ((h - 1 - y) * rowBytes + (w - 1) * colBytes, -colBytes), // 180°
      3 => ((w - 1 - y) * colBytes, rowBytes), // 270° 시계
      _ => (y * rowBytes, colBytes), // 안 돌림
    };
    var p = base;
    for (var x = 0; x < outW; x++) {
      small[o++] = luma[p];
      p += inc;
    }
  }

  final image = img.Image.fromBytes(
    width: outW,
    height: outH,
    bytes: small.buffer,
    numChannels: 1,
  );
  // 60 — 얼굴 특징은 남고 크기는 초당 10장을 보낼 만하다
  return img.encodeJpg(image, quality: 60);
}

/// 상태별 안내 한 줄. **지원자가 다음에 할 일**을 적는다 — 사유만 적으면
/// 화면을 보고도 무엇을 눌러야 할지 모른다
String _messageFor(CameraStatus status) => switch (status) {
  CameraStatus.denied => '면접을 보려면 카메라와 마이크가 필요합니다. 권한을 허용해 주세요.',
  CameraStatus.deniedForever => '카메라·마이크 권한이 꺼져 있습니다. 설정에서 허용한 뒤 다시 시도해 주세요.',
  CameraStatus.unavailable => '이 기기에서 카메라를 찾지 못했습니다.',
  _ => '카메라를 열지 못했습니다. 잠시 후 다시 시도해 주세요.',
};
