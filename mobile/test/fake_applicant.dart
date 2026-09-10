// 지원자 갈래용 가짜 (2026-09-08).
//
// 저장소도 카메라도 플랫폼 채널을 타서 위젯 테스트에서 진짜를 만들면 그 자리에서
// 죽는다. 화면이 인터페이스만 알게 해 두고 여기서 갈아끼운다.

import 'dart:async';
import 'dart:typed_data';

import 'package:arda/api/api_error.dart';
import 'package:arda/data/applicant_portal_repository.dart';
import 'package:arda/data/camera_service.dart';
import 'package:arda/data/interview_socket.dart';
import 'package:arda/data/mic_service.dart';
import 'package:arda/models/applicant_extra.dart';
import 'package:arda/models/applicant_me.dart';
import 'package:arda/models/applicant_portal.dart';
import 'package:flutter/material.dart';

/// 지원자 API. 무엇을 돌려줄지 테스트가 정해 준다
class FakeApplicantPortalRepository implements ApplicantPortalRepository {
  FakeApplicantPortalRepository({
    this.me_,
    Map<String, InterviewPublic>? interviews,
    Map<String, AptitudePublic>? aptitudes,
    Map<String, SchedulePublic>? schedules,
    this.arAnswer = '아르 답변입니다.',
    this.loginError,
    this.meError,
    this.token,
  }) : interviews = {...?interviews},
       aptitudes = {...?aptitudes},
       schedules = {...?schedules};

  /// `GET /applicant/me` 가 줄 것. 안 주면 [meError] 나 빈 목록이다
  final ApplicantMe? me_;

  final Map<String, InterviewPublic> interviews;
  final Map<String, AptitudePublic> aptitudes;
  final Map<String, SchedulePublic> schedules;
  final String arAnswer;

  /// 로그인이 이걸로 실패한다. 서버는 401(틀림)·429(잠김) 를 준다
  final ApiError? loginError;

  /// `/applicant/me` 가 이걸로 실패한다. 만료면 [AuthExpired] 다
  final ApiError? meError;

  /// 저장돼 있는 토큰. 로그인에 성공하면 채워진다
  String? token;

  /// 무엇을 불렀는지 — 순서까지 본다
  final calls = <String>[];

  @override
  Future<void> login({required String email, required String birthdate}) async {
    calls.add('login:$email:$birthdate');
    if (loginError != null) throw loginError!;
    token = 'fake-applicant-token';
  }

  @override
  Future<ApplicantMe> me() async {
    calls.add('me');
    if (meError != null) throw meError!;
    return me_ ?? const ApplicantMe(email: '', name: '');
  }

  @override
  Future<void> logout() async {
    calls.add('logout');
    token = null;
  }

  @override
  Future<bool> hasToken() async => token != null;

  @override
  Future<InterviewPublic> interview(String token) async {
    calls.add('interview:$token');
    return _need(token);
  }

  @override
  Future<InterviewPublic> consent(String token) async {
    calls.add('consent:$token');
    return _replace(token, (i) => _copy(i, consentRequired: false));
  }

  @override
  Future<InterviewPublic> start(String token) async {
    calls.add('start:$token');
    return _replace(
      token,
      (i) => _copy(
        i,
        status: InterviewStatus.inProgress,
        currentQuestion: '자기소개를 해 주세요.',
        questionSeq: 1,
      ),
    );
  }

  @override
  Future<InterviewPublic> answer(String token, String transcript) async {
    calls.add('answer:$token:$transcript');
    final seq = (_need(token).questionSeq ?? 0) + 1;
    return _replace(
      token,
      (i) => _copy(
        i,
        questionSeq: seq,
        currentQuestion: '$seq번째 질문입니다.',
        pacing: '조금 더 자세히 말씀해 주셔도 좋습니다.',
      ),
    );
  }

  @override
  Future<InterviewPublic> finish(String token) async {
    calls.add('finish:$token');
    return _replace(
      token,
      (i) => _copy(i, status: InterviewStatus.done, currentQuestion: null),
    );
  }

  @override
  Future<AptitudePublic> aptitude(String token) async {
    calls.add('aptitude:$token');
    final found = aptitudes[token];
    if (found == null) throw const ServerError(404, '유효하지 않은 링크입니다');
    return found;
  }

  @override
  Future<AptitudePublic> submitAptitude(
    String token,
    Map<String, int> answers,
  ) async {
    calls.add('submitAptitude:$token:${answers.length}');
    final base = aptitudes[token];
    if (base == null) throw const ServerError(404, '유효하지 않은 링크입니다');
    final next = AptitudePublic(
      token: token,
      status: AptitudeStatus.submitted,
      applicantName: base.applicantName,
      postingTitle: base.postingTitle,
    );
    aptitudes[token] = next;
    return next;
  }

  @override
  Future<SchedulePublic> schedule(String token) async {
    calls.add('schedule:$token');
    final found = schedules[token];
    if (found == null) throw const ServerError(404, '유효하지 않은 링크입니다');
    return found;
  }

  @override
  Future<SchedulePublic> confirmSlot(String token, int slotId) async {
    calls.add('confirmSlot:$token:$slotId');
    final base = schedules[token];
    if (base == null) throw const ServerError(404, '유효하지 않은 링크입니다');
    final next = SchedulePublic(
      token: token,
      status: ScheduleStatus.confirmed,
      applicantName: base.applicantName,
      postingTitle: base.postingTitle,
      currentStage: base.currentStage,
      slots: base.slots,
      confirmedSlot: base.slots.firstWhere((s) => s.id == slotId),
    );
    schedules[token] = next;
    return next;
  }

  @override
  Future<String> askAr(String token, String question) async {
    calls.add('askAr:$token:$question');
    return arAnswer;
  }

  InterviewPublic _need(String token) {
    final found = interviews[token];
    if (found == null) throw const ServerError(404, '유효하지 않은 링크입니다');
    return found;
  }

  InterviewPublic _replace(
    String token,
    InterviewPublic Function(InterviewPublic) change,
  ) {
    final next = change(_need(token));
    interviews[token] = next;
    return next;
  }
}

/// 모델에 copyWith 를 두지 않았다(화면이 안 고친다) — 가짜에서만 필요해 여기 둔다
InterviewPublic _copy(
  InterviewPublic base, {
  InterviewStatus? status,
  bool? consentRequired,
  String? currentQuestion,
  int? questionSeq,
  String? pacing,
}) => InterviewPublic(
  token: base.token,
  status: status ?? base.status,
  applicantName: base.applicantName,
  postingTitle: base.postingTitle,
  consentRequired: consentRequired ?? base.consentRequired,
  currentQuestion: currentQuestion,
  questionSeq: questionSeq ?? base.questionSeq,
  expiresAt: base.expiresAt,
  pacing: pacing,
);

/// 켜라면 켜지는 카메라. 상태를 테스트가 직접 밀어 넣을 수도 있다
class FakeCameraService extends CameraService {
  FakeCameraService({this.opensAs = CameraStatus.live, this.opening});

  /// 켜라고 하면 어떤 상태가 되는가 — 거부·카메라 없음을 만들 때 바꾼다
  final CameraStatus opensAs;

  /// 켜는 데 시간이 걸리게 만든다. **권한 창이 떠 있는 동안**을 흉내 낸다 —
  /// 그 사이에 마이크를 열려고 하면 안드로이드가 거짓을 돌려준다(2026-09-09)
  final Completer<void>? opening;

  CameraStatus _status = CameraStatus.idle;

  int starts = 0;
  int stops = 0;
  int settingsOpened = 0;

  @override
  CameraStatus get status => _status;

  @override
  String? get message =>
      _status == CameraStatus.live || _status == CameraStatus.idle
      ? null
      : '카메라를 쓸 수 없습니다';

  @override
  Future<void> start() async {
    // 진짜와 같은 규약 — 이미 켜져 있으면 아무것도 안 한다.
    // 안 그러면 "다시 열지 않았다" 를 세는 테스트가 거짓말을 한다
    if (_status == CameraStatus.live) return;
    starts++;
    if (opening != null && !opening!.isCompleted) await opening!.future;
    push(opensAs);
  }

  @override
  Future<void> stop() async {
    // 진짜도 이미 놓은 것을 또 놓지 않는다(_release 가 컨트롤러가 없으면 그냥
    // 돌아온다). 앱을 벗어날 때 inactive→hidden→paused 로 세 번 들어오므로,
    // 세는 쪽이 진짜와 같아야 뜻이 맞는다
    if (_status == CameraStatus.idle) return;
    stops++;
    push(CameraStatus.idle);
  }

  @override
  Future<void> openSettings() async => settingsOpened++;

  /// 밖에서 상태를 바꾼다 — 면접 중에 카메라가 끊기는 경우를 만든다
  void push(CameraStatus next) {
    if (_status == next) return;
    _status = next;
    notifyListeners();
  }

  @override
  Widget buildPreview() => const SizedBox(key: Key('fake-preview'));

  /// 서버로 보낸 얼굴 프레임을 밖에서 밀어 넣는 자리
  final StreamController<Uint8List> frameSink =
      StreamController<Uint8List>.broadcast();

  int frameStreams = 0;
  /// 밀어 넣은 프레임 수 — 시험이 셀 일이 있으면 여기서 본다
  int framesPushed = 0;

  @override
  int get framesSent => framesPushed;

  @override
  Stream<Uint8List> frames() {
    frameStreams++;
    return frameSink.stream;
  }
}

/// 가짜 마이크. 테스트가 PCM 조각을 손으로 밀어 넣는다
class FakeMicService implements MicService {
  FakeMicService({this.failsWith});

  /// 열자마자 던질 것. 마이크가 막힌 지원자를 만들 때 쓴다
  final MicUnavailable? failsWith;

  final StreamController<Uint8List> sink =
      StreamController<Uint8List>.broadcast();

  int starts = 0;
  int stops = 0;

  @override
  Future<Stream<Uint8List>> start() async {
    starts++;
    final fail = failsWith;
    if (fail != null) throw fail;
    return sink.stream;
  }

  @override
  Future<void> stop() async => stops++;

  @override
  Future<void> dispose() async {
    await stop();
    await sink.close();
  }
}

/// 가짜 면접 소켓. 서버가 보내는 것을 테스트가 직접 밀어 넣고, 앱이 보낸 것을 센다
class FakeInterviewSocket implements InterviewSocket {
  final StreamController<InterviewEvent> _events =
      StreamController<InterviewEvent>.broadcast();

  final List<Uint8List> audio = [];
  final List<Uint8List> video = [];

  /// [답변 완료] 를 누른 횟수
  int ends = 0;
  bool closed = false;

  @override
  Stream<InterviewEvent> get events => _events.stream;

  /// 서버가 보낸 것처럼 흘려 넣는다
  void emit(InterviewEvent event) => _events.add(event);

  @override
  void sendAudio(Uint8List pcm) => audio.add(pcm);

  @override
  void sendVideo(Uint8List jpeg) => video.add(jpeg);

  @override
  void sendEnd() => ends += 1;

  @override
  Future<void> close() async {
    closed = true;
    await _events.close();
  }
}
