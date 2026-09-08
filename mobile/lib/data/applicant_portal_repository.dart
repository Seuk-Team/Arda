/// 지원자가 부르는 것들 (2026-09-08).
///
/// **담당자 저장소와 클라이언트부터 다르다.** 지원자 토큰을 붙이는
/// [applicantClient] 를 쓴다 — 담당자 토큰이 폰에 남아 있어도 섞이지 않는다.
/// 서버가 토큰 종류(`typ`)를 갈라 보므로 섞이면 그냥 401 이고, 화면에는
/// "다시 로그인해 주세요" 로만 보여 원인을 찾기 어렵다 (ADR-0031).
///
/// 부르는 것은 둘로 갈린다:
///
/// **① 지원자 토큰이 필요한 것** — 로그인해야 볼 수 있는 자기 것
///   POST /public/applicant/login   로그인 (여기만 토큰 없이)
///   GET  /applicant/me             내 지원·면접·인적성·일정 토큰
///
/// **② 링크 토큰이 곧 인증인 것** — `/applicant/me` 가 준 토큰을 경로에 박는다.
/// 메일 링크에 실리는 것과 같은 토큰이라 **로그인이 만료돼도 이쪽은 돈다.**
///   GET/POST /public/interview/{t}   조회·동의·시작·답변·종료
///   GET/POST /public/aptitude/{t}    인적성 문항·제출
///   GET/POST /public/schedule/{t}    후보 시간·확정, 아르에게 묻기
library;

import '../api/api_client.dart';
import '../api/api_error.dart';
import '../api/endpoints.dart';
import '../auth/applicant_store.dart';
import '../models/applicant_extra.dart';
import '../models/applicant_me.dart';
import '../models/applicant_portal.dart';

class ApplicantPortalRepository {
  ApplicantPortalRepository({ApiClient? client, ApplicantStore? store})
    : _store = store ?? const ApplicantStore(),
      _client = client ?? applicantClient(store ?? const ApplicantStore());

  final ApiClient _client;
  final ApplicantStore _store;

  /// 지원자 로그인 — 지원할 때 쓴 이메일 + 생년월일 8자리(`YYYYMMDD`).
  ///
  /// **실패 사유를 나누지 않는다.** 없는 이메일·틀린 생년월일·생년월일이 없는
  /// 옛 지원서가 전부 같은 401 이고, 형식이 틀려도 422 가 아니라 401 이다 —
  /// 422 는 "형식은 맞다"는 신호가 되어 떠보는 데 쓰인다. 그래서 앱도 사유를
  /// 지어내지 않고 **서버가 준 문구를 그대로** 화면에 올린다.
  ///
  /// 5회 실패하면 15분 잠긴다(429). **잠긴 뒤에는 맞는 값을 넣어도 막힌다** —
  /// 안 그러면 시도 상한이 의미가 없다. 그 안내도 서버 문구 그대로 나간다.
  ///
  /// 성공하면 토큰을 저장한다. 2시간짜리고 리프레시가 없다.
  Future<void> login({required String email, required String birthdate}) async {
    final json = await _client.post(
      Endpoints.applicantLogin,
      body: {'email': email, 'birth_date': birthdate},
      // 로그인은 원래 토큰이 없다. 남은 담당자 토큰이 붙어 나가면 안 된다
      authenticated: false,
    );
    final token = json['access_token'] as String?;
    if (token == null || token.isEmpty) {
      throw const ServerError(502, '로그인 응답을 이해하지 못했습니다.');
    }
    await _store.write(token);
  }

  /// 내 지원 현황. **401 이면 만료다** — [ApiClient] 가 저장된 토큰을 버리고
  /// [AuthExpired] 를 던지므로, 부르는 쪽은 로그인 화면으로 보내면 된다
  Future<ApplicantMe> me() async {
    final json = await _client.get(Endpoints.applicantMe);
    return ApplicantMeJson.fromJson(json);
  }

  /// 지원자로서 나가기
  Future<void> logout() => _store.clear();

  /// 이 기기에 지원자 토큰이 있는가 — 런치 화면이 갈래를 고를 때 쓴다
  Future<bool> hasToken() async => (await _store.read()) != null;

  // ── 링크 토큰으로 도는 것들 ──────────────────────────
  //
  // 아래는 지원자 토큰이 아니라 **경로에 박힌 토큰**이 인증이다.
  // 그래서 헤더를 붙이지 않는다.

  Future<InterviewPublic> interview(String token) async {
    final json = await _client.get(Endpoints.interview(token));
    return InterviewPublicJson.fromJson(json, token: token);
  }

  /// 녹음·전사 동의. **면접 시작의 선행 조건이다** — 지원 폼의 개인정보 동의와
  /// 별개라(그때는 녹음이 없었다) 시작 전에 한 번 더 받는다.
  /// 없으면 `/start` 가 422 로 막는다
  Future<InterviewPublic> consent(String token) async {
    final json = await _client.post(
      Endpoints.interviewConsent(token),
      body: {'agreed': true},
      authenticated: false,
    );
    return InterviewPublicJson.fromJson(json, token: token);
  }

  Future<InterviewPublic> start(String token) async {
    final json = await _client.post(
      Endpoints.interviewStart(token),
      authenticated: false,
    );
    return InterviewPublicJson.fromJson(json, token: token);
  }

  /// 지금 질문에 답한다.
  ///
  /// **순번을 보내지 않는다** — 서버가 "아직 답 안 한 가장 앞 질문" 에 붙인다.
  /// 앱이 번호를 보내면 어긋난 번호로 남의 칸에 답이 들어갈 수 있다.
  ///
  /// 응답에 다음 질문과 진행 보조가 같이 온다. **다시 조회하면 진행 보조가
  /// 사라지므로**(서버가 저장하지 않는다) 이 응답을 그대로 화면에 써야 한다.
  Future<InterviewPublic> answer(String token, String transcript) async {
    final json = await _client.post(
      Endpoints.interviewAnswer(token),
      body: {'transcript': transcript},
      authenticated: false,
    );
    return InterviewPublicJson.fromJson(json, token: token);
  }

  /// 면접 종료. **답을 다 안 해도 끝낼 수 있다** — 중간에 그만두는 것도
  /// 지원자의 선택이고, 막으면 창을 닫아 버려 상태가 진행 중으로 영영 남는다
  Future<InterviewPublic> finish(String token) async {
    final json = await _client.post(
      Endpoints.interviewFinish(token),
      authenticated: false,
    );
    return InterviewPublicJson.fromJson(json, token: token);
  }

  Future<AptitudePublic> aptitude(String token) async {
    final json = await _client.get(Endpoints.aptitude(token));
    return AptitudePublicJson.fromJson(json, token: token);
  }

  /// 인적성 제출. **전 문항 한 번씩, 재제출 없다** — 서버가 부분 제출을 거절한다
  /// (반쯤 남은 설문은 통계를 왜곡한다).
  Future<AptitudePublic> submitAptitude(
    String token,
    Map<String, int> answers,
  ) async {
    final json = await _client.post(
      Endpoints.aptitudeSubmit(token),
      body: {
        'answers': [
          for (final e in answers.entries) {'key': e.key, 'value': e.value},
        ],
      },
      authenticated: false,
    );
    return AptitudePublicJson.fromJson(json, token: token);
  }

  Future<SchedulePublic> schedule(String token) async {
    final json = await _client.get(Endpoints.schedule(token));
    return SchedulePublicJson.fromJson(json, token: token);
  }

  /// 시간 고르기 → **그 자리에서 확정된다** (ADR-0016: 담당자 승인 없음).
  /// 되돌릴 수 없어서 화면이 먼저 물어본다
  Future<SchedulePublic> confirmSlot(String token, int slotId) async {
    final json = await _client.post(
      Endpoints.scheduleConfirm(token),
      body: {'slot_id': slotId},
      authenticated: false,
    );
    return SchedulePublicJson.fromJson(json, token: token);
  }

  /// 아르에게 묻기 — 공고 내용 기반 FAQ.
  ///
  /// **대화 이력이 없다**(서버가 stateless). 한 번 물으면 한 번 답한다 —
  /// 앞 질문을 기억하지 않으므로 화면도 "이어지는 대화" 처럼 굴면 안 된다.
  /// 연봉·평가·다른 지원자는 서버 프롬프트가 답하지 않는다.
  Future<String> askAr(String token, String question) async {
    final json = await _client.post(
      Endpoints.scheduleFaq(token),
      body: {'question': question},
      authenticated: false,
    );
    return json['answer'] as String? ?? '';
  }
}
