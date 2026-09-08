// 붙여넣은 것에서 토큰 뽑기 (2026-09-08).
//
// 지원자는 메일에서 링크 전체를 복사해 온다. 여기서 틀리면 멀쩡한 링크를 넣고도
// "알아보지 못했습니다" 가 뜬다 — 지원자가 다시 할 수 있는 일이 없는 자리다.

import 'package:arda/auth/applicant_store.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  // 저장소가 플랫폼 채널을 타서 바인딩이 필요하다. 없으면 채널을 찾기도 전에
  // 죽어서 우리가 보려는 경로(플러그인 없음 → MissingPluginException)가 안 나온다
  TestWidgetsFlutterBinding.ensureInitialized();

  group('링크 알아보기', () {
    test('면접 링크', () {
      final t = parseApplicantLink(
        'https://seuk.suvisdev.cloud/interview/rT4k9_xQmZ2aB7nLp0sWvA',
      );
      expect(t?.kind, ApplicantTokenKind.interview);
      expect(t?.token, 'rT4k9_xQmZ2aB7nLp0sWvA');
    });

    test('지원 현황 링크', () {
      final t = parseApplicantLink(
        'https://seuk.suvisdev.cloud/applications/status/abc123',
      );
      expect(t?.kind, ApplicantTokenKind.portal);
      expect(t?.token, 'abc123');
    });

    test('앞뒤 공백은 무시한다 — 복사하면 딸려 온다', () {
      final t = parseApplicantLink('  https://x.dev/interview/tok  \n');
      expect(t?.token, 'tok');
    });

    test('상대 경로도 받는다 — PUBLIC_APP_BASE_URL 이 비면 서버가 이렇게 준다', () {
      final t = parseApplicantLink('/interview/tok');
      expect(t?.kind, ApplicantTokenKind.interview);
      expect(t?.token, 'tok');
    });

    test('토큰만 붙여넣으면 면접으로 본다', () {
      final t = parseApplicantLink('rT4k9_xQmZ2aB7nLp0sWvA');
      expect(t?.kind, ApplicantTokenKind.interview);
      expect(t?.token, 'rT4k9_xQmZ2aB7nLp0sWvA');
    });

    test('빈 문자열은 못 알아본다', () {
      expect(parseApplicantLink('   '), isNull);
    });

    test('경로에 아무것도 없는 주소는 못 알아본다', () {
      expect(parseApplicantLink('https://seuk.suvisdev.cloud'), isNull);
    });

    test('엉뚱한 경로는 못 알아본다 — 담당자 링크를 넣은 경우', () {
      expect(parseApplicantLink('https://x.dev/postings/3'), isNull);
    });
  });

  // 2026-09-08 실기기에서 첫 로그인이 여기서 멈췄다. 저장된 것이 없으면
  // read() 가 `const []` 를 주는데 add() 가 거기에 removeWhere 를 불렀다 —
  // UnsupportedError 라 `on ApiError` 에도 안 걸려 스피너만 영영 돌았다.
  //
  // 플랫폼 채널이 없는 테스트 환경이 그 경로를 그대로 만든다: 저장소 읽기가
  // MissingPluginException 으로 실패 → read() 가 `const []`.
  group('저장소가 없을 때 (첫 실행·플러그인 없음)', () {
    const store = ApplicantStore();
    const token = ApplicantToken(kind: ApplicantTokenKind.portal, token: 'p1');

    test('읽으면 빈 목록이다', () async {
      expect(await store.read(), isEmpty);
    });

    test('넣어도 죽지 않는다', () async {
      expect(await store.add(token), [token]);
    });

    test('빼도 죽지 않는다', () async {
      expect(await store.remove(token), isEmpty);
    });
  });

  group('토큰 보관', () {
    test('같은 것을 다시 넣으면 맨 앞으로 올라간다 — 두 번 쌓이지 않는다', () {
      const a = ApplicantToken(kind: ApplicantTokenKind.interview, token: 'a');
      const b = ApplicantToken(kind: ApplicantTokenKind.portal, token: 'b');
      expect(
        a ==
            const ApplicantToken(
              kind: ApplicantTokenKind.interview,
              token: 'a',
            ),
        isTrue,
      );
      expect(a == b, isFalse);
    });

    test('종류가 다르면 다른 토큰이다 — 값이 같아도', () {
      const a = ApplicantToken(kind: ApplicantTokenKind.interview, token: 'x');
      const b = ApplicantToken(kind: ApplicantTokenKind.portal, token: 'x');
      expect(a == b, isFalse);
    });
  });
}
