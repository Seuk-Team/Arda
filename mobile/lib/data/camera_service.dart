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

import 'package:camera/camera.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
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
      final controller = CameraController(
        front,
        ResolutionPreset.medium,
        enableAudio: true,
      );
      await controller.initialize();
      _controller = controller;
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
    if (controller == null) return;
    try {
      await controller.dispose();
    } on Exception {
      // 이미 죽은 컨트롤러를 닫는 것은 실패해도 상관없다
    }
  }

  @override
  Future<void> openSettings() => openAppSettings();

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

/// 상태별 안내 한 줄. **지원자가 다음에 할 일**을 적는다 — 사유만 적으면
/// 화면을 보고도 무엇을 눌러야 할지 모른다
String _messageFor(CameraStatus status) => switch (status) {
  CameraStatus.denied => '면접을 보려면 카메라와 마이크가 필요합니다. 권한을 허용해 주세요.',
  CameraStatus.deniedForever => '카메라·마이크 권한이 꺼져 있습니다. 설정에서 허용한 뒤 다시 시도해 주세요.',
  CameraStatus.unavailable => '이 기기에서 카메라를 찾지 못했습니다.',
  _ => '카메라를 열지 못했습니다. 잠시 후 다시 시도해 주세요.',
};
