/// 아르의 요약 — ERD `applications.ai_summary` 에 들어 있는 **JSON**.
///
/// 에이전트가 3단계 체인으로 만들어 문자열 컬럼에 통째로 넣는다. 웹의
/// `ApplicantPanel.tsx` 가 같은 규격으로 파싱해 그리고 있어 그 동작을 그대로 옮겼다 —
/// 두 화면이 같은 값을 다르게 보여 주면 안 된다.
///
/// 분량은 2026-09-01 팀장 요청으로 줄었다(6905c37): 요지 2문장 이내,
/// 강점·확인 필요 각 2개까지 40자. 화면 노출 약 235자.
///
/// `recommendation.check_points`(면접 확인 포인트)는 값은 오지만 **그리지 않는다** —
/// 05-design §0.5 가 이 자리를 "자소서 요지 + 공고 요건 대비 적합·우려 지점"으로
/// 한정한다. 요약이 길어지면 안 읽는다.
library;

import 'dart:convert';

class AiSummary {
  const AiSummary({
    this.insufficient = false,
    this.gist,
    this.fit = const [],
    this.concerns = const [],
    this.raw,
  });

  /// 자료가 부족해 만들지 못한 경우 — 화면에 그 사실을 적는다
  final bool insufficient;

  /// 자소서 요지 (2문장 이내)
  final String? gist;

  /// 공고 요건과 맞는 지점 — 화면 라벨 "강점"
  final List<String> fit;

  /// 확인이 필요한 지점 — 화면 라벨 "확인 필요"
  final List<String> concerns;

  /// JSON 이 아니었을 때의 원문. 웹도 이 경우 원문을 그대로 보여 준다 —
  /// 모델이 규격을 벗어나도 담당자가 내용은 읽을 수 있어야 한다
  final String? raw;

  bool get isRawText => raw != null;

  /// 그릴 것이 하나도 없는 경우 — 빈 카드를 만들지 않는다
  bool get isEmpty =>
      !insufficient &&
      raw == null &&
      (gist == null || gist!.isEmpty) &&
      fit.isEmpty &&
      concerns.isEmpty;

  /// 저장된 문자열을 판다. 웹과 같은 순서로 관대하게 처리한다:
  /// 코드펜스를 벗기고, JSON 이면 규격대로, 아니면 원문 그대로.
  factory AiSummary.parse(String stored) {
    var s = stored.trim();

    // 모델이 ```json 펜스를 붙여 오는 일이 있다 (웹도 같은 처리)
    if (s.startsWith('```')) {
      s = s.replaceFirst(RegExp(r'^```[a-zA-Z]*\n?'), '');
      if (s.endsWith('```')) s = s.substring(0, s.length - 3);
      s = s.trim();
    }

    Object? decoded;
    try {
      decoded = jsonDecode(s);
    } on FormatException {
      return AiSummary(raw: stored.trim());
    }

    if (decoded is! Map<String, dynamic>) {
      return AiSummary(raw: stored.trim());
    }

    return AiSummary(
      insufficient: decoded['insufficient'] == true,
      gist: switch (decoded['gist']) {
        final String g when g.trim().isNotEmpty => g.trim(),
        _ => null,
      },
      fit: _stringList(decoded['fit']),
      concerns: _stringList(decoded['concerns']),
    );
  }

  static List<String> _stringList(Object? value) {
    if (value is! List) return const [];
    return [
      for (final item in value)
        if (item is String && item.trim().isNotEmpty) item.trim(),
    ];
  }
}
