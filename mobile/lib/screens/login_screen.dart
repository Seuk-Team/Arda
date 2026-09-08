import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../api/api_error.dart';
import '../auth/applicant_store.dart';
import '../auth/auth_service.dart';
import '../auth/current_user.dart';
import '../data/applicant_portal_repository.dart';
import '../routes.dart';
import '../theme/tokens.dart';

/// 로그인 — `mockup-login.html` 을 옮긴 것.
///
/// 그 목업은 폭 360px 카드라 폰 화면에 그대로 맞는다. 모바일 전용 시안은 따로 없다.
///
/// **앱의 첫 화면이다**(2026-09-01). 통과하면 탭 셸(홈)로 간다.
///
/// **진짜 로그인이다**(큐 7, 2026-09-02) — `POST /auth/login` 을 부르고 받은
/// 토큰을 Keystore 에 넣는다.
///
/// 틀린 비밀번호와 끊긴 네트워크는 **다른 문구**로 갈린다: 앞의 것은 다시
/// 입력하면 되고, 뒤의 것은 입력해 봐야 소용이 없다.
///
/// ## 2026-09-08 — 두 갈래가 됐다
///
/// 한 앱을 담당자와 지원자가 같이 쓴다. 그런데 **지원자에게는 계정이 없다** —
/// 서버에 지원자용 로그인이 아예 없고, 공개 경로는 전부 토큰 방식이다
/// (`토큰이 곧 인증이다`, backend/app/api/portal.py). 그래서 지원자 탭은
/// 비밀번호를 묻지 않고 **메일로 받은 링크**를 받는다.
///
/// 두 탭은 저장소도 도착지도 다르다: 담당자는 JWT → 탭 셸, 지원자는 링크
/// 토큰 → 지원자 홈. 섞이면 남의 신분으로 요청이 나간다.
class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key, this.auth, this.portal, this.applicantStore});

  /// 테스트가 가짜 서비스를 넣는 자리. 평소에는 null 이라 진짜가 만들어진다
  final AuthService? auth;

  /// 지원자 탭이 쓰는 것들 — 같은 이유로 열어 둔다
  final ApplicantPortalRepository? portal;
  final ApplicantStore? applicantStore;

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

/// 어느 쪽으로 들어오는가.
enum LoginRole { staff, applicant }

class _LoginScreenState extends State<LoginScreen> {
  /// 담당자가 기본이다 — 지금 이 앱을 매일 켜는 사람이 담당자다.
  /// 지원자는 면접 때 한 번 들어오고, 그 뒤로는 런치 화면이 바로 보내 준다
  LoginRole _role = LoginRole.staff;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      // 목업 body 배경은 --bg (카드가 떠 보이게 하는 받침)
      backgroundColor: AppColors.bg,
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(AppSpace.s5),
            child: ConstrainedBox(
              // 목업 .card: width 360, max-width 100%
              constraints: const BoxConstraints(maxWidth: 360),
              child: Container(
                padding: const EdgeInsets.all(AppSpace.s6),
                decoration: const BoxDecoration(
                  color: AppColors.bgElev,
                  borderRadius: AppShape.card,
                  border: Border.fromBorderSide(
                    BorderSide(
                      color: AppColors.border,
                      width: AppShape.borderW,
                    ),
                  ),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    const Center(child: _ArMark()),
                    const SizedBox(height: AppSpace.s3),
                    const _Logo(),
                    const SizedBox(height: AppSpace.s1),
                    // 초안의 부제. 로고만 있으면 무슨 서비스인지 모른다
                    const Text(
                      '채용 관리',
                      textAlign: TextAlign.center,
                      style: TextStyle(
                        fontFamily: AppType.fontFamily,
                        fontSize: AppType.sm,
                        color: AppColors.textSub,
                        // §2: 작은 글씨엔 그림자 금지
                      ),
                    ),
                    const SizedBox(height: AppSpace.s5),

                    _RoleTabs(
                      role: _role,
                      onChanged: (r) => setState(() => _role = r),
                    ),
                    const SizedBox(height: AppSpace.s5),

                    if (_role == LoginRole.staff)
                      _StaffForm(auth: widget.auth)
                    else
                      _ApplicantForm(
                        portal: widget.portal,
                        store: widget.applicantStore,
                      ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// 두 칸 세그먼트. 탭바(`TabBar`)를 쓰지 않는 이유는 **여기가 화면 전환이
/// 아니라 선택**이라서다 — 스와이프로 넘어가면 비밀번호를 치다가 손이 미끄러져
/// 입력이 사라진다.
class _RoleTabs extends StatelessWidget {
  const _RoleTabs({required this.role, required this.onChanged});

  final LoginRole role;
  final ValueChanged<LoginRole> onChanged;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(3),
      decoration: BoxDecoration(
        color: AppColors.bgSunken,
        borderRadius: AppShape.ctl,
        border: Border.all(
          color: AppColors.borderSoft,
          width: AppShape.borderW,
        ),
      ),
      child: Row(
        children: [
          Expanded(
            child: _RoleTab(
              label: '담당자',
              on: role == LoginRole.staff,
              onTap: () => onChanged(LoginRole.staff),
            ),
          ),
          Expanded(
            child: _RoleTab(
              label: '지원자',
              on: role == LoginRole.applicant,
              onTap: () => onChanged(LoginRole.applicant),
            ),
          ),
        ],
      ),
    );
  }
}

class _RoleTab extends StatelessWidget {
  const _RoleTab({required this.label, required this.on, required this.onTap});

  final String label;
  final bool on;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      selected: on,
      button: true,
      child: Material(
        color: on ? AppColors.accentSoft : Colors.transparent,
        borderRadius: AppShape.ctl,
        clipBehavior: Clip.antiAlias,
        child: InkWell(
          onTap: onTap,
          highlightColor: AppColors.sunkenHover,
          splashColor: AppColors.sunkenHover,
          child: SizedBox(
            // §9 터치 타깃 — 세그먼트도 손가락으로 누른다
            height: AppLayout.minTouchTarget - 6,
            child: Center(
              child: Text(
                label,
                style: TextStyle(
                  fontFamily: AppType.fontFamily,
                  fontSize: AppType.sm,
                  fontWeight: AppType.wSemiBold,
                  color: on ? AppColors.accentText : AppColors.textSub,
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// 담당자 — 이메일·비밀번호. 2026-09-08 이전의 로그인 화면 그대로다.
class _StaffForm extends StatefulWidget {
  const _StaffForm({this.auth});

  final AuthService? auth;

  @override
  State<_StaffForm> createState() => _StaffFormState();
}

class _StaffFormState extends State<_StaffForm> {
  final _email = TextEditingController();
  final _password = TextEditingController();

  late final AuthService _auth = widget.auth ?? AuthService();

  /// 보내는 중 — 버튼을 잠그고 스피너를 돌린다. 두 번 눌러 두 번 보내지 않는다
  bool _sending = false;

  /// 마지막 실패 문구. 다시 입력하기 시작하면 지운다 —
  /// 고치는 중에 남아 있으면 방금 것이 또 틀린 줄 안다
  String? _error;

  @override
  void initState() {
    super.initState();
    // 목업 JS 와 같다 — 둘 다 채워야 버튼이 살아난다
    _email.addListener(_onChanged);
    _password.addListener(_onChanged);
  }

  void _onChanged() => setState(() => _error = null);

  @override
  void dispose() {
    _email.dispose();
    _password.dispose();
    super.dispose();
  }

  bool get _canSubmit =>
      !_sending &&
      _email.text.trim().isNotEmpty &&
      _password.text.trim().isNotEmpty;

  Future<void> _submit() async {
    if (!_canSubmit) return;
    setState(() {
      _sending = true;
      _error = null;
    });

    try {
      final user = await _auth.login(
        email: _email.text.trim(),
        // 비밀번호는 trim 하지 않는다 — 앞뒤 공백도 비밀번호의 일부다
        password: _password.text,
      );
      if (!mounted) return;
      // 더보기·설정이 여기서 읽는다 — 화면마다 /auth/me 를 다시 부르지 않는다
      CurrentUserScope.notifierOf(context)?.value = user;
      // 착지점은 탭 셸이고, 셸은 홈(대시보드)에서 시작한다.
      // pushReplacement 라 뒤로가기로 로그인 화면에 돌아오지 않는다
      Navigator.pushReplacementNamed(context, Routes.home);
    } on ApiError catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e.message;
        _sending = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: [
        _Field(
          label: '이메일',
          controller: _email,
          hint: 'name@company.com',
          keyboardType: TextInputType.emailAddress,
          autofillHints: const [AutofillHints.username],
        ),
        const SizedBox(height: AppSpace.s4),
        _Field(
          label: '비밀번호',
          controller: _password,
          hint: '비밀번호',
          obscureText: true,
          autofillHints: const [AutofillHints.password],
          onSubmitted: _canSubmit ? (_) => _submit() : null,
        ),
        // 실패 문구는 버튼 **위**에 둔다 — 버튼을 누르고 눈이
        // 그 자리에 있는데 아래에 뜨면 못 본다
        if (_error != null) ...[
          const SizedBox(height: AppSpace.s4),
          _ErrorNote(_error!),
        ],
        const SizedBox(height: AppSpace.s4),

        SizedBox(
          // §9 터치 타깃 44 — 목업은 40이지만 그건 데스크톱 기준이다
          height: AppLayout.minTouchTarget,
          child: FilledButton(
            onPressed: _canSubmit ? _submit : null,
            child: _sending
                // 글자를 지우지 않고 그 자리에 스피너를 둔다 —
                // 버튼 크기가 변하면 눌린 자리가 흔들린다
                ? const SizedBox(
                    width: 20,
                    height: 20,
                    child: CircularProgressIndicator(
                      strokeWidth: 2,
                      color: AppColors.bgElev,
                    ),
                  )
                : const Text('로그인'),
          ),
        ),
      ],
    );
  }
}

/// 지원자 — 메일로 받은 링크로 들어온다 (2026-09-08).
///
/// **타이핑을 시키지 않는다.** 토큰이 포털 43자·면접 22자에 대소문자가 섞여
/// 있어 손으로 치면 거의 틀린다. 그래서 [붙여넣기] 를 크게 두고, 입력창은
/// 링크 전체든 토큰만이든 다 받는다([parseApplicantLink]).
///
/// 링크를 잃은 사람을 위해 **메일로 다시 받기**도 같이 둔다 — 포털 링크는
/// 7일이면 죽어서, 이 길이 없으면 다시 들어올 방법이 없다.
class _ApplicantForm extends StatefulWidget {
  const _ApplicantForm({this.portal, this.store});

  final ApplicantPortalRepository? portal;
  final ApplicantStore? store;

  @override
  State<_ApplicantForm> createState() => _ApplicantFormState();
}

class _ApplicantFormState extends State<_ApplicantForm> {
  final _link = TextEditingController();
  final _email = TextEditingController();

  late final ApplicantPortalRepository _portal =
      widget.portal ?? ApplicantPortalRepository();
  late final ApplicantStore _store = widget.store ?? const ApplicantStore();

  bool _entering = false;
  bool _mailing = false;
  String? _error;

  /// 서버가 준 안내 문장. **찾았든 못 찾았든 같은 말이 온다** — 앱이 결과를
  /// 나눠 그리면 그것만으로 "이 사람이 여기 지원했는가" 를 확인하는 도구가 된다
  String? _mailNotice;

  @override
  void initState() {
    super.initState();
    _link.addListener(() {
      if (_error != null) setState(() => _error = null);
    });
  }

  @override
  void dispose() {
    _link.dispose();
    _email.dispose();
    super.dispose();
  }

  Future<void> _paste() async {
    final data = await Clipboard.getData(Clipboard.kTextPlain);
    final text = data?.text?.trim();
    if (text == null || text.isEmpty) {
      setState(() => _error = '복사해 둔 링크가 없습니다.');
      return;
    }
    _link.text = text;
  }

  Future<void> _enter() async {
    if (_entering) return;
    final parsed = parseApplicantLink(_link.text);
    if (parsed == null) {
      setState(() => _error = '링크를 알아보지 못했습니다. 메일에서 받은 주소를 그대로 붙여넣어 주세요.');
      return;
    }

    setState(() {
      _entering = true;
      _error = null;
    });
    try {
      // **저장 전에 서버에 물어본다.** 죽은 링크를 넣어 두면 다음에 앱을 켤
      // 때마다 오류 화면으로 떨어진다
      switch (parsed.kind) {
        case ApplicantTokenKind.portal:
          await _portal.status(parsed.token);
        case ApplicantTokenKind.interview:
          await _portal.interview(parsed.token);
      }
      await _store.add(parsed);
      if (!mounted) return;
      Navigator.pushReplacementNamed(context, Routes.applicantHome);
    } on ApiError catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e.message;
        _entering = false;
      });
    }
  }

  Future<void> _mail() async {
    if (_mailing || _email.text.trim().isEmpty) return;
    setState(() {
      _mailing = true;
      _error = null;
      _mailNotice = null;
    });
    try {
      final message = await _portal.requestLookupLink(_email.text.trim());
      if (!mounted) return;
      setState(() {
        _mailNotice = message;
        _mailing = false;
      });
    } on ApiError catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e.message;
        _mailing = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: [
        const Text(
          '메일로 받은 링크를 붙여넣어 주세요.',
          style: TextStyle(
            fontFamily: AppType.fontFamily,
            fontSize: AppType.sm,
            color: AppColors.textSub,
          ),
        ),
        const SizedBox(height: AppSpace.s4),
        _Field(
          label: '면접·지원 현황 링크',
          controller: _link,
          hint: 'https://…/interview/…',
          keyboardType: TextInputType.url,
          onSubmitted: (_) => _enter(),
        ),
        const SizedBox(height: AppSpace.s2),
        Align(
          alignment: Alignment.centerRight,
          child: TextButton(onPressed: _paste, child: const Text('붙여넣기')),
        ),

        if (_error != null) ...[
          const SizedBox(height: AppSpace.s2),
          _ErrorNote(_error!),
        ],
        const SizedBox(height: AppSpace.s3),

        SizedBox(
          height: AppLayout.minTouchTarget,
          child: FilledButton(
            onPressed: _entering ? null : _enter,
            child: _entering
                ? const SizedBox(
                    width: 20,
                    height: 20,
                    child: CircularProgressIndicator(
                      strokeWidth: 2,
                      color: AppColors.bgElev,
                    ),
                  )
                : const Text('입장'),
          ),
        ),

        const SizedBox(height: AppSpace.s5),
        const Divider(color: AppColors.borderSoft, height: 1),
        const SizedBox(height: AppSpace.s4),

        const Text(
          '링크를 잃어버리셨나요?',
          style: TextStyle(
            fontFamily: AppType.fontFamily,
            fontSize: AppType.sm,
            fontWeight: AppType.wSemiBold,
            color: AppColors.text,
          ),
        ),
        const SizedBox(height: AppSpace.s3),
        _Field(
          label: '지원할 때 쓴 이메일',
          controller: _email,
          hint: 'name@example.com',
          keyboardType: TextInputType.emailAddress,
          onSubmitted: (_) => _mail(),
        ),
        if (_mailNotice != null) ...[
          const SizedBox(height: AppSpace.s3),
          Text(
            _mailNotice!,
            style: const TextStyle(
              fontFamily: AppType.fontFamily,
              fontSize: AppType.caption,
              color: AppColors.textSub,
            ),
          ),
        ],
        const SizedBox(height: AppSpace.s3),
        SizedBox(
          height: AppLayout.minTouchTarget,
          child: OutlinedButton(
            onPressed: _mailing ? null : _mail,
            child: Text(_mailing ? '보내는 중…' : '메일로 링크 받기'),
          ),
        ),
      ],
    );
  }
}

/// 아르 마크 — 앱 UI 초안(2026-09-01)이 로고 위에 더한 것.
///
/// 런처 아이콘이 아르라서 첫 화면에서 한 번은 마주치는 게 맞다. 사이드바 하단
/// 상주 슬롯(05-design §0.5)은 로그인 뒤의 이야기라 여기서는 브랜드 표시일 뿐이고,
/// **누를 수 없다.**
class _ArMark extends StatelessWidget {
  const _ArMark();

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 72,
      height: 72,
      clipBehavior: Clip.antiAlias,
      // 유리 바탕이 캐릭터 뒤로 비친다 (ar_screen.dart ArAvatar 주석 참고)
      decoration: const BoxDecoration(
        color: AppColors.bgElev,
        shape: BoxShape.circle,
        border: Border.fromBorderSide(
          BorderSide(color: AppColors.border, width: AppShape.borderW),
        ),
      ),
      child: Image.asset(
        'assets/images/ar.png',
        fit: BoxFit.cover,
        // 화면 낭독기에는 장식이라고 알린다 — 로고 글자가 바로 아래에 있다
        excludeFromSemantics: true,
      ),
    );
  }
}

/// 목업 `.logo` — 첫 글자 `A` 만 잎초록.
class _Logo extends StatelessWidget {
  const _Logo();

  @override
  Widget build(BuildContext context) {
    return const Text.rich(
      TextSpan(
        children: [
          TextSpan(
            text: 'A',
            style: TextStyle(color: AppColors.leaf),
          ),
          TextSpan(text: 'rda'),
        ],
        style: TextStyle(
          fontFamily: AppType.fontFamily,
          fontSize: AppType.h1,
          fontWeight: FontWeight.w700,
          letterSpacing: -0.22,
          color: AppColors.text,
          shadows: AppTextShadow.heading,
        ),
      ),
      // 카드가 stretch 라 글자가 왼쪽에 붙는다. 아르 마크·부제와 같은
      // 세로선에 서야 하므로 가운데로 맞춘다
      textAlign: TextAlign.center,
      maxLines: 1,
      softWrap: false,
    );
  }
}

/// 목업 `.tfield` — 라벨 + 입력칸.
class _Field extends StatelessWidget {
  const _Field({
    required this.label,
    required this.controller,
    required this.hint,
    this.obscureText = false,
    this.keyboardType,
    this.autofillHints,
    this.onSubmitted,
  });

  final String label;
  final TextEditingController controller;
  final String hint;
  final bool obscureText;
  final TextInputType? keyboardType;
  final List<String>? autofillHints;
  final ValueChanged<String>? onSubmitted;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
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
        TextField(
          controller: controller,
          obscureText: obscureText,
          keyboardType: keyboardType,
          autofillHints: autofillHints,
          onSubmitted: onSubmitted,
          style: const TextStyle(
            fontFamily: AppType.fontFamily,
            fontSize: AppType.body,
            color: AppColors.text,
          ),
          decoration: InputDecoration(
            hintText: hint,
            hintStyle: const TextStyle(
              fontFamily: AppType.fontFamily,
              fontSize: AppType.body,
              color: AppColors.textSub,
            ),
            filled: true,
            fillColor: AppColors.bgElev,
            // §9 터치 타깃 — 목업 40 대신 44
            constraints: const BoxConstraints(
              minHeight: AppLayout.minTouchTarget,
            ),
            contentPadding: const EdgeInsets.symmetric(
              horizontal: AppSpace.s3,
              vertical: AppSpace.s3,
            ),
            border: const OutlineInputBorder(
              borderRadius: AppShape.ctl,
              borderSide: BorderSide(
                color: AppColors.border,
                width: AppShape.borderW,
              ),
            ),
            enabledBorder: const OutlineInputBorder(
              borderRadius: AppShape.ctl,
              borderSide: BorderSide(
                color: AppColors.border,
                width: AppShape.borderW,
              ),
            ),
            focusedBorder: const OutlineInputBorder(
              borderRadius: AppShape.ctl,
              borderSide: BorderSide(
                color: AppColors.leaf,
                width: AppShape.borderW,
              ),
            ),
          ),
        ),
      ],
    );
  }
}

/// 로그인 실패 문구 — 적갈 테두리의 낮은 상자.
///
/// 05-design §1: 색은 판단에만. 로그인 실패는 "이대로는 안 된다"는 판정이라
/// 적갈이 맞다. 토스트로 띄우지 않는 이유는 사라지기 때문이다 — 다시 입력하는
/// 동안 무엇이 틀렸는지 보이는 편이 낫다.
class _ErrorNote extends StatelessWidget {
  const _ErrorNote(this.message);

  final String message;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(
        horizontal: AppSpace.s3,
        vertical: AppSpace.s3,
      ),
      decoration: BoxDecoration(
        color: AppColors.dangerSoft,
        borderRadius: AppShape.ctl,
        border: Border.all(color: AppColors.danger, width: AppShape.borderW),
      ),
      child: Text(
        message,
        style: const TextStyle(
          fontFamily: AppType.fontFamily,
          fontSize: AppType.sm,
          height: 1.5,
          color: AppColors.danger,
        ),
      ),
    );
  }
}
