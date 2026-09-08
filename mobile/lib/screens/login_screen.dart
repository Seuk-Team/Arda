import 'dart:ui' as ui;

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../api/api_error.dart';
import '../auth/auth_service.dart';
import '../auth/current_user.dart';
import '../data/applicant_portal_repository.dart';
import '../routes.dart';
import '../theme/tokens.dart';
import '../widgets/network_field.dart';

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
  const LoginScreen({super.key, this.auth, this.portal});

  /// 테스트가 가짜 서비스를 넣는 자리. 평소에는 null 이라 진짜가 만들어진다
  final AuthService? auth;

  /// 지원자 탭이 쓰는 것 — 같은 이유로 열어 둔다
  final ApplicantPortalRepository? portal;

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

/// 어느 쪽으로 들어오는가.
enum LoginRole { staff, applicant }

/// 인트로가 이번 실행에서 이미 지나갔는가.
///
/// **세션당 한 번이다** — 매번 나오면 통행세다(웹도 `sessionStorage` 로 같은
/// 규칙을 건다). 앱에서는 프로세스 수명이 곧 세션이라 최상위 변수로 충분하다:
/// 로그아웃하고 돌아와도 다시 돌지 않고, 앱을 껐다 켜면 다시 돈다.
bool _introSeen = false;

class _LoginScreenState extends State<LoginScreen>
    with SingleTickerProviderStateMixin {
  /// 담당자가 기본이다 — 지금 이 앱을 매일 켜는 사람이 담당자다.
  /// 지원자는 면접 때 한 번 들어오고, 그 뒤로는 런치 화면이 바로 보내 준다
  LoginRole _role = LoginRole.staff;

  /// 인트로 시계. 웹 `LoginIntro.tsx` 와 같은 길이·같은 간격이다
  AnimationController? _intro;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (_intro != null || _introSeen) return;

    // 05-design §5: 동작 줄이기면 연출을 돌리지 않는다. 여기서 판단해야
    // MediaQuery 를 읽을 수 있다(initState 에서는 아직 없다)
    if (MediaQuery.disableAnimationsOf(context)) {
      _introSeen = true;
      return;
    }
    _intro = AnimationController(vsync: this, duration: _kEnd)
      ..addStatusListener((s) {
        if (s == AnimationStatus.completed) _finishIntro();
      })
      ..forward();
  }

  @override
  void dispose() {
    _intro?.dispose();
    super.dispose();
  }

  /// 끝났거나 Skip. **다시는 안 돈다**
  void _finishIntro() {
    if (_intro == null) return;
    _introSeen = true;
    setState(() {
      _intro?.dispose();
      _intro = null;
    });
  }

  @override
  Widget build(BuildContext context) {
    final intro = _intro;
    return Scaffold(
      backgroundColor: AppColors.bg,
      body: Stack(
        children: [
          // 브랜드가 곧 배경이다 (05-design §0.0 딥 네트워크)
          Positioned.fill(
            child: intro == null
                ? const NetworkField()
                : AnimatedBuilder(
                    animation: intro,
                    builder: (_, _) =>
                        NetworkField(dim: _introDim(intro.value * _kEndMs)),
                  ),
          ),

          Positioned.fill(child: SafeArea(child: _card(intro))),

          if (intro != null)
            Positioned.fill(
              child: _IntroLayer(intro: intro, onSkip: _finishIntro),
            ),
        ],
      ),
    );
  }

  /// 로그인 카드. 인트로 끝에 **같은 문법으로** 떠오른다 — 왼쪽에서 슥
  Widget _card(AnimationController? intro) {
    final card = Center(
      child: SingleChildScrollView(
        padding: const EdgeInsets.all(AppSpace.s5),
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 360),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            mainAxisSize: MainAxisSize.min,
            children: [
              const _Brand(),
              const SizedBox(height: AppSpace.s5),
              _GlassCard(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    _RoleTabs(
                      role: _role,
                      onChanged: (r) => setState(() => _role = r),
                    ),
                    const SizedBox(height: AppSpace.s5),
                    if (_role == LoginRole.staff)
                      _StaffForm(auth: widget.auth)
                    else
                      _ApplicantForm(portal: widget.portal),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );

    if (intro == null) return card;
    return AnimationBuilderCard(intro: intro, child: card);
  }
}

/// 카드 등장 — 인트로가 끝날 무렵 왼쪽에서 슥 들어온다.
///
/// 별도 위젯인 이유: 이 애니메이션만 다시 그리면 되는데 화면 전체를
/// [AnimatedBuilder] 로 감싸면 폼까지 매 프레임 다시 만들어진다
class AnimationBuilderCard extends StatelessWidget {
  const AnimationBuilderCard({
    super.key,
    required this.intro,
    required this.child,
  });

  final AnimationController intro;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: intro,
      // child 를 밖에서 한 번만 만든다 — 매 프레임 폼을 새로 세우지 않는다
      child: child,
      builder: (_, built) {
        final ts = intro.value * _kEndMs - _kLead;
        final e = _kEase.transform(((ts - _kCardAt) / _kIn).clamp(0.0, 1.0));
        return Opacity(
          opacity: e,
          child: Transform.translate(
            offset: Offset(-72 * (1 - e), 0),
            child: Transform.scale(scale: .96 + .04 * e, child: built),
          ),
        );
      },
    );
  }
}

/// 브랜드 — 로고 + 이름. 로고는 노드 다섯과 연결선이 이루는 A 다 (§0.0)
class _Brand extends StatelessWidget {
  const _Brand();

  @override
  Widget build(BuildContext context) {
    return const Column(
      children: [
        BrandMark(size: 46),
        SizedBox(height: AppSpace.s3),
        _Logo(),
        SizedBox(height: AppSpace.s1),
        // 로고만 있으면 무슨 서비스인지 모른다
        Text(
          '채용 관리',
          textAlign: TextAlign.center,
          style: TextStyle(
            fontFamily: AppType.fontFamily,
            fontSize: AppType.sm,
            color: AppColors.textSub,
            // §2: 작은 글씨엔 그림자 금지
          ),
        ),
      ],
    );
  }
}

/// 유리 카드. **뒤가 비쳐야 한다** — 배경 노드망이 카드 밑으로 이어지는 것이
/// 보여야 브랜드가 화면 전체에 걸린다 (05-design §0.4 재질: 유리)
class _GlassCard extends StatelessWidget {
  const _GlassCard({required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) {
    return ClipRRect(
      borderRadius: AppShape.card,
      child: BackdropFilter(
        filter: ui.ImageFilter.blur(sigmaX: 18, sigmaY: 18),
        child: Container(
          padding: const EdgeInsets.all(AppSpace.s5),
          decoration: BoxDecoration(
            color: AppColors.bgElev,
            borderRadius: AppShape.card,
            border: Border.all(
              color: AppColors.border,
              width: AppShape.borderW,
            ),
          ),
          child: child,
        ),
      ),
    );
  }
}

/// ── 인트로 상수 ──────────────────────────────────────
///
/// 웹 `LoginIntro.tsx` 의 값을 그대로 쓴다. 길이도 간격도 같아야 두 화면이
/// 같은 연출로 읽힌다.
///
/// 진입(330)과 퇴장(190) 간격이 다른 이유: 퇴장은 가속 곡선이라 짧아도
/// "후-둑" 이 읽히지만, 진입은 감속 곡선이라 같은 간격이면 두 줄이 거의 함께
/// 도착해 한 덩어리로 보인다. 그래서 진입만 벌린다.
const _kEnd = Duration(milliseconds: 3600);
const _kEndMs = 3600.0;

/// 들어오기 전 한 박자. 이게 없으면 마운트와 등장이 겹쳐 "들어가자마자 이미
/// 떠 있는" 것처럼 보인다 — 슥 들어오는 동작 자체가 안 읽힌다
const _kLead = 620.0;
const _kIn = 672.0; // 진입 이징 길이
const _kEnterBeat = 330.0;
const _kLeaveBeat = 190.0;
const _kLeave = 2350.0;
const _kOut = 640.0;
const _kCardAt = 2920.0; // 카드가 떠오르기 시작하는 시각
/// 감광은 글자보다 살짝 먼저 걸린다 — 배경이 눌리는 것이 곧 예고다
const _kDimAt = _kLead - 360;

/// team.seuk.cloud 의 hero-enter 와 같은 곡선. 웹도 이것을 쓴다
const _kEase = Cubic(.2, .7, .2, 1);

/// 배경 감광 값. `t` 는 시퀀스 시작부터의 ms
double _introDim(double t) {
  final w = _kEase.transform(((t - _kDimAt) / 600).clamp(0.0, 1.0));
  final out = ((t - _kLead - (_kLeave + _kLeaveBeat)) / 640).clamp(0.0, 1.0);
  return (w - out).clamp(0.0, 1.0);
}

/// 시네마틱 인트로 — 세션당 1회.
///
/// 위에서부터 후두둑: 워드마크와 카피가 왼쪽에서 들어와 함께 서고, 같은
/// 순서·같은 간격으로 오른쪽으로 빠진다. 문법은 하나다 — 슥 들어옴 → 머묾 →
/// 가속 퇴장. 배경 감광은 [NetworkField] 가 같은 시계로 받는다.
class _IntroLayer extends StatelessWidget {
  const _IntroLayer({required this.intro, required this.onSkip});

  final AnimationController intro;
  final VoidCallback onSkip;

  @override
  Widget build(BuildContext context) {
    return Stack(
      children: [
        // 인트로는 화면을 덮지만 Skip 말고는 아무것도 안 받는다
        Positioned.fill(
          child: IgnorePointer(
            child: AnimatedBuilder(
              animation: intro,
              builder: (context, _) => _stack(intro.value * _kEndMs - _kLead),
            ),
          ),
        ),
        Positioned(
          top: AppSpace.s5,
          right: AppSpace.s5,
          child: SafeArea(child: _SkipButton(onTap: onSkip)),
        ),
      ],
    );
  }

  Widget _stack(double ts) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: AppSpace.s5),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            _sweep(
              ts,
              enter: 0,
              leave: _kLeave,
              dist: 460,
              child: const _Wordmark(),
            ),
            _sweep(
              ts,
              enter: _kEnterBeat,
              leave: _kLeave + _kLeaveBeat,
              dist: 380,
              child: const _Copy(),
            ),
          ],
        ),
      ),
    );
  }

  /// 한 덩어리의 문법: 슥 들어와(감속) → 머물고 → 가속하며 빠진다
  Widget _sweep(
    double ts, {
    required double enter,
    required double leave,
    required double dist,
    required Widget child,
  }) {
    double o = 0, dx = -dist;
    if (ts >= enter && ts < leave) {
      final e = _kEase.transform(((ts - enter) / _kIn).clamp(0.0, 1.0));
      o = e;
      dx = -dist * (1 - e);
    } else if (ts >= leave) {
      var q = ((ts - leave) / _kOut).clamp(0.0, 1.0);
      q = q * q; // 퇴장은 가속
      o = 1 - q;
      dx = (dist + 60) * q;
    }
    return Opacity(
      opacity: o,
      child: Transform.translate(offset: Offset(dx, 0), child: child),
    );
  }
}

/// 워드마크 — 그냥 글씨다. 배경 망이 유기적으로 빛나는 앞에 또렷한 타입이
/// 서야 둘 다 산다.
///
/// **크롬(금속)은 명암 밴딩으로 읽힌다.** 글자 잉크가 박스의 0.155~0.851 을
/// 차지하는 것에 맞춰 어두운 띠를 52% 에 둔다 — 웹과 같은 정지점이다.
class _Wordmark extends StatelessWidget {
  const _Wordmark();

  static const _chrome = LinearGradient(
    begin: Alignment.topCenter,
    end: Alignment.bottomCenter,
    colors: [
      Color(0xFFC9D8EC),
      Color(0xFFFFFFFF),
      Color(0xFF93A9C6),
      Color(0xFF63799B),
      Color(0xFFB9CCE4),
      Color(0xFFFFFFFF),
      Color(0xFF8497B4),
    ],
    stops: [0, .33, .46, .52, .60, .80, 1],
  );

  @override
  Widget build(BuildContext context) {
    return ShaderMask(
      shaderCallback: _chrome.createShader,
      blendMode: BlendMode.srcIn,
      child: const Text(
        'SEUK',
        style: TextStyle(
          fontFamily: AppType.fontFamily,
          fontSize: 64,
          // 번들한 굵기가 400·600 둘뿐이다(pubspec). 800 을 쓰면 600 으로
          // 떨어져 자간만 어긋나므로, 있는 것 중 제일 굵은 것을 쓴다
          fontWeight: AppType.wSemiBold,
          letterSpacing: -64 * .035,
          height: 1.05,
          color: Colors.white,
        ),
      ),
    );
  }
}

/// 소제목 + 설명은 한 세트 — 같이 들어오고 같이 빠진다.
///
/// **줄은 손으로 끊는다.** 폭이 335px 뿐이라 맡겨 두면 조사만 남거나
/// ("및" 한 글자 줄) 관형어와 체언이 갈라진다("하나의 / 플랫폼").
class _Copy extends StatelessWidget {
  const _Copy();

  @override
  Widget build(BuildContext context) {
    return const Padding(
      padding: EdgeInsets.only(top: 22),
      child: Column(
        children: [
          Text(
            'AI 기반 채용 프로세스 자동화 및\n지원자 통합 관리 플랫폼',
            textAlign: TextAlign.center,
            style: TextStyle(
              fontFamily: AppType.fontFamily,
              fontSize: AppType.h2,
              fontWeight: AppType.wSemiBold,
              letterSpacing: -AppType.h2 * .015,
              height: 1.45,
              color: Color(0xFFE4EDFF),
              shadows: [
                Shadow(color: Color(0x807DD3FC), blurRadius: 28),
                Shadow(color: Color(0x4760A5FA), blurRadius: 64),
              ],
            ),
          ),
          SizedBox(height: 14),
          Text(
            '이력서 AI 파싱, 칸반 보드,\n'
            'Tool-Calling Agent, RAG 질의응답까지 —\n'
            '채용 프로세스를\n'
            '하나의 플랫폼에서 자동화합니다.',
            textAlign: TextAlign.center,
            style: TextStyle(
              fontFamily: AppType.fontFamily,
              fontSize: AppType.sm,
              height: 1.75,
              color: Color(0xFFA8BCDC),
              shadows: [Shadow(color: Color(0x3860A5FA), blurRadius: 22)],
            ),
          ),
        ],
      ),
    );
  }
}

/// 매번 나오면 통행세다 — 빠져나갈 문을 늘 열어 둔다
class _SkipButton extends StatelessWidget {
  const _SkipButton({required this.onTap});

  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: const Color(0x0FFFFFFF),
      shape: const StadiumBorder(
        side: BorderSide(color: Color(0x2EFFFFFF), width: AppShape.borderW),
      ),
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: onTap,
        child: const Padding(
          padding: EdgeInsets.symmetric(
            horizontal: AppSpace.s4,
            vertical: AppSpace.s3,
          ),
          child: Text(
            'Skip →',
            style: TextStyle(
              fontFamily: AppType.fontFamily,
              fontSize: AppType.caption,
              fontWeight: AppType.wSemiBold,
              letterSpacing: .04 * AppType.caption,
              color: Color(0xFFCBD5E6),
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
  const _ApplicantForm({this.portal});

  final ApplicantPortalRepository? portal;

  @override
  State<_ApplicantForm> createState() => _ApplicantFormState();
}

class _ApplicantFormState extends State<_ApplicantForm> {
  final _email = TextEditingController();
  final _birth = TextEditingController();

  late final ApplicantPortalRepository _portal =
      widget.portal ?? ApplicantPortalRepository();

  bool _sending = false;
  String? _error;

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
    super.dispose();
  }

  bool get _canSubmit =>
      !_sending &&
      _email.text.trim().isNotEmpty &&
      _birth.text.length == _birthLength;

  Future<void> _submit() async {
    if (!_canSubmit) return;
    // 8자리를 채웠어도 날짜가 아닐 수 있다(19981345). 왕복 한 번을 아끼고,
    // 무엇이 틀렸는지도 여기서 더 정확히 말해 줄 수 있다 — 서버는 형식 오류도
    // 일부러 401 로만 답한다(떠보기 방지)
    if (!_looksLikeBirthdate(_birth.text)) {
      setState(() => _error = '생년월일을 다시 확인해 주세요. 예: 19980315');
      return;
    }

    setState(() {
      _sending = true;
      _error = null;
    });
    try {
      await _portal.login(email: _email.text.trim(), birthdate: _birth.text);
      if (!mounted) return;
      Navigator.pushReplacementNamed(context, Routes.applicantHome);
    } on ApiError catch (e) {
      // **서버 문구를 그대로 쓴다.** 없는 이메일·틀린 생년월일·생년월일 없는
      // 옛 지원서가 전부 같은 401 이고, 5회 실패하면 15분 잠긴다(429).
      // 앱이 사유를 지어내면 서버가 일부러 감춘 것을 도로 드러낸다
      if (!mounted) return;
      setState(() {
        _error = e.message;
        _sending = false;
      });
    } catch (e) {
      // 저장소가 죽는 것처럼 **예상 못 한 실패**. 여기서 안 받으면 스피너가
      // 영영 돌고 사용자가 할 수 있는 일이 없다
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
