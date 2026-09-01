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

enum ArSpeaker { ar, me }

class ArMessage {
  const ArMessage({
    required this.speaker,
    required this.text,
    this.pendingAction,
  });

  final ArSpeaker speaker;
  final String text;

  /// 이 답변에 딸려 온 실행 제안. 아르 말풍선에만 붙는다
  final PendingAction? pendingAction;
}

/// 아르가 하려는 일 — **아직 실행되지 않았다.**
class PendingAction {
  const PendingAction({
    required this.toolName,
    required this.description,
    required this.targets,
    required this.confirmLabel,
  });

  /// 서버가 주는 도구 이름 (`ChatResponse.pending_action.tool_name`)
  final String toolName;

  /// 서버가 지어 준 사람 말 설명 (`description`)
  final String description;

  /// 대상이 누구인지 카드에 적기 위한 요약 — 이름과 지금 단계
  final List<PendingTarget> targets;

  /// 승인 버튼 문구
  final String confirmLabel;
}

class PendingTarget {
  const PendingTarget({
    required this.name,
    required this.stageLabel,
    required this.meta,
  });

  final String name;
  final String stageLabel;
  final String meta;
}
