/// 설정 — 앱 UI 초안(2026-09-01). 더보기에서 들어온다.
///
/// 05-design 설정 절: "내 계정 · 면접 가능 시간(전원) / 사용자·권한 ·
/// 메일 템플릿(admin 전용)". 배포판 웹이 이 넷을 상단 탭으로 두고 있어 앱도 같다.
///
/// **역할별 화면 분기를 만들지 않는다**(app.md W4 · ADR-0017) — 네 탭을 다 두고,
/// 막는 것은 서버가 한다. 지금은 어차피 전부 조회 전용이다.
///
/// **내 계정 탭만 서버에 붙었다** (큐 8 3단계, 2026-09-03) — `PATCH /auth/me` 로
/// 이름·비밀번호를 바꾼다. 그 API 가 받는 것이 그 둘뿐이라(`MeUpdate`) 나머지 탭
/// (사용자·권한 · 메일 템플릿 · 면접 가능 시간)은 아직 잠겨 있다. 잠긴 칸은
/// 살아 있는 것처럼 두지 않는다 — 글자가 보조색인 `_LockedField` 다.
library;

import 'package:flutter/material.dart';

import '../api/api_error.dart';
import '../auth/auth_service.dart';
import '../auth/authed_client.dart';
import '../auth/current_user.dart';
import '../auth/logout.dart';
import '../data/mock_data.dart';
import '../data/settings_repository.dart';
import '../models/app_user.dart';
import '../models/availability.dart';
import '../models/mail_template.dart';
import '../models/team_member.dart';
import '../theme/tokens.dart';
import '../utils/format.dart';
import '../widgets/app_top_bar.dart';
import '../widgets/async_view.dart';

/// 배포판 웹과 같은 탭 구성·순서.
enum SettingsTab {
  account('내 계정'),
  users('사용자·권한'),
  mail('메일 템플릿'),
  availability('면접 가능 시간');

  const SettingsTab(this.label);

  final String label;
}

class SettingsScreen extends StatefulWidget {
  const SettingsScreen({super.key, this.user, this.auth, this.repository});

  final AppUser? user;

  /// 테스트가 가짜를 넣는 자리 (큐 8)
  final AuthService? auth;

  /// 나머지 세 탭이 읽는 것들 (큐 8 4단계)
  final SettingsRepository? repository;

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  SettingsTab _tab = SettingsTab.account;

  late final SettingsRepository _repo =
      widget.repository ?? SettingsRepository(authedClient());

  @override
  Widget build(BuildContext context) {
    final me = widget.user ?? CurrentUserScope.of(context) ?? mockUser;

    return Scaffold(
      appBar: const AppTopBar(title: '설정', showBack: true),
      body: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          _Tabs(current: _tab, onSelected: (t) => setState(() => _tab = t)),
          Expanded(
            child: switch (_tab) {
              SettingsTab.account => _Account(user: me, auth: widget.auth),
              SettingsTab.users => _Users(repository: _repo),
              SettingsTab.mail => _Mail(repository: _repo),
              // 내 것만 본다 — 남의 가용 시간은 이 화면이 볼 자리가 아니다
              SettingsTab.availability => _Availability(
                repository: _repo,
                userId: me.id,
              ),
            },
          ),
        ],
      ),
    );
  }
}

/// 탭 줄 — 375px 에 넷이 다 안 들어가 가로로 스크롤한다.
///
/// §9 의 "가로 스크롤로 밀어 넣지 않는다"는 칸반·월 그리드를 두고 한 말이고,
/// 탭 줄은 원래 스크롤하는 요소다(Material `TabBar(isScrollable: true)`).
class _Tabs extends StatelessWidget {
  const _Tabs({required this.current, required this.onSelected});

  final SettingsTab current;
  final ValueChanged<SettingsTab> onSelected;

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: const BoxDecoration(
        color: AppColors.bgElev,
        border: Border(
          bottom: BorderSide(color: AppColors.border, width: AppShape.borderW),
        ),
      ),
      child: SizedBox(
        height: AppLayout.minTouchTarget + AppSpace.s1,
        child: ListView(
          scrollDirection: Axis.horizontal,
          padding: const EdgeInsets.symmetric(horizontal: AppSpace.s2),
          children: [
            for (final tab in SettingsTab.values)
              _Tab(
                tab: tab,
                selected: tab == current,
                onTap: () => onSelected(tab),
              ),
          ],
        ),
      ),
    );
  }
}

class _Tab extends StatelessWidget {
  const _Tab({required this.tab, required this.selected, required this.onTap});

  final SettingsTab tab;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      button: true,
      selected: selected,
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          onTap: onTap,
          highlightColor: AppColors.bgSunken,
          splashColor: AppColors.bgSunken,
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: AppSpace.s3),
            alignment: Alignment.center,
            decoration: BoxDecoration(
              // 선택 표시는 밑줄 — 사이드바가 배경으로 하는 것과 달리
              // 탭 줄은 밑줄이 관습이다(Material TabBar indicator)
              border: Border(
                bottom: BorderSide(
                  color: selected ? AppColors.leaf : Colors.transparent,
                  width: 2,
                ),
              ),
            ),
            child: Text(
              tab.label,
              softWrap: false,
              style: TextStyle(
                fontFamily: AppType.fontFamily,
                fontSize: AppType.sm,
                fontWeight: selected ? AppType.wSemiBold : AppType.wRegular,
                color: selected ? AppColors.leaf : AppColors.textSub,
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// 내 계정 — **여기만 잠금이 풀렸다** (큐 8 3단계, 2026-09-03).
///
/// `PATCH /auth/me` 는 이름과 비밀번호만 받는다. 이메일·역할은 서버가 아예
/// 안 받으므로(`MeUpdate`) 잠긴 채로 둔다 — 로그인 식별자와 권한이라 본인이
/// 스스로 바꿀 것이 아니다.
///
/// 이름과 비밀번호를 한 [저장] 으로 묶지 않는다: 바뀌는 대상이 다르고 비밀번호는
/// 현재 것을 맞혀야 한다. 웹도 별도 폼이다.
class _Account extends StatefulWidget {
  const _Account({required this.user, this.auth});

  final AppUser user;

  /// 테스트가 가짜를 넣는 자리
  final AuthService? auth;

  @override
  State<_Account> createState() => _AccountState();
}

class _AccountState extends State<_Account> {
  late final _name = TextEditingController(text: widget.user.name);
  final _current = TextEditingController();
  final _next = TextEditingController();
  final _confirm = TextEditingController();

  bool _savingName = false;
  bool _savingPassword = false;

  /// 새 비밀번호가 규칙에 맞지 않으면 그 이유. 맞으면 null
  String? _passwordProblem;

  AuthService get _auth =>
      widget.auth ??
      CurrentUserScope.authOf(context) as AuthService? ??
      AuthService();

  @override
  void initState() {
    super.initState();
    // 이름이 그대로면 [저장] 이 잠긴다 — 글자마다 다시 그려야 그게 보인다
    _name.addListener(() => setState(() {}));
    for (final c in [_current, _next, _confirm]) {
      c.addListener(() => setState(() => _passwordProblem = null));
    }
  }

  @override
  void dispose() {
    for (final c in [_name, _current, _next, _confirm]) {
      c.dispose();
    }
    super.dispose();
  }

  /// 서버가 `name` 1~50자를 요구한다(`MeUpdate`). 안 바뀌었으면 보낼 것이 없다
  bool get _canSaveName {
    final v = _name.text.trim();
    return !_savingName &&
        v.isNotEmpty &&
        v.length <= 50 &&
        v != widget.user.name;
  }

  bool get _canChangePassword =>
      !_savingPassword &&
      _current.text.isNotEmpty &&
      _next.text.isNotEmpty &&
      _confirm.text.isNotEmpty;

  Future<void> _saveName() async {
    final messenger = ScaffoldMessenger.of(context);
    final holder = CurrentUserScope.notifierOf(context);
    setState(() => _savingName = true);

    try {
      final updated = await _auth.updateMe(name: _name.text.trim());
      if (!mounted) return;
      // 상단 바 아바타·더보기의 이름이 같은 값을 봐야 한다
      holder?.value = updated;
      messenger.showSnackBar(const SnackBar(content: Text('이름을 저장했습니다')));
    } on ApiError catch (e) {
      if (!mounted) return;
      messenger.showSnackBar(SnackBar(content: Text(e.message)));
    } finally {
      if (mounted) setState(() => _savingName = false);
    }
  }

  Future<void> _changePassword() async {
    // 서버도 막지만 화면에서 먼저 본다 — 422 를 받고 알려 주면 헛걸음이다.
    // 확인칸은 서버로 보내지 않는다(화면에서만 대조하는 값이다)
    if (_next.text.length < 8) {
      setState(() => _passwordProblem = '새 비밀번호는 8자 이상이어야 합니다.');
      return;
    }
    if (_next.text != _confirm.text) {
      setState(() => _passwordProblem = '새 비밀번호가 서로 다릅니다.');
      return;
    }

    final messenger = ScaffoldMessenger.of(context);
    setState(() {
      _savingPassword = true;
      _passwordProblem = null;
    });

    try {
      await _auth.updateMe(
        currentPassword: _current.text,
        newPassword: _next.text,
      );
      if (!mounted) return;

      // 셋 다 비운다. 남겨 두면 남이 화면을 잡았을 때 그대로 보인다
      for (final c in [_current, _next, _confirm]) {
        c.clear();
      }
      messenger.showSnackBar(
        // 서버가 기존 토큰을 죽이지 않아 다시 로그인할 필요가 없다
        const SnackBar(content: Text('비밀번호를 바꿨습니다')),
      );
    } on ApiError catch (e) {
      if (!mounted) return;
      // 401 은 "현재 비밀번호가 올바르지 않습니다" 다. 여기서는 만료가 아니라
      // 틀린 것이므로 로그아웃되지 않는다(api_client.dart authExpiryOn401)
      setState(() => _passwordProblem = e.message);
    } finally {
      if (mounted) setState(() => _savingPassword = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return ListView(
      // 비밀번호 변경·로그아웃이 붙으면서 목록이 화면보다 길어졌다. 아래 여백에
      // 내비게이션 바 높이를 더하지 않으면 마지막 버튼이 그 뒤로 들어간다
      padding: EdgeInsets.fromLTRB(
        AppSpace.s4,
        AppSpace.s4,
        AppSpace.s4,
        AppSpace.s4 + MediaQuery.paddingOf(context).bottom,
      ),
      children: [
        _LiveField(label: '이름', controller: _name, enabled: !_savingName),
        // 서버가 안 받는 것들이다 — 살아 있는 칸으로 두면 바꿀 수 있는 줄 안다
        _LockedField(label: '이메일', value: widget.user.email),
        _LockedField(label: '역할', value: widget.user.role.label),
        const _Note('이메일과 역할은 본인이 바꿀 수 없습니다.'),
        const SizedBox(height: AppSpace.s4),
        Align(
          alignment: Alignment.centerRight,
          child: _ActionButton(
            label: '저장',
            enabled: _canSaveName,
            busy: _savingName,
            onPressed: _saveName,
          ),
        ),

        const _Divider(),
        const _SectionTitle('비밀번호 변경'),
        _LiveField(
          label: '현재 비밀번호',
          controller: _current,
          obscure: true,
          enabled: !_savingPassword,
        ),
        _LiveField(
          label: '새 비밀번호',
          controller: _next,
          obscure: true,
          enabled: !_savingPassword,
        ),
        _LiveField(
          label: '새 비밀번호 확인',
          controller: _confirm,
          obscure: true,
          enabled: !_savingPassword,
        ),
        if (_passwordProblem != null) ...[
          const SizedBox(height: AppSpace.s2),
          Text(
            _passwordProblem!,
            style: const TextStyle(
              fontFamily: AppType.fontFamily,
              fontSize: AppType.caption,
              height: 1.5,
              // §1: 적갈은 판단에만 — 여기가 그 자리다
              color: AppColors.danger,
            ),
          ),
        ],
        const SizedBox(height: AppSpace.s4),
        Align(
          alignment: Alignment.centerRight,
          child: _ActionButton(
            label: '변경',
            enabled: _canChangePassword,
            busy: _savingPassword,
            onPressed: _changePassword,
          ),
        ),

        // 로그아웃 — 웹 836bc01 반영. 더보기에도 있다(웹의 우측 상단 자리).
        const _Divider(),
        const _Divider(),
        Align(alignment: Alignment.centerRight, child: _LogoutButton()),
      ],
    );
  }
}

/// 실제로 타이핑되는 칸 — [_LockedField] 와 달리 글자가 본문색이다.
class _LiveField extends StatelessWidget {
  const _LiveField({
    required this.label,
    required this.controller,
    this.obscure = false,
    this.enabled = true,
  });

  final String label;
  final TextEditingController controller;
  final bool obscure;
  final bool enabled;

  @override
  Widget build(BuildContext context) {
    const outline = OutlineInputBorder(
      borderRadius: AppShape.ctl,
      borderSide: BorderSide(color: AppColors.border, width: AppShape.borderW),
    );

    return Padding(
      padding: const EdgeInsets.only(bottom: AppSpace.s3),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(
            label,
            style: const TextStyle(
              fontFamily: AppType.fontFamily,
              fontSize: AppType.caption,
              color: AppColors.textSub,
            ),
          ),
          const SizedBox(height: AppSpace.s1),
          TextField(
            controller: controller,
            obscureText: obscure,
            enabled: enabled,
            // 비밀번호 칸에 자동완성·추천이 뜨면 안 된다
            autocorrect: !obscure,
            enableSuggestions: !obscure,
            style: const TextStyle(
              fontFamily: AppType.fontFamily,
              fontSize: AppType.body,
              color: AppColors.text,
            ),
            decoration: const InputDecoration(
              isDense: true,
              filled: true,
              fillColor: AppColors.bgSunken,
              contentPadding: EdgeInsets.symmetric(
                horizontal: AppSpace.s3,
                vertical: AppSpace.s3,
              ),
              border: outline,
              enabledBorder: outline,
              disabledBorder: outline,
              focusedBorder: OutlineInputBorder(
                borderRadius: AppShape.ctl,
                borderSide: BorderSide(
                  color: AppColors.leaf,
                  width: AppShape.borderW,
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

/// 실제로 도는 버튼 — [_LockedButton] 과 같은 모양이되 눌린다.
class _ActionButton extends StatelessWidget {
  const _ActionButton({
    required this.label,
    required this.enabled,
    required this.busy,
    required this.onPressed,
  });

  final String label;
  final bool enabled;
  final bool busy;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: AppLayout.minTouchTarget,
      child: FilledButton(
        onPressed: enabled ? onPressed : null,
        child: busy
            // 글자 자리에 스피너를 둔다 — 버튼 크기가 변하면 눌린 자리가 흔들린다
            ? const SizedBox(
                width: 20,
                height: 20,
                child: CircularProgressIndicator(
                  strokeWidth: 2,
                  color: AppColors.bgElev,
                ),
              )
            : Text(label),
      ),
    );
  }
}

/// 구획 사이 실선 — 잠긴 것과 도는 것을 가른다.
class _Divider extends StatelessWidget {
  const _Divider();

  @override
  Widget build(BuildContext context) {
    return const Padding(
      padding: EdgeInsets.symmetric(vertical: AppSpace.s5),
      child: Divider(
        height: AppShape.borderW,
        thickness: AppShape.borderW,
        color: AppColors.border,
      ),
    );
  }
}

class _SectionTitle extends StatelessWidget {
  const _SectionTitle(this.text);

  final String text;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: AppSpace.s4),
      child: Text(
        text,
        style: const TextStyle(
          fontFamily: AppType.fontFamily,
          fontSize: AppType.h2,
          fontWeight: FontWeight.w700,
          color: AppColors.text,
          shadows: AppTextShadow.heading,
        ),
      ),
    );
  }
}

/// 잠기지 않은 유일한 버튼. 더보기의 로그아웃과 같은 동작이다 —
/// 로그인 화면으로 보내고 뒤로 스택을 비운다.
class _LogoutButton extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Material(
      color: AppColors.bgElev,
      shape: const RoundedRectangleBorder(
        borderRadius: AppShape.ctl,
        side: BorderSide(color: AppColors.border, width: AppShape.borderW),
      ),
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        // 더보기의 로그아웃과 같은 함수다 — 한쪽만 토큰을 지우면
        // 나간 줄 알았는데 다음에 켤 때 그대로 들어가진다
        onTap: () => logout(context),
        highlightColor: AppColors.bgSunken,
        splashColor: AppColors.bgSunken,
        child: Container(
          height: AppLayout.minTouchTarget,
          padding: const EdgeInsets.symmetric(horizontal: AppSpace.s5),
          alignment: Alignment.center,
          child: const Text(
            '로그아웃',
            style: TextStyle(
              fontFamily: AppType.fontFamily,
              fontSize: AppType.sm,
              fontWeight: AppType.wSemiBold,
              color: AppColors.text,
            ),
          ),
        ),
      ),
    );
  }
}

/// 사용자·권한 — 웹은 표, 앱은 카드(§9 "테이블은 카드형").
class _Users extends StatelessWidget {
  const _Users({required this.repository});

  final SettingsRepository repository;

  @override
  Widget build(BuildContext context) {
    return _Section<List<TeamMember>>(
      load: repository.users,
      emptyMessage: '등록된 사용자가 없습니다.',
      builder: (users) => ListView(
        padding: const EdgeInsets.all(AppSpace.s4),
        children: [
          const Align(
            alignment: Alignment.centerRight,
            child: _LockedButton('사용자 추가'),
          ),
          const SizedBox(height: AppSpace.s3),
          // 비활성 계정은 맨 아래로 — 지금 일하는 사람이 위에 있어야 한다
          for (final u in [
            ...users,
          ]..sort((a, b) => a.active == b.active ? 0 : (a.active ? -1 : 1)))
            _UserCard(user: u),
          const _Note('계정 생성·권한 변경은 admin 전용이라 앱에서는 보기만 합니다.'),
        ],
      ),
    );
  }
}

class _UserCard extends StatelessWidget {
  const _UserCard({required this.user});

  final TeamMember user;

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(bottom: AppSpace.s3),
      padding: const EdgeInsets.all(AppSpace.s4),
      decoration: BoxDecoration(
        color: AppColors.bgElev,
        borderRadius: AppShape.card,
        border: Border.all(color: AppColors.border, width: AppShape.borderW),
        boxShadow: AppShadow.card,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  user.name,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                    fontFamily: AppType.fontFamily,
                    fontSize: AppType.body,
                    fontWeight: AppType.wSemiBold,
                    color: AppColors.text,
                  ),
                ),
              ),
              const SizedBox(width: AppSpace.s2),
              Text(
                user.role.label,
                softWrap: false,
                style: TextStyle(
                  fontFamily: AppType.fontFamily,
                  fontSize: AppType.caption,
                  fontWeight: AppType.wSemiBold,
                  // §1: 강조는 잎초록. 멤버는 보조색
                  color: user.role == UserRole.admin
                      ? AppColors.leaf
                      : AppColors.textSub,
                ),
              ),
            ],
          ),
          const SizedBox(height: AppSpace.s1),
          Text(
            user.email,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(
              fontFamily: AppType.fontFamily,
              fontSize: AppType.sm,
              color: AppColors.textSub,
            ),
          ),
          const SizedBox(height: AppSpace.s2),
          Text(
            user.active ? '활성' : '비활성',
            style: TextStyle(
              fontFamily: AppType.fontFamily,
              fontSize: AppType.caption,
              // §1: 색은 판단에만. 비활성은 종료 신호가 아니라 상태라 무채로 둔다
              color: user.active ? AppColors.leaf : AppColors.textSub,
            ),
          ),
        ],
      ),
    );
  }
}

/// 메일 템플릿 — 단계 고르기 + 제목·본문. 배포판처럼 문구는 아직 비어 있다.
class _Mail extends StatefulWidget {
  const _Mail({required this.repository});

  final SettingsRepository repository;

  @override
  State<_Mail> createState() => _MailState();
}

class _MailState extends State<_Mail> {
  int _picked = 0;

  @override
  Widget build(BuildContext context) {
    return _Section<List<MailTemplate>>(
      load: widget.repository.templates,
      emptyMessage: '등록된 문구가 없습니다.',
      builder: (templates) {
        // 받아 온 순서가 바뀌어도 고른 자리가 어긋나지 않게 잘라 둔다
        final picked = templates[_picked.clamp(0, templates.length - 1)];

        return ListView(
          padding: const EdgeInsets.all(AppSpace.s4),
          children: [
            SizedBox(
              height: AppLayout.minTouchTarget,
              child: ListView.separated(
                scrollDirection: Axis.horizontal,
                itemCount: templates.length,
                separatorBuilder: (_, _) => const SizedBox(width: AppSpace.s2),
                itemBuilder: (_, i) => _StagePill(
                  label: templates[i].label,
                  selected: i == _picked,
                  onTap: () => setState(() => _picked = i),
                ),
              ),
            ),
            const SizedBox(height: AppSpace.s4),

            // **읽기만 한다.** 고치면 이후 모든 지원자에게 나가는 문구가 바뀌고,
            // 폰에서 여러 줄 본문을 고치는 것은 실수하기 쉽다 — 웹에서 한다
            _LockedField(label: '제목', value: picked.subject),
            _LockedField(label: '본문', value: picked.body, lines: 10),
            _Note(
              picked.isDefault
                  ? '기본 문구입니다. 고치려면 웹 설정에서 하세요.'
                  : '${picked.updatedByName ?? '누군가'} 님이 고친 문구입니다. '
                        '고치려면 웹 설정에서 하세요.',
            ),
            const SizedBox(height: AppSpace.s3),
            const _Note('단계를 바꿀 때 자동으로 나가는 메일도 이 문구를 씁니다.'),
          ],
        );
      },
    );
  }
}

class _StagePill extends StatelessWidget {
  const _StagePill({
    required this.label,
    required this.selected,
    required this.onTap,
  });

  final String label;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      button: true,
      selected: selected,
      child: Material(
        color: selected ? AppColors.sproutSoft : AppColors.bgSunken,
        borderRadius: AppShape.pill,
        clipBehavior: Clip.antiAlias,
        child: InkWell(
          onTap: onTap,
          highlightColor: AppColors.sunkenHover,
          splashColor: AppColors.sunkenHover,
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: AppSpace.s4),
            alignment: Alignment.center,
            decoration: BoxDecoration(
              borderRadius: AppShape.pill,
              border: Border.all(
                color: selected ? AppColors.sprout : AppColors.border,
                width: AppShape.borderW,
              ),
            ),
            child: Text(
              label,
              softWrap: false,
              style: TextStyle(
                fontFamily: AppType.fontFamily,
                fontSize: AppType.sm,
                fontWeight: selected ? AppType.wSemiBold : AppType.wRegular,
                color: selected ? AppColors.leaf : AppColors.textSub,
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// 면접 가능 시간 — 등록한 시간대에서 담당자가 후보 시간을 만든다.
///
/// **읽기만 한다** (큐 8 4단계). 등록은 시작·종료를 고르는 시간 구간 UI 가
/// 따로 필요해서 이번 범위 밖이다.
class _Availability extends StatelessWidget {
  const _Availability({required this.repository, required this.userId});

  final SettingsRepository repository;

  /// 내 것만 본다 — 남의 가용 시간은 이 화면이 볼 자리가 아니다
  final int userId;

  @override
  Widget build(BuildContext context) {
    return _Section<List<Availability>>(
      load: () => repository.availability(userId),
      // 비어도 안내 문구는 남아야 한다 — 왜 비면 안 되는지가 그 문구에 있다
      emptyMessage: '',
      hideWhenEmpty: false,
      builder: (slots) => ListView(
        padding: const EdgeInsets.all(AppSpace.s4),
        children: [
          const _Note(
            '등록한 시간대에서 담당자가 면접 후보 시간을 만들어 지원자에게 보냅니다. '
            '비워 두면 제안을 만들 수 없습니다. 추가·삭제는 웹 설정에서 하세요.',
          ),
          const SizedBox(height: AppSpace.s4),
          if (slots.isEmpty)
            const Center(
              child: Text(
                // 배포판과 같은 문구
                '등록된 가능 시간이 없습니다.',
                style: TextStyle(
                  fontFamily: AppType.fontFamily,
                  fontSize: AppType.sm,
                  color: AppColors.textSub,
                ),
              ),
            )
          else
            for (final s in slots)
              _LockedField(
                label: formatDate(s.startAt),
                value: '${formatTime(s.startAt)} – ${formatTime(s.endAt)}',
              ),
        ],
      ),
    );
  }
}

/// 탭 하나가 서버에서 받아 그리는 틀 — 세 탭이 같은 모양이라 한 번만 쓴다.
///
/// [AsyncView] 를 그대로 쓰되 **탭마다 Future 를 한 번만 만든다** — `build`
/// 안에서 만들면 다시 그릴 때마다 새 요청이 나간다.
class _Section<T> extends StatefulWidget {
  const _Section({
    required this.load,
    required this.builder,
    required this.emptyMessage,
    this.hideWhenEmpty = true,
  });

  final Future<T> Function() load;
  final Widget Function(T) builder;
  final String emptyMessage;

  /// 비면 [emptyMessage] 만 그릴지. false 면 **비어도 [builder] 를 부른다** —
  /// 면접 가능 시간은 비었을 때도 "왜 비면 안 되는지" 를 적어야 한다
  final bool hideWhenEmpty;

  @override
  State<_Section<T>> createState() => _SectionState<T>();
}

class _SectionState<T> extends State<_Section<T>> {
  late Future<T> _future = _load();

  /// `ignore()` 이유는 postings_screen.dart 참고
  Future<T> _load() => widget.load()..ignore();

  @override
  Widget build(BuildContext context) => AsyncView<T>(
    future: _future,
    onRetry: () => setState(() {
      _future = _load();
    }),
    emptyMessage: widget.emptyMessage,
    isEmpty: (v) => widget.hideWhenEmpty && v is List && v.isEmpty,
    builder: (context, value) => widget.builder(value),
  );
}

/// 잠긴 입력칸 — 05-design §4 인풋은 sunken. 값은 보조색으로 둬서
/// 지금 고칠 수 없다는 것이 눌러 보기 전에 읽힌다.
class _LockedField extends StatelessWidget {
  const _LockedField({
    required this.label,
    required this.value,
    this.lines = 1,
  });

  final String label;
  final String value;
  final int lines;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: AppSpace.s4),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            label,
            style: const TextStyle(
              fontFamily: AppType.fontFamily,
              fontSize: AppType.sm,
              fontWeight: AppType.wSemiBold,
              color: AppColors.text,
            ),
          ),
          const SizedBox(height: AppSpace.s2),
          Container(
            width: double.infinity,
            constraints: BoxConstraints(
              minHeight: lines == 1
                  ? AppLayout.minTouchTarget
                  : AppLayout.minTouchTarget * lines / 2,
            ),
            padding: const EdgeInsets.all(AppSpace.s3),
            decoration: BoxDecoration(
              color: AppColors.bgSunken,
              borderRadius: AppShape.ctl,
              border: Border.all(
                color: AppColors.border,
                width: AppShape.borderW,
              ),
            ),
            child: Text(
              value,
              style: const TextStyle(
                fontFamily: AppType.fontFamily,
                fontSize: AppType.body,
                color: AppColors.textSub,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

/// 잠긴 버튼 — 테마의 `disabledBackgroundColor` 와 같은 단계로 둔다.
class _LockedButton extends StatelessWidget {
  const _LockedButton(this.label);

  final String label;

  @override
  Widget build(BuildContext context) {
    return Container(
      height: AppLayout.minTouchTarget,
      padding: const EdgeInsets.symmetric(horizontal: AppSpace.s5),
      alignment: Alignment.center,
      decoration: BoxDecoration(
        color: AppColors.bgSunken,
        borderRadius: AppShape.ctl,
        border: Border.all(color: AppColors.border, width: AppShape.borderW),
      ),
      child: Text(
        label,
        softWrap: false,
        style: const TextStyle(
          fontFamily: AppType.fontFamily,
          fontSize: AppType.sm,
          fontWeight: AppType.wSemiBold,
          color: AppColors.textSub,
        ),
      ),
    );
  }
}

class _Note extends StatelessWidget {
  const _Note(this.text);

  final String text;

  @override
  Widget build(BuildContext context) {
    return Text(
      text,
      style: const TextStyle(
        fontFamily: AppType.fontFamily,
        fontSize: AppType.caption,
        height: 1.5,
        color: AppColors.textSub,
      ),
    );
  }
}
