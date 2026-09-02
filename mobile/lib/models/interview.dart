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

/// 일정 제안의 상태 — 웹 `SchedulePublicOut.status` 와 같은 값.
///
/// 담당자가 후보 시간을 보내면 `proposed`, 지원자가 고르면 `confirmed`,
/// 기한이 지나면 `expired` 다. 아직 보내지 않았으면 서버가 null 을 준다(= [none]).
///
/// 화면 문구는 웹 `Dashboard.tsx` 의 `scheduleChip` 그대로다.
/// **확정만 연두, 나머지는 전부 무채** — 05-design §1 "색은 판단에만" 이고,
/// 제안 만료는 판단이 아니라 진행 상태다.
enum ScheduleStatus {
  none('일정 없음'),
  proposed('일정 제안 중'),
  confirmed(''), // 확정은 문구 대신 시각을 적는다
  expired('제안 만료');

  const ScheduleStatus(this.label);

  final String label;
}
