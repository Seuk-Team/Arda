/// AI 면접 — 지원자용 (2026-09-08).
///
/// 05-design §0.5 에 없는 화면이다. 그 문서의 화면 지도는 담당자용이고,
/// 여기는 **계정 없는 사람이 링크로 들어와 보는 화면**이다. 그래서 탭바도
/// 아르 버튼도 없고, 상단 바에는 나가는 문 하나만 있다.
///
/// ## 카메라가 계속 켜져 있는 것이 이 화면의 핵심이다
///
/// 한 번 찍어 올리는 것과 결과가 다르다(에이전트 도메인 요청서 2026-09-07):
/// 다시 찍기가 없고, 본인 확인이 면접 내내 이어지고, 표정이 답변 중간에
/// 끊기지 않는다. 그래서 동의가 끝나는 순간부터 종료까지 카메라를 놓지 않는다 —
/// 질문마다 켰다 끄면 위 셋이 다 무너진다.
///
/// **아르 얼굴이나 목소리는 나오지 않는다.** 질문은 글로 뜨고 지원자가 답한다
/// (ADR-0004: 음성은 STT 만, TTS 없음). "영상통화 같다" 는 것은 카메라가
/// 계속 켜져 있고 대화가 끊기지 않는다는 뜻이지 양쪽 얼굴이 보인다는 뜻이 아니다.
///
/// ## 지금 답변은 글로 낸다
///
/// 카메라는 켜져 있지만 **답변 전송은 아직 텍스트다.** 음성·영상 업로드
/// (`audio-upload-url` → S3 → `answer`)는 다음 조각이고, 실시간 전송(WebSocket)은
/// 서버가 아직 없다. 텍스트 경로(`POST .../answer {transcript}`)는 이미 열려
/// 있어서, 이것만으로도 면접이 끝까지 돈다 — 답을 못 내는 면접 화면을 두는
/// 것보다 낫다.
///
/// ## 분석 결과는 지원자에게 안 보인다
///
/// 화면에 나오는 것은 질문과 진행 상태뿐이다. 진행 보조(`pacing`)는 점수가
/// 아니라 "다음에 할 행동" 한 문장이고 서버가 저장하지도 않는다.
library;

import 'package:flutter/material.dart';

import '../api/api_error.dart';
import '../data/applicant_portal_repository.dart';
import '../data/camera_service.dart';
import '../models/applicant_portal.dart';
import '../theme/tokens.dart';
import '../widgets/app_top_bar.dart';

class InterviewScreen extends StatefulWidget {
  const InterviewScreen({
    super.key,
    required this.token,
    this.portal,
    this.camera,
  });

  final String token;

  /// 테스트가 가짜를 넣는 자리. 카메라는 실기기가 없으면 못 여니
  /// **테스트에서는 반드시 가짜를 넣어야 한다**
  final ApplicantPortalRepository? portal;
  final CameraService? camera;

  @override
  State<InterviewScreen> createState() => _InterviewScreenState();
}

class _InterviewScreenState extends State<InterviewScreen>
    with WidgetsBindingObserver {
  late final ApplicantPortalRepository _portal =
      widget.portal ?? ApplicantPortalRepository();
  late final CameraService _camera = widget.camera ?? DeviceCameraService();

  /// 테스트가 넣어 준 카메라는 테스트가 치운다 — 우리가 만든 것만 우리가 닫는다
  late final bool _ownsCamera = widget.camera == null;

  final _answer = TextEditingController();

  InterviewPublic? _data;
  String? _error;

  /// 서버에 뭔가 보내는 중 — 버튼을 잠근다
  bool _sending = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _camera.addListener(_onCamera);
    _answer.addListener(_onTyping);
    _load();
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _camera.removeListener(_onCamera);
    // 나가는 길이 여럿(뒤로가기·완료·오류)이라 여기 한 곳에서 확실히 놓아 준다.
    // 안 그러면 화면을 나가도 카메라 표시등이 계속 켜져 있다
    if (_ownsCamera) _camera.dispose();
    _answer.dispose();
    super.dispose();
  }

  void _onCamera() {
    if (mounted) setState(() {});
  }

  void _onTyping() {
    // 제출 버튼이 살아나는지만 보면 된다. 매 글자 setState 는 아깝지만
    // 이 화면에 다른 무거운 것이 없다
    if (mounted) setState(() {});
  }

  /// **앱을 벗어나면 안드로이드가 카메라를 뺏는다.** 전화 한 통이 오면 돌아왔을
  /// 때 미리보기가 검은 화면으로 남는다 — 그래서 나갈 때 놓고 돌아올 때 다시 연다.
  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    switch (state) {
      case AppLifecycleState.paused:
      case AppLifecycleState.hidden:
      case AppLifecycleState.detached:
        _camera.stop();
      case AppLifecycleState.resumed:
        if (_wantsCamera) _camera.start();
      case AppLifecycleState.inactive:
        // 알림 그림자가 잠깐 내려온 것 같은 상태다. 여기서 끄면 깜빡인다
        break;
    }
  }

  /// 지금 카메라가 켜져 있어야 하는가. **동의가 끝난 순간부터 종료까지다**
  bool get _wantsCamera => switch (_data?.status) {
    InterviewStatus.pending => _data?.consentRequired == false,
    InterviewStatus.inProgress => true,
    _ => false,
  };

  Future<void> _load() async {
    setState(() => _error = null);
    try {
      final data = await _portal.interview(widget.token);
      if (!mounted) return;
      _apply(data);
    } on ApiError catch (e) {
      if (!mounted) return;
      setState(() => _error = e.message);
    }
  }

  /// 받아 온 것을 화면에 얹고, 카메라를 그 상태에 맞춘다.
  ///
  /// **응답을 그대로 쓴다.** 다시 조회하면 진행 보조가 사라진다 — 서버가
  /// 저장하지 않아 조회에는 안 실린다(웹 `Interview.tsx` 와 같은 처리)
  void _apply(InterviewPublic data) {
    setState(() {
      _data = data;
      _sending = false;
    });
    if (_wantsCamera) {
      _camera.start();
    } else {
      _camera.stop();
    }
  }

  Future<void> _send(Future<InterviewPublic> Function() call) async {
    if (_sending) return;
    setState(() {
      _sending = true;
      _error = null;
    });
    try {
      final next = await call();
      if (!mounted) return;
      _apply(next);
    } on ApiError catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e.message;
        _sending = false;
      });
    }
  }

  Future<void> _submitAnswer() async {
    final text = _answer.text.trim();
    if (text.isEmpty) return;
    await _send(() => _portal.answer(widget.token, text));
    if (mounted) _answer.clear();
  }

  Future<void> _finish() async {
    final ok = await showInterviewFinishSheet(context);
    if (ok != true || !mounted) return;
    await _send(() => _portal.finish(widget.token));
  }

  @override
  Widget build(BuildContext context) {
    final data = _data;
    return Scaffold(
      appBar: const AppTopBar(title: 'AI 면접', showBack: true),
      body: SafeArea(
        child: data == null
            ? _Center(
                child: _error == null
                    ? const _Loading()
                    : _Failed(message: _error!, onRetry: _load),
              )
            : _body(data),
      ),
    );
  }

  Widget _body(InterviewPublic data) {
    return ListView(
      padding: const EdgeInsets.all(AppSpace.s4),
      children: [
        Text(
          data.postingTitle,
          style: const TextStyle(
            fontFamily: AppType.fontFamily,
            fontSize: AppType.sm,
            color: AppColors.textSub,
          ),
        ),
        const SizedBox(height: AppSpace.s1),
        Text(
          '${data.applicantName}님',
          style: const TextStyle(
            fontFamily: AppType.fontFamily,
            fontSize: AppType.h2,
            fontWeight: AppType.wSemiBold,
            color: AppColors.text,
            shadows: AppTextShadow.heading,
          ),
        ),
        const SizedBox(height: AppSpace.s4),

        // 카메라는 동의 뒤부터 켠다 — 화면에 들어오자마자 권한을 요구하면
        // 무엇을 하는 앱인지도 모르고 거부당한다
        if (_wantsCamera) ...[
          _CameraBox(camera: _camera),
          const SizedBox(height: AppSpace.s4),
        ],

        switch (data.status) {
          InterviewStatus.pending when data.consentRequired => _Consent(
            busy: _sending,
            onAgree: () => _send(() => _portal.consent(widget.token)),
          ),
          InterviewStatus.pending => _Ready(
            busy: _sending,
            ready: _camera.status == CameraStatus.live,
            onStart: () => _send(() => _portal.start(widget.token)),
          ),
          InterviewStatus.inProgress => _Question(
            data: data,
            controller: _answer,
            busy: _sending,
            onSubmit: _submitAnswer,
            onFinish: _finish,
          ),
          InterviewStatus.done => const _Done(),
          InterviewStatus.expired => const _Expired(),
        },

        if (_error != null) ...[
          const SizedBox(height: AppSpace.s4),
          _Note(text: _error!, tone: AppColors.danger),
        ],
      ],
    );
  }
}

/// 미리보기 상자. 켜지는 중·거부·실패까지 여기서 다 그린다 —
/// **꺼진 것을 조용히 넘기지 않는다.** 카메라가 죽은 줄 모르고 말하면
/// 그 면접은 다시 볼 수 없다
class _CameraBox extends StatelessWidget {
  const _CameraBox({required this.camera});

  final CameraService camera;

  @override
  Widget build(BuildContext context) {
    return ClipRRect(
      borderRadius: AppShape.card,
      child: Container(
        height: 240,
        width: double.infinity,
        color: AppColors.bgSunken,
        child: switch (camera.status) {
          CameraStatus.live => Stack(
            fit: StackFit.expand,
            children: [
              FittedBox(
                fit: BoxFit.cover,
                child: _Sized(child: camera.buildPreview()),
              ),
              const Positioned(
                left: AppSpace.s3,
                top: AppSpace.s3,
                child: _LiveDot(),
              ),
            ],
          ),
          CameraStatus.starting => const Center(
            child: CircularProgressIndicator(strokeWidth: 2),
          ),
          _ => _CameraBlocked(camera: camera),
        },
      ),
    );
  }
}

/// `FittedBox` 안에서 미리보기가 크기를 못 정하는 경우를 막는다
class _Sized extends StatelessWidget {
  const _Sized({required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) =>
      SizedBox(width: 720, height: 1280, child: child);
}

/// 촬영 중 표시. **켜져 있다는 것이 늘 보여야 한다** — 지원자가 자기가 찍히고
/// 있는지 모른 채 말하게 두면 안 된다
class _LiveDot extends StatelessWidget {
  const _LiveDot();

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: AppColors.bgChrome,
        borderRadius: AppShape.pill,
        border: Border.all(color: AppColors.border, width: AppShape.borderW),
      ),
      child: const Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(Icons.fiber_manual_record, size: 10, color: AppColors.danger),
          SizedBox(width: 6),
          Text(
            '촬영 중',
            style: TextStyle(
              fontFamily: AppType.fontFamily,
              fontSize: AppType.caption,
              fontWeight: AppType.wSemiBold,
              color: AppColors.text,
            ),
          ),
        ],
      ),
    );
  }
}

class _CameraBlocked extends StatelessWidget {
  const _CameraBlocked({required this.camera});

  final CameraService camera;

  @override
  Widget build(BuildContext context) {
    final settings = camera.status == CameraStatus.deniedForever;
    return Padding(
      padding: const EdgeInsets.all(AppSpace.s4),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          const Icon(
            Icons.videocam_off_outlined,
            size: 28,
            color: AppColors.neutral,
          ),
          const SizedBox(height: AppSpace.s2),
          Text(
            camera.message ?? '카메라가 꺼져 있습니다.',
            textAlign: TextAlign.center,
            style: const TextStyle(
              fontFamily: AppType.fontFamily,
              fontSize: AppType.sm,
              color: AppColors.textSub,
            ),
          ),
          const SizedBox(height: AppSpace.s3),
          SizedBox(
            height: AppLayout.minTouchTarget,
            child: OutlinedButton(
              onPressed: settings ? camera.openSettings : camera.start,
              child: Text(settings ? '설정 열기' : '다시 시도'),
            ),
          ),
        ],
      ),
    );
  }
}

/// 동의. **면접 시작의 선행 조건이다** — 지원 폼에서 받은 개인정보 동의와
/// 별개다(그때는 녹음이 없었다).
class _Consent extends StatelessWidget {
  const _Consent({required this.busy, required this.onAgree});

  final bool busy;
  final VoidCallback onAgree;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const Text(
          '면접 안내',
          style: TextStyle(
            fontFamily: AppType.fontFamily,
            fontSize: AppType.body,
            fontWeight: AppType.wSemiBold,
            color: AppColors.text,
          ),
        ),
        const SizedBox(height: AppSpace.s3),
        // **실제 동작과 맞는 것만 적는다.** 영상 보관 여부는 아직 정해지지
        // 않아서(에이전트 도메인과 협의 중) 여기에 "저장하지 않습니다" 를
        // 적지 않는다 — 사실이 아닌 동의 문구는 없느니만 못하다
        const Text(
          '질문은 글로 표시되고, 답변은 채용 검토 목적으로만 활용됩니다.\n'
          '면접 중에는 본인 확인을 위해 카메라가 켜져 있습니다.',
          style: TextStyle(
            fontFamily: AppType.fontFamily,
            fontSize: AppType.sm,
            height: 1.6,
            color: AppColors.textSub,
          ),
        ),
        const SizedBox(height: AppSpace.s5),
        SizedBox(
          height: AppLayout.minTouchTarget,
          child: FilledButton(
            onPressed: busy ? null : onAgree,
            child: Text(busy ? '처리 중…' : '동의하고 계속하기'),
          ),
        ),
      ],
    );
  }
}

class _Ready extends StatelessWidget {
  const _Ready({
    required this.busy,
    required this.ready,
    required this.onStart,
  });

  final bool busy;

  /// 카메라가 켜졌는가. **꺼진 채로 시작하게 두지 않는다** — 시작하면 첫 질문이
  /// 나오고, 그때부터는 다시 찍기가 없다
  final bool ready;

  final VoidCallback onStart;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text(
          ready ? '준비되셨으면 시작해 주세요. 첫 번째 질문이 표시됩니다.' : '카메라가 켜지면 시작할 수 있습니다.',
          style: const TextStyle(
            fontFamily: AppType.fontFamily,
            fontSize: AppType.sm,
            height: 1.6,
            color: AppColors.textSub,
          ),
        ),
        const SizedBox(height: AppSpace.s4),
        SizedBox(
          height: AppLayout.minTouchTarget,
          child: FilledButton(
            onPressed: (busy || !ready) ? null : onStart,
            child: Text(busy ? '시작 중…' : '면접 시작'),
          ),
        ),
      ],
    );
  }
}

class _Question extends StatelessWidget {
  const _Question({
    required this.data,
    required this.controller,
    required this.busy,
    required this.onSubmit,
    required this.onFinish,
  });

  final InterviewPublic data;
  final TextEditingController controller;
  final bool busy;
  final VoidCallback onSubmit;
  final VoidCallback onFinish;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        // 진행 보조 — 앞 답변을 듣고 건네는 말. **경고처럼 보이게 하지 않는다**:
        // 지적이 아니라 배려다. 점수가 아니고 저장되지도 않는다
        if (data.pacing != null) ...[
          _Note(text: data.pacing!, tone: AppColors.accentText),
          const SizedBox(height: AppSpace.s3),
        ],

        // 몇 번째인지만 적는다 — **전체가 몇 개인지는 서버가 주지 않는다**
        // (`InterviewPublicOut` 에 총 문항 수가 없다). 지어내 적지 않는다
        if (data.questionSeq != null)
          Text(
            '질문 ${data.questionSeq}',
            style: const TextStyle(
              fontFamily: AppType.fontFamily,
              fontSize: AppType.caption,
              fontWeight: AppType.wSemiBold,
              fontFeatures: AppType.tabularNums,
              color: AppColors.textSub,
            ),
          ),
        const SizedBox(height: AppSpace.s2),
        Text(
          data.currentQuestion ?? '',
          style: const TextStyle(
            fontFamily: AppType.fontFamily,
            fontSize: AppType.h2,
            height: 1.5,
            color: AppColors.text,
          ),
        ),
        const SizedBox(height: AppSpace.s4),

        TextField(
          controller: controller,
          maxLines: 5,
          minLines: 3,
          enabled: !busy,
          textInputAction: TextInputAction.newline,
          style: const TextStyle(
            fontFamily: AppType.fontFamily,
            fontSize: AppType.sm,
            height: 1.6,
            color: AppColors.text,
          ),
          decoration: const InputDecoration(hintText: '답변을 입력해 주세요'),
        ),
        const SizedBox(height: AppSpace.s3),

        SizedBox(
          height: AppLayout.minTouchTarget,
          child: FilledButton(
            onPressed: (busy || controller.text.trim().isEmpty)
                ? null
                : onSubmit,
            child: Text(busy ? '보내는 중…' : '답변 제출'),
          ),
        ),
        const SizedBox(height: AppSpace.s3),
        SizedBox(
          height: AppLayout.minTouchTarget,
          child: OutlinedButton(
            onPressed: busy ? null : onFinish,
            child: const Text('면접 종료'),
          ),
        ),
      ],
    );
  }
}

class _Done extends StatelessWidget {
  const _Done();

  @override
  Widget build(BuildContext context) =>
      const _Note(text: '면접이 완료되었습니다. 참여해 주셔서 감사합니다.', tone: AppColors.okText);
}

class _Expired extends StatelessWidget {
  const _Expired();

  @override
  Widget build(BuildContext context) => const _Note(
    text: '링크 유효 기간이 지났습니다. 담당자에게 문의해 주세요.',
    tone: AppColors.danger,
  );
}

class _Note extends StatelessWidget {
  const _Note({required this.text, required this.tone});

  final String text;
  final Color tone;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(AppSpace.s3),
      decoration: BoxDecoration(
        color: AppColors.bgSunken,
        borderRadius: AppShape.ctl,
        border: Border.all(
          color: AppColors.borderSoft,
          width: AppShape.borderW,
        ),
      ),
      child: Text(
        text,
        style: TextStyle(
          fontFamily: AppType.fontFamily,
          fontSize: AppType.sm,
          height: 1.6,
          color: tone,
        ),
      ),
    );
  }
}

class _Center extends StatelessWidget {
  const _Center({required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) => Center(
    child: Padding(padding: const EdgeInsets.all(AppSpace.s5), child: child),
  );
}

class _Loading extends StatelessWidget {
  const _Loading();

  @override
  Widget build(BuildContext context) => const Column(
    mainAxisSize: MainAxisSize.min,
    children: [
      CircularProgressIndicator(strokeWidth: 2),
      SizedBox(height: AppSpace.s3),
      Text(
        '불러오는 중…',
        style: TextStyle(
          fontFamily: AppType.fontFamily,
          fontSize: AppType.sm,
          color: AppColors.textSub,
        ),
      ),
    ],
  );
}

class _Failed extends StatelessWidget {
  const _Failed({required this.message, required this.onRetry});

  final String message;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Text(
          message,
          textAlign: TextAlign.center,
          style: const TextStyle(
            fontFamily: AppType.fontFamily,
            fontSize: AppType.sm,
            color: AppColors.danger,
          ),
        ),
        const SizedBox(height: AppSpace.s4),
        SizedBox(
          height: AppLayout.minTouchTarget,
          child: OutlinedButton(onPressed: onRetry, child: const Text('다시 시도')),
        ),
      ],
    );
  }
}

/// 종료 확인. **되돌릴 수 없다** — 끝내면 남은 질문에 답할 수 없다.
/// 공고 삭제 시트와 같은 모양이다(§3 동종 요소 동일 규격)
Future<bool?> showInterviewFinishSheet(BuildContext context) {
  return showModalBottomSheet<bool>(
    context: context,
    backgroundColor: AppColors.bgElev,
    showDragHandle: true,
    shape: const RoundedRectangleBorder(
      borderRadius: BorderRadius.vertical(top: AppShape.rCard),
    ),
    builder: (sheetContext) => SafeArea(
      top: false,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(
          AppSpace.s5,
          0,
          AppSpace.s5,
          AppSpace.s5,
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          mainAxisSize: MainAxisSize.min,
          children: [
            const Text(
              '면접 종료',
              style: TextStyle(
                fontFamily: AppType.fontFamily,
                fontSize: AppType.h2,
                fontWeight: FontWeight.w700,
                color: AppColors.text,
                shadows: AppTextShadow.heading,
              ),
            ),
            const SizedBox(height: AppSpace.s1),
            const Text(
              '면접을 끝냅니다. 남은 질문에는 답할 수 없습니다.',
              style: TextStyle(
                fontFamily: AppType.fontFamily,
                fontSize: AppType.sm,
                height: 1.5,
                color: AppColors.danger,
              ),
            ),
            const SizedBox(height: AppSpace.s4),
            Row(
              children: [
                Expanded(
                  child: SizedBox(
                    height: AppLayout.minTouchTarget,
                    child: OutlinedButton(
                      onPressed: () => Navigator.pop(sheetContext, false),
                      child: const Text('취소'),
                    ),
                  ),
                ),
                const SizedBox(width: AppSpace.s3),
                Expanded(
                  child: SizedBox(
                    height: AppLayout.minTouchTarget,
                    child: FilledButton(
                      style: FilledButton.styleFrom(
                        backgroundColor: AppColors.danger,
                      ),
                      onPressed: () => Navigator.pop(sheetContext, true),
                      child: const Text('종료'),
                    ),
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    ),
  );
}
