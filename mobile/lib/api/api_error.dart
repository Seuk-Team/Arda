/// API 호출이 실패하는 방식 — 화면이 서로 다르게 대응해야 하는 것만 나눈다.
///
/// 05-design §6 이 오류 상태에 문구를 요구하는데, "인터넷이 없다" 와
/// "비밀번호가 틀렸다" 에 같은 문구를 띄우면 사용자가 할 수 있는 일이 달라진다.
/// 그래서 종류를 나눈다 — 더 잘게 쪼개지는 않는다. 화면이 구별해 쓰지 않는
/// 구분은 만들 이유가 없다.
library;

sealed class ApiError implements Exception {
  const ApiError(this.message);

  /// 화면에 그대로 띄울 수 있는 한국어 문구
  final String message;

  @override
  String toString() => 'ApiError: $message';
}

/// 서버까지 못 갔다 — 비행기 모드, 지하철, 서버 다운, 잘못된 API_BASE.
///
/// 사용자가 할 수 있는 일이 있다(연결 확인 후 다시 시도)므로 재시도 버튼을 준다.
class NetworkError extends ApiError {
  const NetworkError([super.message = '연결하지 못했습니다. 네트워크를 확인해 주세요.']);
}

/// 토큰이 없거나 만료됐다 (401).
///
/// 우리 서버는 리프레시 토큰이 없다(12시간짜리 access token 하나뿐) — 갱신할
/// 방법이 없으므로 **다시 로그인**이 유일한 길이다. 이걸 받으면 저장된 토큰을
/// 버리고 로그인 화면으로 보낸다.
class AuthExpired extends ApiError {
  const AuthExpired([super.message = '로그인이 만료됐습니다. 다시 로그인해 주세요.']);
}

/// 로그인 자체가 틀렸다 — 로그인 요청에서만 나온다.
///
/// [AuthExpired] 와 나누는 이유: 만료는 "다시 로그인하세요" 지만 이건 이미
/// 로그인 화면에 있는 사람에게 뜬다. 같은 문구를 쓰면 뭘 하라는 건지 모른다.
class LoginFailed extends ApiError {
  const LoginFailed([super.message = '이메일 또는 비밀번호가 올바르지 않습니다.']);
}

/// 권한이 없다 (403). 역할로 막힌 것이라 다시 로그인해도 안 된다.
class Forbidden extends ApiError {
  const Forbidden([super.message = '권한이 없습니다.']);
}

/// 그 밖의 서버 응답 — 4xx·5xx. 상태 코드를 달고 다닌다.
///
/// 서버가 준 문구가 있으면 그걸 쓴다(FastAPI 의 `detail`). 우리 백엔드는
/// 한국어로 답하고 있어 그대로 띄우는 편이 정확하다.
class ServerError extends ApiError {
  const ServerError(this.statusCode, [String? message])
    : super(message ?? '요청을 처리하지 못했습니다.');

  final int statusCode;

  @override
  String toString() => 'ServerError($statusCode): $message';
}
