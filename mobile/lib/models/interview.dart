/// 확정된 면접 한 건.
///
/// 백엔드 `InterviewOut`(`backend/app/schemas/schedule.py`) 을 그대로 옮겼다 —
/// `GET /schedules` 가 주는 모양이다. 목 데이터를 실제 API 로 바꿀 때 모양을
/// 다시 주무르지 않으려고 필드 이름·구성을 계약에 맞춰 둔다.
///
/// 데이터는 **확정된 일정 제안만**이다(05-design 캘린더 절 · ADR-0016).
/// 앱에서 등록·수정·삭제는 없다 — 조회 전용.
library;

class Interview {
  const Interview({
    required this.proposalId,
    required this.applicationId,
    required this.applicantName,
    required this.postingTitle,
    required this.interviewerId,
    required this.interviewerName,
    required this.startAt,
    required this.endAt,
  });

  final int proposalId;
  final int applicationId;
  final String applicantName;
  final String postingTitle;

  /// 면접관 — 캘린더 화면의 그날 목록이 쓴다. 대시보드 행에는 넣지 않는다
  final int interviewerId;
  final String interviewerName;

  final DateTime startAt;
  final DateTime endAt;
}
