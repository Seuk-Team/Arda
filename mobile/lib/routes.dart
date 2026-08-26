/// 화면 이름과 경로. 화면이 늘어나면 여기에만 추가한다.
///
/// 화면 구성은 05-design §0.5 화면 지도와 role/app.md §3 범위를 따른다.
/// 앱은 웹의 전 화면을 옮기지 않는다 — 칸반·지원 폼은 앱 범위 밖이다.
library;

abstract final class Routes {
  /// 공고 리스트 — 앱의 첫 화면
  static const postings = '/';

  /// 공고 하나의 지원자 리스트
  static const applicants = '/applicants';

  /// 지원자 상세
  static const applicantDetail = '/applicants/detail';
}
