/// 지원자가 받은 링크 토큰 보관 (2026-09-08).
///
/// **담당자 토큰([TokenStore])과 키부터 나눠 둔다.** 한 폰에 둘 다 있을 수
/// 있고(개발·시연), 한쪽 로그아웃이 다른 쪽을 지우면 안 된다.
///
/// ## 왜 목록인가
///
/// 한 사람이 공고 여러 개에 냈으면 **지원 건마다 메일이 한 통씩** 가고 링크도
/// 그만큼 온다(backend/app/api/portal.py). 하나만 들고 있으면 나중에 붙여넣은
/// 링크가 앞의 것을 덮어 다른 지원이 화면에서 사라진다.
///
/// ## 왜 안전한 저장소인가
///
/// 토큰이 곧 인증이다 — 이 값을 아는 사람은 그 지원자의 현황과 면접을 열 수
/// 있다. 평문 XML(`shared_preferences`)에 두면 백업에서 그대로 읽힌다.
///
/// ## 얼마나 오래 사나
///
/// 포털 토큰은 **7일**이고, 링크를 다시 받으면 이전 것이 그 자리에서 죽는다
/// (`portal.py` 가 부를 때마다 새로 발급한다). 그래서 여기 있는 값이 늘 살아
/// 있다고 가정하면 안 된다 — 화면은 410/404 를 만나면 "링크 다시 받기" 로
/// 안내하고 [remove] 로 지운다.
library;

import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// 저장해 둔 링크 하나. 어느 쪽 링크인지까지 같이 들고 있어야 화면을 고른다
enum ApplicantTokenKind {
  /// `/applications/status/<t>` — 지원 현황
  portal('portal'),

  /// `/interview/<t>` — AI 면접
  interview('interview');

  const ApplicantTokenKind(this.value);

  final String value;

  static ApplicantTokenKind? parse(String? value) {
    for (final k in ApplicantTokenKind.values) {
      if (k.value == value) return k;
    }
    return null;
  }
}

class ApplicantToken {
  const ApplicantToken({required this.kind, required this.token});

  final ApplicantTokenKind kind;
  final String token;

  Map<String, dynamic> toJson() => {'kind': kind.value, 'token': token};

  static ApplicantToken? fromJson(Object? value) {
    if (value is! Map) return null;
    final kind = ApplicantTokenKind.parse(value['kind'] as String?);
    final token = value['token'] as String?;
    if (kind == null || token == null || token.isEmpty) return null;
    return ApplicantToken(kind: kind, token: token);
  }

  @override
  bool operator ==(Object other) =>
      other is ApplicantToken && other.kind == kind && other.token == token;

  @override
  int get hashCode => Object.hash(kind, token);
}

class ApplicantStore {
  const ApplicantStore([this._storage = const FlutterSecureStorage()]);

  final FlutterSecureStorage _storage;

  static const _key = 'arda.applicant_tokens';

  Future<List<ApplicantToken>> read() async {
    String? raw;
    try {
      raw = await _storage.read(key: _key);
    } on Exception catch (e) {
      // 기기 암호화 키가 바뀌면(공장 초기화·백업 복원) 읽기가 실패한다.
      // 저장된 것이 없는 것과 같게 다룬다 — 링크를 다시 넣으면 된다.
      // **삼키되 보이게 한다** (TokenStore 와 같은 판단)
      if (kDebugMode) debugPrint('[applicant] 토큰을 읽지 못했다: $e');
      return const [];
    }
    if (raw == null || raw.isEmpty) return const [];

    try {
      final decoded = jsonDecode(raw);
      if (decoded is! List) return const [];
      return [for (final item in decoded) ?ApplicantToken.fromJson(item)];
    } on FormatException {
      // 예전 형식이 남아 있으면 버린다 — 못 읽는 값을 들고 있어 봐야 소용없다
      return const [];
    }
  }

  /// 넣는다. **같은 것이 이미 있으면 맨 앞으로 올린다** — 방금 넣은 링크가
  /// 목록 아래에 묻히면 "안 들어갔나" 싶어 또 붙여넣게 된다
  Future<List<ApplicantToken>> add(ApplicantToken token) async {
    final next = [token, ...(await read())..removeWhere((t) => t == token)];
    await _write(next);
    return next;
  }

  Future<List<ApplicantToken>> remove(ApplicantToken token) async {
    final next = (await read())..removeWhere((t) => t == token);
    await _write(next);
    return next;
  }

  /// 지원자로서 나가기. **최선 노력이다** — 실패해도 던지지 않는다
  /// ([TokenStore.clear] 와 같은 이유: 나갈 방법이 없으면 안 된다)
  Future<void> clear() async {
    try {
      await _storage.delete(key: _key);
    } on Exception {
      // 위 주석 참고
    }
  }

  Future<void> _write(List<ApplicantToken> tokens) async {
    try {
      await _storage.write(
        key: _key,
        value: jsonEncode([for (final t in tokens) t.toJson()]),
      );
    } on Exception catch (e) {
      // 저장에 실패해도 이번 화면은 그대로 굴러간다(메모리에는 있다).
      // 다음에 앱을 켜면 링크를 다시 넣어야 할 뿐이다
      if (kDebugMode) debugPrint('[applicant] 토큰을 저장하지 못했다: $e');
    }
  }
}

/// 붙여넣은 것에서 토큰을 뽑는다.
///
/// 지원자는 메일에서 **링크 전체**를 복사해 온다. 토큰만 치라고 하면 43자
/// (포털)·22자(면접) 대소문자 섞인 문자열이라 거의 틀린다. 그래서 링크든
/// 토큰이든 다 받고, 경로로 어느 쪽인지 가른다.
///
/// 못 알아보면 null 이다 — 화면이 "링크를 다시 확인해 주세요" 라고 한다.
ApplicantToken? parseApplicantLink(String input) {
  final text = input.trim();
  if (text.isEmpty) return null;

  // 경로만 본다. 도메인은 보지 않는다 — 개발 서버·프로덕션·상대 경로가 다 온다
  final path = Uri.tryParse(text)?.path ?? text;
  final parts = [
    for (final s in path.split('/'))
      if (s.isNotEmpty) s,
  ];

  for (var i = 0; i < parts.length - 1; i++) {
    if (parts[i] == 'interview') {
      return ApplicantToken(
        kind: ApplicantTokenKind.interview,
        token: parts[i + 1],
      );
    }
    if (parts[i] == 'status') {
      return ApplicantToken(
        kind: ApplicantTokenKind.portal,
        token: parts[i + 1],
      );
    }
  }

  // 경로가 없으면 토큰만 붙여넣은 것이다. **면접으로 본다** — 링크 없이 토큰만
  // 손에 든 경우는 사실상 면접이고, 틀렸으면 서버가 404 로 알려 준다
  if (parts.length == 1 && !parts.first.contains('.')) {
    return ApplicantToken(
      kind: ApplicantTokenKind.interview,
      token: parts.first,
    );
  }
  return null;
}
