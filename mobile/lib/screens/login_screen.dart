import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../api/api_error.dart';
import '../auth/applicant_store.dart';
import '../auth/auth_service.dart';
import '../auth/current_user.dart';
import '../data/applicant_demo.dart';
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
/// **지원할 때 쓴 이메일 + 생년월일 8자리**로 들어온다.
///
/// **그 로그인은 서버에 아직 없다**(2026-09-08) — 화면만 먼저 만들어 뒀고,
/// 백엔드가 생기면 [ApplicantPortalRepository.login] 만 진짜 호출로 바뀐다.
/// 링크 붙여넣기는 뺐다: 링크는 앱을 설치할 때 주는 것이다.
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

/// 지원자 — 지원할 때 쓴 이메일 + 생년월일 8자리 (2026-09-08).
///
/// **서버에 아직 없다.** 백엔드가 아는 지원자 확인 방법은 지금 "이메일로 링크를
/// 보낸다" 하나뿐이고 `applications` 에 생년월일 컬럼이 없다. 화면을 먼저 만들어
/// 두고 [ApplicantPortalRepository.login] 이 진짜 호출이 되면 그대로 살아난다 —
/// 이 위젯은 고칠 것이 없다.
///
/// 링크 붙여넣기는 뺐다: 링크는 **앱을 설치할 때 주는 것**이라 앱 안에서 다시
/// 받을 자리가 없다.
class _ApplicantForm extends StatefulWidget {
  const _ApplicantForm({this.portal, this.store});

  final ApplicantPortalRepository? portal;
  final ApplicantStore? store;

  @override
  State<_ApplicantForm> createState() => _ApplicantFormState();
}

class _ApplicantFormState extends State<_ApplicantForm> {
  final _email = TextEditingController();
  final _birth = TextEditingController();

  late final ApplicantPortalRepository _portal =
      widget.portal ?? applicantPortal();
  late final ApplicantStore _store = widget.store ?? const ApplicantStore();

  bool _sending = false;
  String? _error;

  /// 개발용 링크 칸 ([applicantLinkEntry] 일 때만 산다)
  final _link = TextEditingController();
  bool _entering = false;

  @override
  void initState() {
    super.initState();
    _email.addListener(_onChanged);
    _birth.addListener(_onChanged);
  }

  void _onChanged() => setState(() => _error = null);

  @override
  void dispose() {
    _email.dispose();
    _birth.dispose();
    _link.dispose();
    super.dispose();
  }

  /// 담당자가 웹에서 만든 링크로 **진짜 서버에** 들어간다.
  ///
  /// 종류를 가리지 않는다 — 면접·인적성·일정·지원 현황 링크가 다 들어오고,
  /// 여러 번 넣으면 쌓인다(탭마다 자기 링크를 쓴다).
  Future<void> _enterByLink() async {
    if (_entering) return;
    final parsed = parseApplicantLink(_link.text);
    if (parsed == null) {
      setState(() => _error = '링크를 알아보지 못했습니다.');
      return;
    }
    setState(() {
      _entering = true;
      _error = null;
    });
    try {
      // **저장 전에 서버에 물어본다** — 죽은 링크를 넣어 두면 다음에 켤 때마다
      // 오류 화면으로 떨어진다
      switch (parsed.kind) {
        case ApplicantTokenKind.portal:
          await _portal.status(parsed.token);
        case ApplicantTokenKind.interview:
          await _portal.interview(parsed.token);
        case ApplicantTokenKind.aptitude:
          await _portal.aptitude(parsed.token);
        case ApplicantTokenKind.schedule:
          await _portal.schedule(parsed.token);
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
    } catch (e) {
      if (!mounted) return;
      if (kDebugMode) debugPrint('[applicant] 링크 입장 실패: $e');
      setState(() {
        _error = '들어가지 못했습니다.';
        _entering = false;
      });
    }
  }

  bool get _canSubmit =>
      !_sending &&
      _email.text.trim().isNotEmpty &&
      _birth.text.length == _birthLength;

  Future<void> _submit() async {
    if (!_canSubmit) return;
    // 8자리를 채웠어도 날짜가 아닐 수 있다(19981345). 왕복 한 번을 아끼고,
    // 무엇이 틀렸는지도 여기서 더 정확히 말해 줄 수 있다
    if (!_looksLikeBirthdate(_birth.text)) {
      setState(() => _error = '생년월일을 다시 확인해 주세요. 예: 19980315');
      return;
    }

    setState(() {
      _sending = true;
      _error = null;
    });
    try {
      final tokens = await _portal.login(
        email: _email.text.trim(),
        birthdate: _birth.text,
      );
      for (final token in tokens) {
        await _store.add(token);
      }
      if (!mounted) return;
      Navigator.pushReplacementNamed(context, Routes.applicantHome);
    } on ApiError catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e.message;
        _sending = false;
      });
    } catch (e) {
      // 저장소가 죽는 것처럼 **예상 못 한 실패**. 여기서 안 받으면 스피너가
      // 영영 돌고 사용자가 할 수 있는 일이 없다 (2026-09-08 실기기에서 겪었다).
      // `on Exception` 이 아니라 통째로 받는 이유: Error 도 같이 와야 한다
      if (!mounted) return;
      if (kDebugMode) debugPrint('[applicant] 로그인 실패: $e');
      setState(() {
        _error = '로그인하지 못했습니다. 잠시 후 다시 시도해 주세요.';
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
          hint: '지원할 때 쓴 이메일',
          keyboardType: TextInputType.emailAddress,
          autofillHints: const [AutofillHints.username],
        ),
        const SizedBox(height: AppSpace.s4),
        _Field(
          label: '생년월일 8자리',
          controller: _birth,
          hint: '예: 19980315',
          // 비밀번호 자리라 가린다. 대신 8자리를 다 채우기 전에는 버튼이 안
          // 살아나고, 날짜가 아니면 보내기 전에 잡아 준다
          obscureText: true,
          keyboardType: TextInputType.number,
          inputFormatters: [
            FilteringTextInputFormatter.digitsOnly,
            // maxLength 를 안 쓰는 이유: 입력창 아래 카운터가 붙어 칸 높이가 는다
            LengthLimitingTextInputFormatter(_birthLength),
          ],
          onSubmitted: _canSubmit ? (_) => _submit() : null,
        ),
        // 실패 문구는 버튼 위 (담당자 탭과 같은 이유)
        if (_error != null) ...[
          const SizedBox(height: AppSpace.s4),
          _ErrorNote(_error!),
        ],
        const SizedBox(height: AppSpace.s4),

        SizedBox(
          height: AppLayout.minTouchTarget,
          child: FilledButton(
            onPressed: _canSubmit ? _submit : null,
            child: _sending
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

        // 개발용. 릴리스 빌드에서는 상수가 false 라 통째로 빠진다
        if (applicantLinkEntry) ...[
          const SizedBox(height: AppSpace.s5),
          const Divider(color: AppColors.borderSoft, height: 1),
          const SizedBox(height: AppSpace.s4),
          const Text(
            '개발용 — 링크로 입장',
            style: TextStyle(
              fontFamily: AppType.fontFamily,
              fontSize: AppType.sm,
              fontWeight: AppType.wSemiBold,
              color: AppColors.warnText,
            ),
          ),
          const SizedBox(height: AppSpace.s1),
          const Text(
            '담당자가 만든 면접·인적성·일정 링크를 붙여넣으면 그 링크로 들어갑니다. '
            '여러 번 넣으면 탭마다 채워집니다.',
            style: TextStyle(
              fontFamily: AppType.fontFamily,
              fontSize: AppType.caption,
              height: 1.5,
              color: AppColors.textSub,
            ),
          ),
          const SizedBox(height: AppSpace.s3),
          _Field(
            label: '링크',
            controller: _link,
            hint: 'https://…/interview/…',
            keyboardType: TextInputType.url,
            onSubmitted: (_) => _enterByLink(),
          ),
          const SizedBox(height: AppSpace.s2),
          Align(
            alignment: Alignment.centerRight,
            child: TextButton(
              onPressed: () async {
                final data = await Clipboard.getData(Clipboard.kTextPlain);
                final text = data?.text?.trim();
                if (text == null || text.isEmpty) return;
                _link.text = text;
              },
              child: const Text('붙여넣기'),
            ),
          ),
          const SizedBox(height: AppSpace.s2),
          SizedBox(
            height: AppLayout.minTouchTarget,
            child: OutlinedButton(
              onPressed: _entering ? null : _enterByLink,
              child: Text(_entering ? '들어가는 중…' : '링크로 입장'),
            ),
          ),
        ],
      ],
    );
  }
}

/// `19980315`
const _birthLength = 8;

/// 8자리가 진짜 날짜인가.
///
/// [DateTime] 은 넘치는 값을 다음 달로 넘겨 버려서(2월 30일 → 3월 2일) 만든 뒤
/// 되돌려 비교해야 걸러진다.
bool _looksLikeBirthdate(String text) {
  if (text.length != _birthLength) return false;
  final year = int.tryParse(text.substring(0, 4));
  final month = int.tryParse(text.substring(4, 6));
  final day = int.tryParse(text.substring(6, 8));
  if (year == null || month == null || day == null) return false;
  if (year < 1900 || year > DateTime.now().year) return false;

  final parsed = DateTime(year, month, day);
  return parsed.year == year && parsed.month == month && parsed.day == day;
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
    this.inputFormatters,
    this.onSubmitted,
  });

  final String label;
  final TextEditingController controller;
  final String hint;
  final bool obscureText;
  final TextInputType? keyboardType;
  final List<String>? autofillHints;

  /// 생년월일처럼 모양이 정해진 칸에 쓴다 — 숫자만·8자리
  final List<TextInputFormatter>? inputFormatters;

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
          inputFormatters: inputFormatters,
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
