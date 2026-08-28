import 'package:flutter/material.dart';

import '../routes.dart';
import '../theme/tokens.dart';

/// 로그인 — `mockup-login.html` 을 옮긴 것.
///
/// 그 목업은 폭 360px 카드라 폰 화면에 그대로 맞는다. 모바일 전용 시안은 따로 없다.
///
/// **아직 진짜 로그인이 아니다.** 비밀번호를 검사하지 않고 바로 목록으로 넘어간다.
/// JWT 연동과 secure storage 는 큐 7번이고, 이 화면을 앱의 첫 화면으로 거는 것도
/// 그때다(지금은 검사 없는 통과라 첫 화면으로 두면 오히려 헷갈린다).
///
/// 확인은 `flutter run --route=/login` 으로 한다.
class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _email = TextEditingController();
  final _password = TextEditingController();

  @override
  void initState() {
    super.initState();
    // 목업 JS 와 같다 — 둘 다 채워야 버튼이 살아난다
    _email.addListener(_onChanged);
    _password.addListener(_onChanged);
  }

  void _onChanged() => setState(() {});

  @override
  void dispose() {
    _email.dispose();
    _password.dispose();
    super.dispose();
  }

  bool get _canSubmit =>
      _email.text.trim().isNotEmpty && _password.text.trim().isNotEmpty;

  void _submit() {
    // 큐 7번에서 POST /auth/login → 토큰 저장 → 실패 시 아래 오류 문구로 바뀐다
    Navigator.pushReplacementNamed(context, Routes.applicants);
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
                    const _Logo(),
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
                    const SizedBox(height: AppSpace.s4),

                    SizedBox(
                      // §9 터치 타깃 44 — 목업은 40이지만 그건 데스크톱 기준이다
                      height: AppLayout.minTouchTarget,
                      child: FilledButton(
                        onPressed: _canSubmit ? _submit : null,
                        child: const Text('로그인'),
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

/// 목업 `.logo` — 첫 글자 `A` 만 잎초록.
class _Logo extends StatelessWidget {
  const _Logo();

  @override
  Widget build(BuildContext context) {
    return const Text.rich(
      TextSpan(
        children: [
          TextSpan(text: 'A', style: TextStyle(color: AppColors.leaf)),
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
