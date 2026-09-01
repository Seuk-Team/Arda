/// 로그인한 사용자.
///
/// ERD `users` 를 그대로 옮겼다 — id · email · name · role.
/// **사진 컬럼이 없다.** 05-design 설정 절: "프로필 사진은 없다 — `users` 테이블에
/// 사진 컬럼이 없어 이니셜 아바타로 대신한다."
library;

enum UserRole {
  /// 면접관 배정/해제 · 계정 생성 · 메일 템플릿 · 남의 가용 시간
  admin('admin', '관리자'),

  /// 평가 작성이 배정된 건으로 제한되는 것 하나만 다르다 (ADR-0017)
  member('member', '멤버');

  const UserRole(this.value, this.label);

  /// 서버가 주는 코드. 화면 문구가 아니다
  final String value;

  /// 웹 `ROLE_LABEL` 과 같은 문구 — 라벨은 한 곳에만 둔다
  final String label;
}

class AppUser {
  const AppUser({
    required this.id,
    required this.email,
    required this.name,
    required this.role,
  });

  final int id;
  final String email;
  final String name;
  final UserRole role;

  /// 이니셜 아바타에 찍을 글자.
  ///
  /// `dart:core` 의 runes 로 첫 코드 포인트를 집는다 — characters 패키지를
  /// 끌어오지 않으려는 것이고, 이름 첫 글자에 자모 결합까지 볼 일은 없다.
  String get initial =>
      name.isEmpty ? '?' : String.fromCharCode(name.runes.first).toUpperCase();
}
