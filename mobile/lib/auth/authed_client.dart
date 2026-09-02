/// 토큰이 붙은 [ApiClient] 를 만든다 — **저장소는 이걸 쓴다.**
///
/// `ApiClient()` 를 그냥 만들면 `readToken` 이 비어 있어 Authorization 헤더가
/// 안 붙는다. 로그인은 원래 토큰이 없어 통과하지만, 그 밖의 모든 요청은 401 이
/// 되고 화면에는 "로그인이 만료됐습니다" 가 뜬다 — 방금 로그인했는데도.
/// (2026-09-02 실기기에서 공고 목록이 이걸로 막혔다.)
///
/// 큐 8 에서 저장소가 계속 늘어나므로 **연결을 깜빡할 자리를 없앤다.**
/// api 층이 auth 층을 직접 참조하지 않도록, 조립은 여기(auth 층)서 한다.
library;

import '../api/api_client.dart';
import 'token_store.dart';

/// 저장된 토큰을 자동으로 붙이고, 401 이면 그 토큰을 버린다.
ApiClient authedClient([TokenStore store = const TokenStore()]) =>
    ApiClient(readToken: store.read, onAuthExpired: store.clear);
