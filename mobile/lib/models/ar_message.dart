/// 아르 대화 한 줄과, 아르가 내놓은 실행 제안.
///
/// 백엔드 `ChatResponse`(`backend/app/api/agent.py`)를 옮겼다 —
/// `POST /agent/chat` 이 `reply` 와 함께 **쓰기 도구는 실행하지 않고**
/// `pending_action` 으로 돌려주고, 사람이 승인하면 `POST /agent/confirm` 이
/// 실제로 실행한다. 05-design §1 의 "앰버 점선 = AI 제안 / 사람이 확정" 규약이
/// API 수준에서 이미 그렇게 갈려 있다.
///
/// 사용량 필드(`input_tokens`·`cost_usd` 등)는 담고 있지 않다 — 앱 화면에
/// 비용을 노출하지 않기 때문이다(ADR-0011 은 비용 가드가 목적이고, 그 수치를
/// 보는 곳은 웹의 실행 로그다).
library;

/// 대화에 들어가는 줄의 종류.
///
/// [log] 와 [error] 는 말풍선이 아니라 가운데 회색 한 줄이다 — 아르가 한 말도,
/// 내가 한 말도 아니어서 말풍선으로 그리면 대화가 아닌 것이 대화처럼 보인다.
enum ArSpeaker {
  ar,
  me,

  /// 아르가 부른 도구 — "지원자 검색 — 단계: 면접" (큐 8 5단계)
  log,

  /// 보내지 못했거나 서버가 거절했다
  error,
}

class ArMessage {
  const ArMessage({required this.speaker, required this.text, this.findings});

  final ArSpeaker speaker;
  final String text;

  /// 이 답변에 딸려 온 지원자 명단. 아르 말풍선에만 붙는다.
  ///
  /// **서버 응답에는 이런 구조가 없다** — `ChatResponse` 는 `reply` 글과
  /// `tool_calls` 뿐이다. 목데이터 시절에 화면을 그려 보려고 두었던 것이라
  /// 서버에서 온 줄에는 붙지 않는다 (큐 8 5단계, 2026-09-03)
  final ArFindings? findings;
}

/// 아르가 찾아 준 지원자들 — **읽기만 하는 결과다.**
///
/// 서버는 여전히 실행 제안(`pending_action`)을 돌려줄 수 있고 사람이
/// `POST /agent/confirm` 으로 확정하는 2단이지만, **앱은 그 확정 버튼을 두지
/// 않는다.** 단계 변경은 지원자 상세의 [단계 변경] 하나로 모은다 — 같은 일을
/// 두 자리에서 할 수 있으면 어느 쪽이 진짜인지 헷갈린다.
///
/// 확정을 기다리는 것이 아니므로 05-design §1 에 따라 **앰버 점선이 아니다.**
/// 상세의 아르의 요약과 같은 정보 블록으로 그린다.
class ArFindings {
  const ArFindings({required this.title, required this.applicants});

  /// 카드 제목 — "아르가 찾은 지원자"
  final String title;

  final List<FoundApplicant> applicants;
}

/// 명단의 한 사람.
///
/// **지금 단계는 담지 않는다.** 한 번의 검색은 같은 단계에서 걸러 온 것이라
/// 줄마다 같은 값이 반복되고, 그 설명은 이미 아르의 말풍선이 하고 있다.
/// 줄에는 "면접에 부를지" 를 판단할 재료만 둔다.
class FoundApplicant {
  const FoundApplicant({
    required this.applicationId,
    required this.name,
    required this.meta,
    this.gist,
  });

  /// [지원자 정보 보기] 가 여는 상세. 이력서·평가·메모가 거기 다 있다
  final int applicationId;

  final String name;

  /// 경력과 기술 — "1년 · Python · AWS"
  final String meta;

  /// 아르의 요약 요지 (`ai_summary.gist`). **상세에 뜨는 값과 같은 것**이라
  /// 두 화면이 다른 말을 하지 않는다. 요약이 없으면 null 이고 줄만 나온다
  final String? gist;
}
