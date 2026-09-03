/// 설정 화면이 읽는 것들 — 사용자·권한 · 메일 템플릿 · 면접 가능 시간.
/// (큐 8 4단계, 2026-09-03)
///
/// 셋 다 **읽기만** 한다. 쓰기는 각각 이유가 있어 안 붙였다:
/// - 사용자 추가·권한 변경은 admin 전용이고 계정을 만드는 일이다
/// - 메일 템플릿은 **고치면 이후 모든 지원자에게 나가는 문구**가 바뀐다.
///   폰에서 여러 줄 본문을 고치는 것은 실수하기 쉽다 — 웹에서 하면 된다
/// - 면접 가능 시간 등록은 시간 구간 UI 가 따로 필요하다
library;

import '../api/api_client.dart';
import '../api/endpoints.dart';
import '../models/availability.dart';
import '../models/mail_template.dart';
import '../models/team_member.dart';

class SettingsRepository {
  const SettingsRepository(this._client);

  final ApiClient _client;

  /// 팀 전체 — `GET /users`. 조회는 로그인한 사람이면 누구나(ADR-0017).
  Future<List<TeamMember>> users() async {
    final json = await _client.get(Endpoints.users);
    return [
      for (final item in (json['items'] as List? ?? const []))
        TeamMemberJson.fromJson(item as Map<String, dynamic>),
    ];
  }

  /// 메일 문구 넷 — `GET /email-templates`.
  ///
  /// **자동 발송도 이 문구를 쓴다.** 단계를 바꾸면 서버가 여기 저장된 것으로
  /// 메일을 만들어 보낸다. `source` 로 기본 문구인지 누가 고친 것인지 갈린다.
  Future<List<MailTemplate>> templates() async {
    final json = await _client.get(Endpoints.emailTemplates);
    return [
      for (final item in (json['items'] as List? ?? const []))
        MailTemplateJson.fromJson(item as Map<String, dynamic>),
    ];
  }

  /// 내 면접 가능 시간 — `GET /interviewers/{id}/availability`.
  Future<List<Availability>> availability(int userId) async {
    final json = await _client.get(Endpoints.availability(userId));
    return [
      for (final item in (json['items'] as List? ?? const []))
        AvailabilityJson.fromJson(item as Map<String, dynamic>),
    ];
  }
}
