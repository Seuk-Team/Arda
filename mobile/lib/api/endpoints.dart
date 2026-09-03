/// 서버 경로 — 02-api.md 와 1:1.
///
/// **접두어(`/api/v1`)는 여기 없다.** [ApiConfig.base] 가 이미 달고 있다.
/// 02-api.md 표가 접두어를 생략하고 있어 큐 7 에서 404 를 맞았다 — 접두어를
/// 한 곳에만 두는 이유다.
///
/// 문자열을 화면에 흩어 두지 않는다. 경로가 바뀌면 여기만 고친다.
library;

abstract final class Endpoints {
  // 인증
  static const login = '/auth/login';
  static const me = '/auth/me';

  // 공고
  static const postings = '/postings';
  static String posting(int id) => '/postings/$id';

  /// 한 공고의 지원자 목록. 응답은 `ApplicationListItem` 배열 —
  /// **학력·기술이 없다**(목록은 가볍게 준다). 카드가 그것들을 쓰면 안 된다
  static String postingApplications(int id) => '/postings/$id/applications';

  /// 전 공고 통합 검색. `SearchResult { items, total, took_ms, next_cursor }`.
  /// `took_ms` 가 지원자 화면의 **응답 시간 표기**(app.md 큐 8)에 쓰는 값이다
  static const applications = '/applications';

  /// 지원자 상세. **한 번에 다 온다** — 상세 + 단계 이력 + 평가 + 메모 + 첨부.
  /// 화면 하나에 요청 하나면 된다
  static String application(int id) => '/applications/$id';

  static String applicationStage(int id) => '/applications/$id/stage';
  static String applicationHistory(int id) => '/applications/$id/history';
  static String applicationNotes(int id) => '/applications/$id/notes';
  static String applicationEmails(int id) => '/applications/$id/emails';
  static String applicationEvaluations(int id) =>
      '/applications/$id/evaluations';

  /// 평가 하나 고치기 — **내가 쓴 것만** 고칠 수 있다(서버가 `evaluator_id` 를
  /// 본다). 웹은 아직 이 경로를 쓰지 않는다(2026-09-03)
  static String evaluation(int id) => '/evaluations/$id';

  /// 일정 제안 상태 — 대시보드 면접 행의 칩(제안 중·제안 만료)
  static String scheduleProposals(int id) =>
      '/applications/$id/schedule-proposals';

  /// 확정된 면접만. 쿼리 `from`·`to`·`mine`
  static const schedules = '/schedules';

  /// 내게 배정된 지원자 — 평가 대기 큐
  static String assignedApplications(int userId) =>
      '/interviewers/$userId/applications';

  /// **GET 이다.** detail_blocks.dart 주석에 POST 라고 적어 뒀던 것을 고쳤다
  static String fileDownload(int id) => '/files/$id/presign-download';

  // 설정
  static const users = '/users';
  static const emailTemplates = '/email-templates';
  static String availability(int userId) =>
      '/interviewers/$userId/availability';

  // 아르
  static const agentChat = '/agent/chat';
  static const agentConfirm = '/agent/confirm';
}
