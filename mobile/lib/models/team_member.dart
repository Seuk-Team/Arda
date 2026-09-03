/// 팀원 한 명 — 설정 `사용자·권한` 탭 (큐 8 4단계, 2026-09-03).
///
/// [AppUser] 와 나눠 둔다: 저쪽은 **나**(토큰의 주인)이고 이쪽은 **남**이다.
/// 남의 계정에는 활성 여부가 붙고, 내 계정에는 붙지 않는다(비활성이면 로그인
/// 자체가 막혀 앱이 받은 사용자는 늘 활성이다).
library;

import 'app_user.dart';

class TeamMember {
  const TeamMember({
    required this.name,
    required this.email,
    required this.role,
    required this.active,
  });

  final String name;
  final String email;
  final UserRole role;

  /// `users.is_active` — 비활성 계정은 목록 맨 아래로 간다
  final bool active;
}

/// 서버 응답 → 모델. `UserItemOut`(backend/app/schemas/user.py).
extension TeamMemberJson on TeamMember {
  static TeamMember fromJson(Map<String, dynamic> json) => TeamMember(
    name: json['name'] as String? ?? '',
    email: json['email'] as String? ?? '',
    // 모르는 역할은 member 로 둔다 — admin 으로 넘겨짚으면 권한이 있는 것처럼 보인다
    role: UserRole.values.firstWhere(
      (r) => r.value == json['role'],
      orElse: () => UserRole.member,
    ),
    active: json['is_active'] as bool? ?? true,
  );
}
