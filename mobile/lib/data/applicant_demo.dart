/// 지원자 화면을 서버 없이 보기 위한 데모 (2026-09-08).
///
/// **지울 것이다.** 지원자 로그인이 서버에 생기면 이 파일과 [applicantPortal]
/// 의 분기를 같이 지운다.
///
/// ## 왜 있나
///
/// 지원자 로그인은 지금 501 을 던지고(백엔드에 생년월일이 없다), 링크를 넣는
/// 자리도 뺐다. 그래서 **지원자 홈과 면접 화면에 들어갈 길이 하나도 없다** —
/// 다 만들어 놓고 실기기에서 눈으로 볼 수가 없는 상태다.
///
/// ## 진짜로 새어 나가지 않게
///
/// 목데이터가 조용히 진짜인 척한 사고가 이미 한 번 있었다(더보기 평가 현황
/// 배지가 배정 건수와 무관하게 늘 '2' 였다). 그래서 둘을 건다:
///
///  - [applicantDemoMode] 에 `kDebugMode` 를 같이 묶는다. 릴리스 빌드에서는
///    상수가 false 로 접혀 이 코드가 통째로 빠진다.
///  - 켜져 있으면 화면 모서리에 **'데모' 리본**이 뜬다. 진짜 데이터로 착각할
///    수 없다.
///
/// ## 켜는 법
///
/// ```
/// flutter run --dart-define=APPLICANT_DEMO=true
/// ```
///
/// **카메라는 진짜다.** 데모가 대신하는 것은 서버뿐이라, 면접 화면에서 보는
/// 미리보기·권한·수명은 실제 동작 그대로다.
library;

import 'package:flutter/foundation.dart';

import '../api/api_error.dart';
import '../auth/applicant_store.dart';
import '../models/applicant_portal.dart';
import 'applicant_portal_repository.dart';

const applicantDemoMode = kDebugMode && bool.fromEnvironment('APPLICANT_DEMO');

/// 지원자 화면이 쓰는 저장소. 데모가 켜져 있으면 서버 대신 캔 데이터를 준다
ApplicantPortalRepository applicantPortal() =>
    applicantDemoMode ? DemoPortalRepository() : ApplicantPortalRepository();

const _demoPortalToken = 'demo-portal';
const _demoInterviewToken = 'demo-interview';

/// 데모가 로그인할 때 돌려주는 것 — 지원 현황 한 건 + 면접 한 건
const demoTokens = [
  ApplicantToken(kind: ApplicantTokenKind.portal, token: _demoPortalToken),
  ApplicantToken(
    kind: ApplicantTokenKind.interview,
    token: _demoInterviewToken,
  ),
];

/// 서버 흉내. **상태가 남는다** — 동의하면 다음에 물었을 때 동의된 상태고,
/// 답하면 다음 질문으로 넘어간다. 안 그러면 화면을 한 칸도 못 넘긴다
class DemoPortalRepository implements ApplicantPortalRepository {
  static final _questions = [
    '간단히 자기소개를 해 주세요.',
    '최근에 맡았던 일 중 가장 어려웠던 것은 무엇이었나요?',
    '팀에서 의견이 갈렸을 때 어떻게 풀어 가시나요?',
  ];

  /// 화면을 다시 열어도 이어지도록 클래스 밖에 둔다
  static var _consented = false;
  static var _started = false;
  static var _finished = false;
  static var _answered = 0;
  static String? _pacing;

  static const _name = '김도현';
  static const _posting = '프론트엔드 개발자 (React)';

  /// 사람이 기다린다고 느낄 만큼만 — 로딩 상태가 화면에 보여야 한다
  Future<void> _wait() =>
      Future<void>.delayed(const Duration(milliseconds: 400));

  @override
  Future<List<ApplicantToken>> login({
    required String email,
    required String birthdate,
  }) async {
    await _wait();
    return demoTokens;
  }

  @override
  Future<String> requestLookupLink(String email) async {
    await _wait();
    return '입력하신 주소로 지원 현황 조회 링크를 보냈습니다.';
  }

  @override
  Future<PortalStatus> status(String token) async {
    await _wait();
    if (token != _demoPortalToken) {
      throw const ServerError(404, '유효하지 않은 링크입니다');
    }
    return PortalStatus(
      token: token,
      applicantName: _name,
      postingTitle: _posting,
      stageLabel: '서류 검토 중',
      submittedAt: DateTime.now().subtract(const Duration(days: 6)),
    );
  }

  @override
  Future<InterviewPublic> interview(String token) async {
    await _wait();
    return _now(token);
  }

  @override
  Future<InterviewPublic> consent(String token) async {
    await _wait();
    _consented = true;
    return _now(token);
  }

  @override
  Future<InterviewPublic> start(String token) async {
    await _wait();
    _started = true;
    return _now(token);
  }

  @override
  Future<InterviewPublic> answer(String token, String transcript) async {
    await _wait();
    _answered++;
    // 진행 보조는 짧게 답했을 때만 — 서버도 매번 주지 않는다
    _pacing = transcript.trim().length < 20 ? '조금 더 자세히 말씀해 주셔도 좋습니다.' : null;
    if (_answered >= _questions.length) _finished = true;
    return _now(token);
  }

  @override
  Future<InterviewPublic> finish(String token) async {
    await _wait();
    _finished = true;
    return _now(token);
  }

  InterviewPublic _now(String token) {
    if (token != _demoInterviewToken) {
      throw const ServerError(404, '유효하지 않은 링크입니다');
    }
    final status = _finished
        ? InterviewStatus.done
        : _started
        ? InterviewStatus.inProgress
        : InterviewStatus.pending;
    return InterviewPublic(
      token: token,
      status: status,
      applicantName: _name,
      postingTitle: _posting,
      consentRequired: !_consented,
      currentQuestion: status == InterviewStatus.inProgress
          ? _questions[_answered]
          : null,
      questionSeq: status == InterviewStatus.inProgress ? _answered + 1 : null,
      pacing: _pacing,
    );
  }

  /// 처음부터 다시 — 데모를 두 번 보고 싶을 때
  static void reset() {
    _consented = false;
    _started = false;
    _finished = false;
    _answered = 0;
    _pacing = null;
  }
}
