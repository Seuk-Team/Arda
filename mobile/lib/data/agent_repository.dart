/// 아르(에이전트) — 서버에 말을 건다 (큐 8 5단계, 2026-09-03).
///
/// **대화 이력은 서버가 저장하지 않는다.** 화면이 들고 있다가 매번 같이 보낸다
/// (`ChatRequest.history`) — 웹 `ArChat.tsx` 도 같다. 그래서 시트를 닫으면
/// 대화가 사라진다.
///
/// **쓰기 도구는 아르가 스스로 실행하지 않는다.** 서버가 `pending_action` 으로
/// 돌려주고, 사람이 확인해야 `POST /agent/confirm` 이 실제로 실행한다 —
/// 05-design §1 의 "앰버 점선 = 제안 / 잎초록 = 사람 확정" 이 API 수준에서
/// 이미 그렇게 갈려 있다.
library;

import '../api/api_client.dart';
import '../api/endpoints.dart';

/// 아르가 부른 도구 하나 — 화면에 "무엇을 했는지" 한 줄로 적는다.
class ArToolCall {
  const ArToolCall({required this.name, required this.input});

  final String name;
  final Map<String, dynamic> input;
}

/// 사람의 확인을 기다리는 실행 제안.
class ArPendingAction {
  const ArPendingAction({
    required this.toolName,
    required this.arguments,
    required this.description,
  });

  final String toolName;
  final Map<String, dynamic> arguments;

  /// 서버가 만든 사람이 읽을 문장 — "김도현을 면접 단계로 옮깁니다" 같은 것.
  /// **앱이 지어내지 않는다**: 실제로 실행될 것과 화면 문구가 갈리면 안 된다
  final String description;
}

class ArReply {
  const ArReply({required this.text, this.toolCalls = const [], this.pending});

  final String text;
  final List<ArToolCall> toolCalls;
  final ArPendingAction? pending;
}

/// 서버에 보내는 이력 한 줄. `{role, content}` 뿐이다
typedef ArHistoryEntry = ({String role, String content});

class AgentRepository {
  const AgentRepository(this._client);

  final ApiClient _client;

  /// 한 마디 — `POST /agent/chat`.
  ///
  /// 토큰 수·비용도 응답에 오지만 담지 않는다 — **앱 화면에 비용을 노출하지
  /// 않는다**(ADR-0011 의 비용 가드는 웹의 실행 로그에서 본다).
  Future<ArReply> chat(String message, List<ArHistoryEntry> history) async {
    final json = await _client.post(
      Endpoints.agentChat,
      body: {
        'message': message,
        'history': [
          for (final h in history) {'role': h.role, 'content': h.content},
        ],
      },
    );

    final pending = json['pending_action'] as Map<String, dynamic>?;

    return ArReply(
      text: json['reply'] as String? ?? '',
      toolCalls: [
        for (final c in (json['tool_calls'] as List? ?? const []))
          ArToolCall(
            name: (c as Map<String, dynamic>)['name'] as String? ?? '',
            input: (c['input'] as Map<String, dynamic>?) ?? const {},
          ),
      ],
      pending: pending == null
          ? null
          : ArPendingAction(
              toolName: pending['tool_name'] as String? ?? '',
              arguments:
                  (pending['arguments'] as Map<String, dynamic>?) ?? const {},
              description: pending['description'] as String? ?? '',
            ),
    );
  }

  /// 확인 카드에서 [확인] 을 눌렀을 때만 부른다 — `POST /agent/confirm`.
  /// **쓰기 도구는 이 경로로만 실행된다.**
  Future<bool> confirm(ArPendingAction action) async {
    final json = await _client.post(
      Endpoints.agentConfirm,
      body: {'tool_name': action.toolName, 'arguments': action.arguments},
    );
    return json['ok'] as bool? ?? false;
  }
}
