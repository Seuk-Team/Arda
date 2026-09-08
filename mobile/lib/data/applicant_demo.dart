/// 지원자 로그인이 서버에 생길 때까지의 임시 문 둘 (2026-09-08).
///
/// 둘 다 **빌드할 때 이름을 대고 켜야만 산다.** 하는 일이 정반대다:
///
///   [applicantDemoMode]  서버를 캔 데이터로 **대신한다** — 화면을 보여 줄 때
///   [applicantLinkEntry] 진짜 링크로 **진짜 서버에 들어간다** — 붙여서 테스트할 때
///
/// 백엔드를 테스트하려면 뒤엣것이다. 앞엣것은 서버에 아무것도 안 보낸다.
///
/// ── 이하는 데모 ──────────────────────────────────────
///
/// 지원자 화면을 서버 없이 보기 위한 데모.
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
///  - **기본값이 false 다.** `flutter build apk --release` 만 하면 이 문이
///    아예 없다. 켜려면 빌드할 때 이름을 대야 한다.
///  - 켜져 있으면 화면 모서리에 **'데모' 리본**이 뜬다. 진짜 데이터로 착각할
///    수 없다.
///
/// `kDebugMode` 로도 묶어 뒀었는데 뺐다(2026-09-08). 팀에 **나눠 줄 APK 는
/// 릴리스**라야 하는데(디버그는 186MB 에 느리다) 릴리스에서는 상수가 false 로
/// 접혀 문이 사라졌다 — 쓸 수 없는 안전장치는 안전장치가 아니다.
///
/// ## 켜는 법
///
/// ```
/// flutter build apk --release --dart-define=APPLICANT_DEMO=true
/// ```
///
/// **카메라는 진짜다.** 데모가 대신하는 것은 서버뿐이라, 면접 화면에서 보는
/// 미리보기·권한·수명은 실제 동작 그대로다.
library;

import '../api/api_error.dart';
import '../auth/applicant_store.dart';
import '../models/applicant_extra.dart';
import '../models/applicant_portal.dart';
import 'applicant_portal_repository.dart';

const applicantDemoMode = bool.fromEnvironment('APPLICANT_DEMO');

/// 링크를 붙여넣어 **진짜 서버로** 들어가는 문.
///
/// 지원자 로그인(이메일 + 생년월일)이 서버에 없어서, 그 전까지는 지원자
/// 화면에 들어갈 길이 하나도 없다. 그런데 **면접·인적성·일정 공개 API 는 다
/// 살아 있다** — 막힌 것은 문 하나뿐이다. 그래서 담당자가 웹에서 만든 링크를
/// 그대로 붙여넣어 들어가게 열어 둔다: 카메라도, 동의·시작·답변·종료도,
/// 서버에 남는 기록도 전부 진짜다.
///
/// 켜는 법: `flutter build apk --debug --dart-define=APPLICANT_LINK=true`
///
/// 데모와 같이 켜면 데모가 이긴다 — 저장소가 캔 데이터를 주므로 링크를 넣어도
/// 서버에 안 간다. 테스트할 때는 데모를 끄고 이것만 켠다.
///
/// 진짜 로그인이 생기면 이 플래그와 로그인 화면의 그 칸을 같이 지운다.
const applicantLinkEntry = bool.fromEnvironment('APPLICANT_LINK');

/// 지원자 화면이 쓰는 저장소. 데모가 켜져 있으면 서버 대신 캔 데이터를 준다
ApplicantPortalRepository applicantPortal() =>
    applicantDemoMode ? DemoPortalRepository() : ApplicantPortalRepository();

const _demoPortalToken = 'demo-portal';
const _demoInterviewToken = 'demo-interview';
const _demoAptitudeToken = 'demo-aptitude';
const _demoScheduleToken = 'demo-schedule';

/// 데모가 로그인할 때 돌려주는 것 — 탭 넷이 다 채워진다
const demoTokens = [
  ApplicantToken(kind: ApplicantTokenKind.portal, token: _demoPortalToken),
  ApplicantToken(
    kind: ApplicantTokenKind.interview,
    token: _demoInterviewToken,
  ),
  ApplicantToken(kind: ApplicantTokenKind.aptitude, token: _demoAptitudeToken),
  ApplicantToken(kind: ApplicantTokenKind.schedule, token: _demoScheduleToken),
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

  // ── 인적성 ──────────────────────────────────────────

  static var _aptitudeSubmitted = false;

  /// 문항은 서버 상수를 흉내 낸 것이다. **실제 문항이 아니다** — 진짜는
  /// `backend/app/api/aptitude.py` 의 QUESTIONS 가 정한다
  static const _aptitudeQuestions = [
    AptitudeQuestion(key: 'q1', text: '새로운 방식을 시도하는 것을 즐긴다.'),
    AptitudeQuestion(key: 'q2', text: '맡은 일은 기한 안에 끝내는 편이다.'),
    AptitudeQuestion(key: 'q3', text: '여러 사람과 함께 일할 때 힘이 난다.'),
    AptitudeQuestion(key: 'q4', text: '의견이 부딪혀도 끝까지 이야기해 푸는 편이다.'),
    AptitudeQuestion(key: 'q5', text: '예상치 못한 변화에도 침착한 편이다.'),
  ];

  static const _likert = {
    1: '전혀 아니다',
    2: '아니다',
    3: '보통',
    4: '그렇다',
    5: '매우 그렇다',
  };

  @override
  Future<AptitudePublic> aptitude(String token) async {
    await _wait();
    return _aptitudeNow(token);
  }

  @override
  Future<AptitudePublic> submitAptitude(
    String token,
    Map<String, int> answers,
  ) async {
    await _wait();
    _aptitudeSubmitted = true;
    return _aptitudeNow(token);
  }

  AptitudePublic _aptitudeNow(String token) {
    if (token != _demoAptitudeToken) {
      throw const ServerError(404, '유효하지 않은 링크입니다');
    }
    return AptitudePublic(
      token: token,
      status: _aptitudeSubmitted
          ? AptitudeStatus.submitted
          : AptitudeStatus.pending,
      applicantName: _name,
      postingTitle: _posting,
      questions: _aptitudeSubmitted ? const [] : _aptitudeQuestions,
      likertLabels: _aptitudeSubmitted ? const {} : _likert,
    );
  }

  // ── 면접 시간 조율 ──────────────────────────────────

  static int? _confirmedSlotId;

  /// 후보 시간 셋 — 내일부터 사흘, 오후로
  static List<ScheduleSlot> get _slots {
    final base = DateTime.now().add(const Duration(days: 1));
    return [
      for (var i = 0; i < 3; i++)
        ScheduleSlot(
          id: 100 + i,
          startAt: DateTime(base.year, base.month, base.day + i, 14),
          endAt: DateTime(base.year, base.month, base.day + i, 15),
        ),
    ];
  }

  @override
  Future<SchedulePublic> schedule(String token) async {
    await _wait();
    return _scheduleNow(token);
  }

  @override
  Future<SchedulePublic> confirmSlot(String token, int slotId) async {
    await _wait();
    _confirmedSlotId = slotId;
    return _scheduleNow(token);
  }

  SchedulePublic _scheduleNow(String token) {
    if (token != _demoScheduleToken) {
      throw const ServerError(404, '유효하지 않은 링크입니다');
    }
    final picked = _confirmedSlotId;
    return SchedulePublic(
      token: token,
      status: picked == null
          ? ScheduleStatus.proposed
          : ScheduleStatus.confirmed,
      applicantName: _name,
      postingTitle: _posting,
      currentStage: 'screening',
      slots: _slots,
      confirmedSlot: picked == null
          ? null
          : _slots.firstWhere(
              (s) => s.id == picked,
              orElse: () => _slots.first,
            ),
    );
  }

  @override
  Future<String> askAr(String token, String question) async {
    await _wait();
    // 진짜 아르는 공고 내용을 읽고 답한다. 데모는 **답을 지어내지 않는다** —
    // 무엇을 답하는 자리인지만 보여 준다
    return '데모에서는 실제 답변을 만들지 않습니다. '
        '연결되면 공고 내용을 바탕으로 답합니다. (물어보신 것: $question)';
  }

  /// 처음부터 다시 — 데모를 두 번 보고 싶을 때
  static void reset() {
    _consented = false;
    _started = false;
    _finished = false;
    _answered = 0;
    _pacing = null;
    _aptitudeSubmitted = false;
    _confirmedSlotId = null;
  }
}
