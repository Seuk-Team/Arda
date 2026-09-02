/// 앱을 켤 때 제일 먼저 뜨는 화면 — **저장된 토큰이 아직 쓸 수 있는지** 묻는다.
///
/// 토큰이 12시간짜리라, 켤 때마다 로그인시키면 그 12시간이 의미가 없다.
/// 여기서 `GET /auth/me` 로 확인하고 홈이나 로그인으로 갈라 보낸다.
///
/// **네트워크가 끊긴 것은 로그아웃이 아니다.** 지하철에서 앱을 켰다고 토큰을
/// 버리면 안 되므로, 못 닿았을 때는 다시 시도할 자리를 준다(05-design §6 오류).
library;

import 'package:flutter/material.dart';

import '../api/api_error.dart';
import '../auth/auth_service.dart';
import '../auth/current_user.dart';
import '../routes.dart';
import '../theme/tokens.dart';

class LaunchScreen extends StatefulWidget {
  const LaunchScreen({super.key, this.auth});

  final AuthService? auth;

  @override
  State<LaunchScreen> createState() => _LaunchScreenState();
}

class _LaunchScreenState extends State<LaunchScreen> {
  late final AuthService _auth = widget.auth ?? AuthService();

  /// 서버에 못 닿았을 때만 채워진다. 토큰이 없거나 만료된 경우는
  /// 화면을 그리지 않고 곧장 로그인으로 넘어간다
  String? _error;

  @override
  void initState() {
    super.initState();
    _restore();
  }

  Future<void> _restore() async {
    setState(() => _error = null);
    try {
      final user = await _auth.restore();
      if (!mounted) return;
      if (user != null) CurrentUserScope.notifierOf(context)?.value = user;
      Navigator.pushReplacementNamed(
        context,
        user == null ? Routes.login : Routes.home,
      );
    } on ApiError catch (e) {
      // 여기 오는 것은 사실상 NetworkError 뿐이다 — AuthExpired 는 restore 가
      // null 로 바꿔 준다
      if (!mounted) return;
      setState(() => _error = e.message);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.bg,
      body: Center(
        child: Padding(
          padding: const EdgeInsets.all(AppSpace.s5),
          child: _error == null
              // 확인하는 동안. 대개 한 번 깜빡이고 지나간다
              ? const CircularProgressIndicator(color: AppColors.leaf)
              : Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(
                      _error!,
                      textAlign: TextAlign.center,
                      style: const TextStyle(
                        fontFamily: AppType.fontFamily,
                        fontSize: AppType.sm,
                        height: 1.5,
                        color: AppColors.textSub,
                      ),
                    ),
                    const SizedBox(height: AppSpace.s4),
                    // 앱엔 F5 가 없다 — 문구만 띄우면 할 수 있는 게 없다
                    SizedBox(
                      height: AppLayout.minTouchTarget,
                      child: FilledButton(
                        onPressed: _restore,
                        child: const Text('다시 시도'),
                      ),
                    ),
                    const SizedBox(height: AppSpace.s2),
                    // 그래도 안 되면 로그인으로 빠져나갈 길을 준다
                    TextButton(
                      onPressed: () =>
                          Navigator.pushReplacementNamed(context, Routes.login),
                      child: const Text('로그인 화면으로'),
                    ),
                  ],
                ),
        ),
      ),
    );
  }
}
