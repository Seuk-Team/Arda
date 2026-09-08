/// 지원자가 부르는 것들 (2026-09-08).
///
/// **담당자 저장소와 클라이언트부터 다르다.** 여기서 쓰는 [ApiClient] 는
/// `readToken` 이 비어 있어 Authorization 헤더를 아예 안 붙인다 — 지원자에게는
/// 계정이 없고 링크의 토큰이 곧 인증이다. 담당자 토큰이 폰에 남아 있더라도
/// 지원자 요청에 섞여 나가면 안 된다(서버는 무시하겠지만, 남의 신분을 실어
/// 보내는 것 자체가 잘못이다).
///
/// 부르는 것은 전부 이미 열려 있는 공개 경로다 — 백엔드 변경 없음:
///   POST /public/applications/lookup        조회 링크 메일 요청
///   GET  /public/applications/status/{t}    내 지원 현황
///   GET  /public/interview/{t}              면접 상태·현재 질문
///   POST /public/interview/{t}/consent      동의
///   POST /public/interview/{t}/start        시작
///   POST /public/interview/{t}/answer       답변
///   POST /public/interview/{t}/finish       종료
library;

import '../api/api_client.dart';
import '../api/endpoints.dart';
import '../api/api_error.dart';
import '../auth/applicant_store.dart';
import '../models/applicant_portal.dart';

class ApplicantPortalRepository {
  ApplicantPortalRepository([ApiClient? client])
    : _client = client ?? ApiClient();

  final ApiClient _client;

  /// 지원자 로그인 — 지원할 때 쓴 이메일 + 생년월일 8자리 (2026-09-08).
  ///
  /// **서버에 아직 없다.** 지금 백엔드가 아는 지원자 확인 방법은 "이메일로
  /// 링크를 보낸다" 하나뿐이고(`portal.py`), `applications` 에 생년월일
  /// 컬럼 자체가 없다. 화면을 먼저 만들어 두고 백엔드가 생기면 **여기만**
  /// 진짜 호출로 바꾼다 — 부르는 쪽(로그인 화면)은 그대로다.
  ///
  /// 돌려줄 것은 **저장할 토큰들**이다. 한 사람이 공고 여러 개에 냈으면 지원
  /// 건마다 하나씩이고, 면접이 잡혀 있으면 그것도 같이 온다.
  ///
  /// 백엔드에 전할 것 하나: 생년월일은 **경우의 수가 적다.** 지원자 나이대가
  /// 20~35세로 좁혀지면 5천 가지쯤이라 이메일만 알면 자동으로 뚫린다 —
  /// `portal.py` 가 링크 방식을 고른 이유가 그것이다. 시도 횟수 제한이나
  /// 다른 보완이 같이 와야 한다.
  Future<List<ApplicantToken>> login({
    required String email,
    required String birthdate,
  }) async {
    throw const ServerError(501, '지원자 로그인은 아직 준비 중입니다.');
  }

  /// 지원 현황 조회 링크를 메일로 보내 달라고 한다.
  ///
  /// **2026-09-08 로그인 개편으로 화면에서 부르는 곳이 없어졌다.** 링크는 앱을
  /// 설치할 때 주는 것이 됐다. 서버 경로는 살아 있어서 바인딩만 남겨 둔다 —
  /// 로그인이 막힌 사람에게 다시 길을 열어 줄 때 이것이 필요하다.
  ///
  /// **찾았든 못 찾았든 서버 응답이 같다.** 건수를 돌려주면 그것만으로 "이 사람이
  /// 여기 지원했는가" 를 확인하는 도구가 되기 때문이다 — 화면도 결과를 나눠
  /// 그리지 않는다. 서버가 준 안내 문장을 그대로 보여 준다
  Future<String> requestLookupLink(String email) async {
    final json = await _client.post(
      Endpoints.portalLookup,
      body: {'email': email},
      authenticated: false,
    );
    return json['message'] as String? ?? '입력하신 주소로 지원 현황 조회 링크를 보냈습니다.';
  }

  /// 링크로 내 지원 현황 보기.
  Future<PortalStatus> status(String token) async {
    final json = await _client.get(Endpoints.portalStatus(token));
    return PortalStatusJson.fromJson(json, token: token);
  }

  Future<InterviewPublic> interview(String token) async {
    final json = await _client.get(Endpoints.interview(token));
    return InterviewPublicJson.fromJson(json, token: token);
  }

  /// 녹음·전사·보관 동의. **면접 시작의 선행 조건이다.**
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
}
