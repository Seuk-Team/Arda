/// 화면 이름과 경로. 화면이 늘어나면 여기에만 추가한다.
///
/// 화면 구성은 05-design §0.5 화면 지도와 role/app.md §3 범위,
/// 그리고 시안(2026-08-28)을 따른다. 계층은 이렇다:
///
///   공고 리스트 → 그 공고의 지원자 → 지원자 상세
///
/// 로그인은 만들어 뒀지만 아직 앞에 붙이지 않았다 — 큐 7번(실제 JWT 연동)에서
/// 첫 화면으로 건다. 확인은 `flutter run --route=/login` 으로 한다.
library;

abstract final class Routes {
  /// 탭 셸 — 앱의 첫 화면. 열면 **홈(대시보드)** 탭이 선다.
  ///
  /// 공고는 이 셸의 한 탭이라 별도 경로가 없다. 예전에는 이 경로가 곧
  /// 공고 목록이라 `postings` 였다.
  static const home = '/';

  /// 로그인 — 아직 첫 화면이 아니다
  static const login = '/login';

  /// 앱 시작 — 저장된 토큰을 확인하고 홈이나 로그인으로 보낸다 (큐 7)
  static const launch = '/launch';

  /// 한 공고의 지원자 리스트. 인자로 JobPosting 을 받는다
  static const applicants = '/applicants';

  /// 단계 이력. 인자로 (지원자, 공고명) 을 받는다 (시안 2번)
  static const stageHistory = '/applicants/history';

  /// 평가 목록. 인자로 Applicant 를 받는다 (시안 3번)
  static const evaluations = '/applicants/evaluations';

  /// 평가 대기 큐 — 더보기 → 평가 현황. 인자 없음
  static const evaluationQueue = '/evaluations';

  /// 설정 — 더보기 → 설정. 인자 없음
  static const settings = '/settings';

  /// 공고 등록 (2026-09-02) — 공고 탭 상단 [+]
  static const postingNew = '/postings/new';

  /// 지원자 상세. 인자로 Applicant 를 받는다
  static const applicantDetail = '/applicants/detail';
}
