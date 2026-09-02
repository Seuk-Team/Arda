import 'package:flutter/material.dart';

import '../api/api_error.dart';
import '../auth/auth_service.dart';
import '../auth/current_user.dart';
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
class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key, this.auth});

  /// 테스트가 가짜 서비스를 넣는 자리. 평소에는 null 이라 진짜가 만들어진다
  final AuthService? auth;

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
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
                    const SizedBox(height: AppSpace.s6),

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
                ),
              ),
            ),
          ),
        ),
      ),
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
      // ar.png 배경과 같은 흰색 (ar_screen.dart ArAvatar 주석 참고)
      decoration: const BoxDecoration(
        color: AppColors.bgElev,
        shape: BoxShape.circle,
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
