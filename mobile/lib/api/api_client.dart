/// 서버에 말 거는 창구 — 모든 요청이 여기를 지난다.
///
/// **큐 8(API 연동)의 바닥이다.** 토큰 붙이기·에러 분류·타임아웃을 여기 한 번만
/// 두면 화면 쪽은 "부르고 받는" 것만 하면 된다. 화면마다 401 을 따로 처리하기
/// 시작하면 조금씩 달라진다 — 웹도 같은 이유로 `client.ts` 하나를 둔다.
///
/// [http.Client] 를 주입받는다. 테스트가 가짜 클라이언트를 넣어 401·타임아웃·
/// 잘못된 JSON 을 실제 서버 없이 확인한다.
library;

import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;

import 'api_config.dart';
import 'api_error.dart';

/// 저장된 토큰을 읽어 오는 함수. `TokenStore.read` 가 들어온다 —
/// api 층이 auth 층을 직접 참조하지 않게 함수로 받는다(순환 참조 방지).
typedef TokenReader = Future<String?> Function();

/// 토큰이 죽었을 때 알리는 콜백. 저장된 토큰을 지우는 일이 붙는다.
typedef OnAuthExpired = Future<void> Function();

class ApiClient {
  ApiClient({
    http.Client? httpClient,
    this.readToken,
    this.onAuthExpired,
    this.baseUrl = ApiConfig.base,
  }) : _http = httpClient ?? http.Client();

  final http.Client _http;
  final TokenReader? readToken;
  final OnAuthExpired? onAuthExpired;
  final String baseUrl;

  Future<Map<String, dynamic>> get(String path) => _send('GET', path);

  Future<Map<String, dynamic>> post(
    String path, {
    Map<String, dynamic>? body,
    bool authenticated = true,
  }) => _send('POST', path, body: body, authenticated: authenticated);

  Future<Map<String, dynamic>> patch(
    String path, {
    Map<String, dynamic>? body,
  }) => _send('PATCH', path, body: body);

  /// 목록을 주는 엔드포인트용 — 최상위가 배열이라 [_send] 의 Map 과 다르다.
  Future<List<dynamic>> getList(String path) async {
    final decoded = await _sendRaw('GET', path);
    if (decoded is! List) {
      throw const ServerError(200, '목록이 와야 하는데 다른 모양이 왔습니다.');
    }
    return decoded;
  }

  Future<Map<String, dynamic>> _send(
    String method,
    String path, {
    Map<String, dynamic>? body,
    bool authenticated = true,
  }) async {
    final decoded = await _sendRaw(
      method,
      path,
      body: body,
      authenticated: authenticated,
    );
    if (decoded is! Map<String, dynamic>) {
      throw const ServerError(200, '예상과 다른 응답이 왔습니다.');
    }
    return decoded;
  }

  Future<dynamic> _sendRaw(
    String method,
    String path, {
    Map<String, dynamic>? body,
    bool authenticated = true,
  }) async {
    final uri = Uri.parse('$baseUrl$path');
    final headers = <String, String>{
      'Accept': 'application/json',
      if (body != null) 'Content-Type': 'application/json',
    };

    // 로그인처럼 토큰이 아직 없는 요청은 authenticated: false 로 부른다
    if (authenticated) {
      final token = await readToken?.call();
      if (token != null) headers['Authorization'] = 'Bearer $token';
    }

    final request = http.Request(method, uri)..headers.addAll(headers);
    if (body != null) request.body = jsonEncode(body);

    http.Response response;
    try {
      final streamed = await _http.send(request).timeout(ApiConfig.timeout);
      response = await http.Response.fromStream(streamed);
    } on SocketException {
      // DNS 실패·연결 거부 — 서버까지 못 갔다
      throw const NetworkError();
    } on http.ClientException {
      throw const NetworkError();
    } on Exception {
      // TimeoutException 포함. 사용자에게는 못 닿은 것과 구별되지 않는다
      throw const NetworkError();
    }

    return _handle(response, isLogin: !authenticated);
  }

  Future<dynamic> _handle(
    http.Response response, {
    required bool isLogin,
  }) async {
    final code = response.statusCode;

    if (code == 401) {
      // 로그인 요청의 401 은 "비밀번호가 틀렸다" 다 — 만료가 아니다.
      // 같은 문구를 쓰면 로그인 화면에서 "다시 로그인하세요" 가 뜬다
      if (isLogin) throw const LoginFailed();

      // 리프레시 토큰이 없어 갱신할 방법이 없다. 저장된 것을 버린다
      await onAuthExpired?.call();
      throw const AuthExpired();
    }
    if (code == 403) throw Forbidden(_detail(response) ?? '권한이 없습니다.');

    if (code >= 400) throw ServerError(code, _detail(response));

    // 204 No Content — 본문이 없다
    if (response.bodyBytes.isEmpty) return <String, dynamic>{};

    try {
      // 서버가 UTF-8 로 답하는데 charset 을 안 주는 경우가 있어 직접 지정한다.
      // response.body 는 그때 latin1 로 읽어 한글이 깨진다
      return jsonDecode(utf8.decode(response.bodyBytes));
    } on FormatException {
      throw ServerError(code, '응답을 읽지 못했습니다.');
    }
  }

  /// FastAPI 의 `{"detail": "..."}`. 우리 백엔드는 한국어로 답하므로 그대로 쓴다.
  /// 검증 오류(422)는 detail 이 배열이라 문자열일 때만 쓴다.
  String? _detail(http.Response response) {
    try {
      final decoded = jsonDecode(utf8.decode(response.bodyBytes));
      if (decoded is Map && decoded['detail'] is String) {
        return decoded['detail'] as String;
      }
    } on Exception {
      // 본문이 JSON 이 아니면 기본 문구를 쓴다
    }
    return null;
  }

  void close() => _http.close();
}
