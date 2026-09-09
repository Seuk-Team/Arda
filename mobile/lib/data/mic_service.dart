/// 면접용 마이크 — 말소리를 **16kHz·16-bit·mono PCM** 으로 흘린다 (2026-09-09).
///
/// ## 왜 녹음 파일이 아니라 PCM 인가
///
/// 지원자가 "제출" 을 누르지 않는다. **서버가 소리를 듣고 말이 끝난 것을
/// 판정한다**(PROTOCOL.md). 그러려면 소리가 실시간으로 흘러가야 하는데,
/// 녹음 파일(m4a·webm)은 서버가 매번 디코딩해야 하고 그 시간이 실시간 예산을
/// 먹는다. PCM 이면 서버가 산술만으로 크기를 잰다.
///
/// ## 왜 50ms 로 다시 자르는가
///
/// `record` 가 주는 조각 크기는 기기가 정한다 — 안드로이드는 `AudioRecord` 의
/// 내부 버퍼 크기를 따라 제각각이다. 그런데 서버의 소음 판정은 **조각 수로
/// 시간을 센다**: 최근 40조각(=2초)의 하위 백분위로 바닥값을 잡고, 갇혔을 때
/// 조각마다 0.4%씩 올려 빠져나온다(`interview_ws.py`). 조각이 크면 그 창이
/// 실제로는 몇 초가 되어 판정이 굼떠지고, 작으면 반대로 요동친다.
///
/// **그래서 기기가 뭘 주든 여기서 1600바이트(50ms)로 맞춰 보낸다.** 웹이
/// AudioWorklet 에서 하는 일과 같은 것을 앱에서는 여기서 한다.
library;

import 'dart:async';
import 'dart:typed_data';

import 'package:flutter/foundation.dart';
import 'package:record/record.dart';

/// 서버가 기대하는 값 (PROTOCOL.md). **바꾸면 서버가 못 알아듣는다.**
const int micSampleRate = 16000;

/// 한 조각의 길이. 서버가 이 단위로 말/침묵을 가른다
const int micChunkMs = 50;

/// 16kHz · 16-bit(2바이트) · mono 에서 50ms = 800표본 = 1600바이트
const int micChunkBytes = micSampleRate * 2 * micChunkMs ~/ 1000;

/// 마이크를 못 쓴다. **사유를 뭉치지 않는다** — 지원자가 할 수 있는 일이 다르다
/// (권한은 다시 허용하면 되지만 기기에 마이크가 없으면 방법이 없다).
class MicUnavailable implements Exception {
  const MicUnavailable(this.message, {this.permanent = false});

  /// 지원자에게 그대로 보여 줄 한 줄
  final String message;

  /// 설정 화면으로 보내야 하는가 (영구 거부)
  final bool permanent;

  @override
  String toString() => 'MicUnavailable($message)';
}

/// 마이크 한 대. 화면은 [AudioRecorder] 를 직접 만들지 않고 이것만 안다 —
/// [CameraService] 와 같은 이유다(실기기 없이 테스트가 돌아야 한다).
abstract class MicService {
  /// 소리를 흘리기 시작한다. 조각은 **정확히 [micChunkBytes]** 다.
  ///
  /// 권한이 없거나 마이크를 못 열면 [MicUnavailable] 을 던진다.
  Future<Stream<Uint8List>> start();

  /// 놓아 준다. **안 부르면 화면을 나가도 녹음 표시등이 켜져 있다.**
  Future<void> stop();

  /// 두 번 다시 안 쓸 때. [stop] 을 포함한다
  Future<void> dispose();
}

/// 진짜 마이크.
class DeviceMicService implements MicService {
  final AudioRecorder _recorder = AudioRecorder();

  StreamSubscription<Uint8List>? _sub;
  StreamController<Uint8List>? _out;

  /// 아직 50ms 를 못 채운 나머지. 다음 조각 앞에 붙는다.
  ///
  /// **`copy: false` 를 쓰지 않는다.** 그러면 `record` 가 준 버퍼를 그대로 들고
  /// 있게 되는데, 플러그인이 그 버퍼를 재사용하면 이미 보낸 소리가 조용히 바뀐다.
  final BytesBuilder _pending = BytesBuilder();

  @override
  Future<Stream<Uint8List>> start() async {
    await stop();

    final bool granted;
    try {
      granted = await _recorder.hasPermission();
    } on Exception catch (e) {
      if (kDebugMode) debugPrint('[mic] 권한 확인 실패: $e');
      throw const MicUnavailable('마이크를 열지 못했습니다. 잠시 후 다시 시도해 주세요.');
    }
    if (!granted) {
      // `record` 는 "이번에 거부" 와 "다시 묻지 않음" 을 구별해 주지 않는다.
      // 카메라 권한과 함께 묻고 있어(CameraService) 여기까지 왔다는 것은 이미
      // 한 번 거부당한 뒤다 — 설정으로 보내는 안내가 맞다.
      throw const MicUnavailable(
        '마이크 권한이 꺼져 있습니다. 설정에서 허용한 뒤 다시 시도해 주세요.',
        permanent: true,
      );
    }

    final Stream<Uint8List> raw;
    try {
      raw = await _recorder.startStream(
        const RecordConfig(
          encoder: AudioEncoder.pcm16bits,
          sampleRate: micSampleRate,
          numChannels: 1,
          // **브라우저 기본값에 맞춘다.** 소연님이 소음 기준을 잡을 때 본 소리가
          // `getUserMedia` 를 거친 것이고(에코 제거·잡음 억제·자동 이득이 기본으로
          // 켜져 있다), 앱만 날것을 보내면 같은 방에서도 바닥값이 다르게 잡힌다.
          echoCancel: true,
          noiseSuppress: true,
          autoGain: true,
        ),
      );
    } on Exception catch (e) {
      if (kDebugMode) debugPrint('[mic] 열지 못했다: $e');
      throw const MicUnavailable('마이크를 열지 못했습니다. 다른 앱이 쓰고 있는지 확인해 주세요.');
    }

    final out = StreamController<Uint8List>(sync: true);
    _out = out;
    _sub = raw.listen(
      (chunk) => _emit(out, chunk),
      onError: (Object e, StackTrace s) => out.addError(e, s),
      onDone: out.close,
      cancelOnError: false,
    );
    return out.stream;
  }

  /// 들어온 것을 50ms 단위로 잘라 내보낸다. 남는 꼬리는 다음 것과 이어 붙인다 —
  /// **버리면 말 끝의 마지막 조각이 사라진다.**
  void _emit(StreamController<Uint8List> out, Uint8List chunk) {
    _pending.add(chunk);
    if (_pending.length < micChunkBytes) return;

    // `takeBytes` 가 준 버퍼는 이제 우리 것이고 아무도 덮어쓰지 않는다.
    // 그래서 복사 없이 뷰로 잘라 보내도 안전하다
    final all = _pending.takeBytes();
    var offset = 0;
    while (all.length - offset >= micChunkBytes) {
      out.add(Uint8List.sublistView(all, offset, offset + micChunkBytes));
      offset += micChunkBytes;
    }
    if (offset < all.length) _pending.add(Uint8List.sublistView(all, offset));
  }

  @override
  Future<void> stop() async {
    await _sub?.cancel();
    _sub = null;
    _pending.clear();
    try {
      if (await _recorder.isRecording()) await _recorder.stop();
    } on Exception catch (e) {
      // 이미 멈춘 것을 또 멈추는 것은 실패해도 상관없다
      if (kDebugMode) debugPrint('[mic] 멈추다 무시한 오류: $e');
    }
    await _out?.close();
    _out = null;
  }

  @override
  Future<void> dispose() async {
    await stop();
    await _recorder.dispose();
  }
}
