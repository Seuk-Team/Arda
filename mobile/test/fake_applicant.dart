// 지원자 갈래용 가짜들 (2026-09-08).
//
// 카메라는 실기기가 있어야 열려서 위젯 테스트에서 진짜를 만들면 그 자리에서
// 죽는다. 저장소도 마찬가지다 — flutter_secure_storage 는 플랫폼 채널을 탄다.
// 그래서 화면이 인터페이스만 알게 해 두고 여기서 갈아끼운다.

import 'package:arda/api/api_error.dart';
import 'package:arda/auth/applicant_store.dart';
import 'package:arda/data/applicant_portal_repository.dart';
import 'package:arda/data/camera_service.dart';
import 'package:arda/models/applicant_extra.dart';
import 'package:arda/models/applicant_portal.dart';
import 'package:flutter/material.dart';

class FakeApplicantStore implements ApplicantStore {
  FakeApplicantStore([List<ApplicantToken>? initial]) : _tokens = [...?initial];

  final List<ApplicantToken> _tokens;

  List<ApplicantToken> get tokens => List.unmodifiable(_tokens);

  @override
  Future<List<ApplicantToken>> read() async => List.of(_tokens);

  @override
  Future<List<ApplicantToken>> add(ApplicantToken token) async {
    _tokens
      ..removeWhere((t) => t == token)
      ..insert(0, token);
    return List.of(_tokens);
  }

  @override
  Future<List<ApplicantToken>> remove(ApplicantToken token) async {
    _tokens.removeWhere((t) => t == token);
    return List.of(_tokens);
  }

  @override
  Future<void> clear() async => _tokens.clear();
}

/// 토큰마다 무엇을 돌려줄지 정해 준다. 안 정해 준 토큰은 404 다
class FakeApplicantPortalRepository implements ApplicantPortalRepository {
  FakeApplicantPortalRepository({
    Map<String, PortalStatus>? statuses,
    Map<String, InterviewPublic>? interviews,
    Map<String, AptitudePublic>? aptitudes,
    Map<String, SchedulePublic>? schedules,
    List<ApplicantToken>? loginTokens,
    this.arAnswer = '아르 답변입니다.',
    this.lookupMessage = '입력하신 주소로 지원 현황 조회 링크를 보냈습니다.',
    this.error,
  }) : statuses = statuses ?? const {},
       interviews = {...?interviews},
       aptitudes = {...?aptitudes},
       schedules = {...?schedules},
       loginTokens = loginTokens ?? const [];

  final Map<String, PortalStatus> statuses;
  final Map<String, InterviewPublic> interviews;
  final Map<String, AptitudePublic> aptitudes;
  final Map<String, SchedulePublic> schedules;
  final String arAnswer;

  /// 로그인이 돌려줄 토큰들. **비어 있으면 진짜와 같이 501 로 실패한다** —
  /// 서버에 아직 지원자 로그인이 없다
  final List<ApplicantToken> loginTokens;

  final String lookupMessage;

  /// 주면 모든 호출이 이걸로 실패한다
  final ApiError? error;

  /// 무엇을 불렀는지 — 순서까지 본다
  final calls = <String>[];

  @override
  Future<List<ApplicantToken>> login({
    required String email,
    required String birthdate,
  }) async {
    calls.add('login:$email:$birthdate');
    if (error != null) throw error!;
    if (loginTokens.isEmpty) {
      throw const ServerError(501, '지원자 로그인은 아직 준비 중입니다.');
    }
    return loginTokens;
  }

  @override
  Future<String> requestLookupLink(String email) async {
    calls.add('lookup:$email');
    if (error != null) throw error!;
    return lookupMessage;
  }

  @override
  Future<PortalStatus> status(String token) async {
    calls.add('status:$token');
    if (error != null) throw error!;
    final found = statuses[token];
    if (found == null) throw const ServerError(404, '유효하지 않은 링크입니다');
    return found;
  }

  @override
  Future<InterviewPublic> interview(String token) async {
    calls.add('interview:$token');
    if (error != null) throw error!;
    return _need(token);
  }

  @override
  Future<InterviewPublic> consent(String token) async {
    calls.add('consent:$token');
    if (error != null) throw error!;
    return _replace(token, (i) => _copy(i, consentRequired: false));
  }

  @override
  Future<InterviewPublic> start(String token) async {
    calls.add('start:$token');
    if (error != null) throw error!;
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
    if (error != null) throw error!;
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
    if (error != null) throw error!;
    return _replace(
      token,
      (i) => _copy(i, status: InterviewStatus.done, currentQuestion: null),
    );
  }

  @override
  Future<AptitudePublic> aptitude(String token) async {
    calls.add('aptitude:$token');
    if (error != null) throw error!;
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
    if (error != null) throw error!;
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
    if (error != null) throw error!;
    final found = schedules[token];
    if (found == null) throw const ServerError(404, '유효하지 않은 링크입니다');
    return found;
  }

  @override
  Future<SchedulePublic> confirmSlot(String token, int slotId) async {
    calls.add('confirmSlot:$token:$slotId');
    if (error != null) throw error!;
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
    if (error != null) throw error!;
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
  FakeCameraService({this.opensAs = CameraStatus.live});

  /// 켜라고 하면 어떤 상태가 되는가 — 거부·카메라 없음을 만들 때 바꾼다
  final CameraStatus opensAs;

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
}
