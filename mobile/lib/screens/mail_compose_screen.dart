/// 메일 쓰기 — 지원자 상세의 메일 버튼 넷에서 들어온다 (큐 8 3단계, 2026-09-03).
///
/// **이 앱에서 유일하게 되돌릴 수 없는 화면이다.** 메모·평가·공고는 다 고칠 수
/// 있지만 메일은 나가면 지원자 메일함에 들어간다 — 큐에 쌓이는 것이 아니라
/// SES 로 실제 발송된다(`backend/app/worker.py`).
///
/// 그래서 웹과 같은 3단계를 그대로 지킨다: 프리셋 → 편집 → **확인**.
/// 웹은 오른쪽 패널 안에서 펴지지만 앱은 별도 화면이다 — 375px 에 제목 칸과
/// 본문 10줄을 상세 안에 끼우면 그 아래가 전부 밀린다.
///
/// **받는 사람은 화면에 없다.** 서버가 `application.email` 로 고정하므로 앱이
/// 주소를 보내지도 못하고, 띄운다고 막을 수 있는 실수가 없다. 잘못 보내는 길은
/// "다른 사람 화면에서 눌렀다" 하나뿐이고 그건 **이름**이 잡는다 — 지원자 개인
/// 이메일을 덮어씌우는 시트에 올릴 이유가 그만큼 약하다(웹도 안 띄운다).
library;

import 'package:flutter/material.dart';

import '../api/api_error.dart';
import '../auth/authed_client.dart';
import '../data/applicant_repository.dart';
import '../data/repositories.dart';
import '../theme/tokens.dart';
import '../widgets/app_top_bar.dart';
import '../widgets/async_view.dart';

/// 메일 프리셋 — 웹 `MAIL_PRESETS` 와 같은 순서·같은 이름.
enum MailPreset {
  interview('interview', '면접 안내', false),
  applied('applied', '접수 확인', false),
  accepted('accepted', '최종 합격', false),

  /// **불합격만 적갈** (§1 색은 판단에만). 되돌릴 수 없는 메일이라
  /// 나머지와 같은 무채로 두면 잘못 누른다
  rejected('rejected', '불합격', true);

  const MailPreset(this.stage, this.label, this.danger);

  /// `?stage=` 로 서버에 넘기는 값
  final String stage;
  final String label;
  final bool danger;
}

class MailComposeScreen extends StatefulWidget {
  const MailComposeScreen({
    super.key,
    required this.applicationId,
    required this.applicantName,
    required this.preset,
    this.repository,
  });

  final int applicationId;

  /// 확인 시트가 "누구에게" 를 적을 때 쓴다
  final String applicantName;

  final MailPreset preset;

  /// 테스트가 가짜를 넣는 자리
  final ApplicantRepository? repository;

  @override
  State<MailComposeScreen> createState() => _MailComposeScreenState();
}

class _MailComposeScreenState extends State<MailComposeScreen> {
  late ApplicantRepository _repo;
  late Future<({String subject, String body})> _future;

  final _subject = TextEditingController();
  final _body = TextEditingController();

  bool _sending = false;

  @override
  void initState() {
    super.initState();
    _repo =
        widget.repository ??
        RepositoryScope.of(context)?.applicants ??
        ApplicantRepository(authedClient());
    _future = _load();

    for (final c in [_subject, _body]) {
      c.addListener(() => setState(() {}));
    }
  }

  /// 프리필을 받아 입력칸에 넣는다.
  ///
  /// **[AsyncView] 의 builder 안에서 채우면 안 된다** — 컨트롤러에 글자를 넣는
  /// 순간 리스너가 돌고, 그게 빌드 도중의 `setState` 가 되어 터진다.
  /// 받아온 뒤(빌드 밖)에 채운다.
  ///
  /// `ignore()` 이유는 postings_screen.dart 참고 — 오류 표시는 AsyncView 가 한다
  Future<({String subject, String body})> _load() {
    final future = _repo.mailPreview(widget.applicationId, widget.preset.stage);
    future.then((preview) {
      if (!mounted) return;
      _subject.text = preview.subject;
      _body.text = preview.body;
    }).ignore();
    return future;
  }

  void _reload() {
    setState(() {
      _future = _load();
    });
  }

  @override
  void dispose() {
    for (final c in [_subject, _body]) {
      c.dispose();
    }
    super.dispose();
  }

  bool get _canSend =>
      !_sending &&
      _subject.text.trim().isNotEmpty &&
      _body.text.trim().isNotEmpty;

  /// [보내기] → 확인 시트 → [발송]. 시트를 한 번 거치는 이유는 단계 변경과
  /// 같되 더 강하다 — 단계는 되돌릴 수 있지만 메일은 못 되돌린다.
  Future<void> _confirmAndSend() async {
    final messenger = ScaffoldMessenger.of(context);
    final navigator = Navigator.of(context);

    final ok = await showMailConfirmSheet(
      context,
      applicantName: widget.applicantName,
      preset: widget.preset,
      subject: _subject.text.trim(),
      body: _body.text,
    );
    if (ok != true || !mounted) return;

    setState(() => _sending = true);

    try {
      await _repo.sendMail(
        widget.applicationId,
        subject: _subject.text.trim(),
        body: _body.text,
      );
      if (!mounted) return;

      // `true` 는 "메일 이력을 다시 받아라" 는 신호다
      navigator.pop(true);
      messenger.showSnackBar(
        SnackBar(content: Text('${widget.applicantName} 님에게 메일을 보냈습니다')),
      );
    } on ApiError catch (e) {
      if (!mounted) return;
      // 화면을 닫지 않는다 — 고쳐 쓴 본문이 다 사라진다
      setState(() => _sending = false);
      messenger.showSnackBar(SnackBar(content: Text(e.message)));
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.bg,
      appBar: AppTopBar(title: widget.preset.label, showBack: true),
      body: AsyncView<({String subject, String body})>(
        future: _future,
        onRetry: _reload,
        emptyMessage: '',
        // 입력칸 채우기는 [_load] 가 이미 했다 — 여기서 하면 빌드 도중 setState 다
        builder: (context, _) => _form(),
      ),
    );
  }

  Widget _form() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Expanded(
          child: ListView(
            padding: const EdgeInsets.all(AppSpace.s4),
            children: [
              _Label('제목'),
              const SizedBox(height: AppSpace.s2),
              TextField(
                controller: _subject,
                enabled: !_sending,
                style: _text,
                decoration: _decoration(),
              ),
              const SizedBox(height: AppSpace.s4),

              _Label('본문'),
              const SizedBox(height: AppSpace.s2),
              TextField(
                controller: _body,
                enabled: !_sending,
                // 폰이라 웹의 10줄보다 짧게 잡고 스크롤에 맡긴다
                minLines: 8,
                maxLines: 20,
                style: _text,
                decoration: _decoration(),
              ),
              const SizedBox(height: AppSpace.s3),
              const Text(
                '{회사명} 같은 자리는 서버가 채웁니다. 지우지 마세요.',
                style: TextStyle(
                  fontFamily: AppType.fontFamily,
                  fontSize: AppType.caption,
                  height: 1.5,
                  color: AppColors.textSub,
                ),
              ),
            ],
          ),
        ),
        _SendBar(
          danger: widget.preset.danger,
          enabled: _canSend,
          sending: _sending,
          onSend: _confirmAndSend,
        ),
      ],
    );
  }
}

const _text = TextStyle(
  fontFamily: AppType.fontFamily,
  fontSize: AppType.body,
  height: 1.6,
  color: AppColors.text,
);

class _Label extends StatelessWidget {
  const _Label(this.text);

  final String text;

  @override
  Widget build(BuildContext context) => Text(
    text,
    style: const TextStyle(
      fontFamily: AppType.fontFamily,
      fontSize: AppType.sm,
      fontWeight: AppType.wSemiBold,
      color: AppColors.text,
    ),
  );
}

/// 05-design §4: 인풋은 sunken 바탕.
InputDecoration _decoration() {
  const outline = OutlineInputBorder(
    borderRadius: AppShape.ctl,
    borderSide: BorderSide(color: AppColors.border, width: AppShape.borderW),
  );

  return const InputDecoration(
    isDense: true,
    filled: true,
    fillColor: AppColors.bgSunken,
    contentPadding: EdgeInsets.all(AppSpace.s3),
    border: outline,
    enabledBorder: outline,
    disabledBorder: outline,
    focusedBorder: OutlineInputBorder(
      borderRadius: AppShape.ctl,
      borderSide: BorderSide(color: AppColors.leaf, width: AppShape.borderW),
    ),
  );
}

/// 화면 아래 [보내기] — 상세의 [단계 변경] 과 같은 자리·같은 높이.
class _SendBar extends StatelessWidget {
  const _SendBar({
    required this.danger,
    required this.enabled,
    required this.sending,
    required this.onSend,
  });

  final bool danger;
  final bool enabled;
  final bool sending;
  final VoidCallback onSend;

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: const BoxDecoration(
        color: AppColors.bgElev,
        border: Border(
          top: BorderSide(color: AppColors.border, width: AppShape.borderW),
        ),
      ),
      // SafeArea 를 높이 제약 바깥에 둔다 — 안쪽이면 내비게이션 바가 차지하는
      // 만큼 72 안에서 깎여 버튼 위아래 여백이 사라진다
      child: SafeArea(
        top: false,
        child: Container(
          constraints: const BoxConstraints(minHeight: 72),
          padding: const EdgeInsets.symmetric(horizontal: AppSpace.s5),
          alignment: Alignment.center,
          child: SizedBox(
            width: double.infinity,
            height: AppLayout.minTouchTarget,
            child: FilledButton(
              style: danger
                  ? FilledButton.styleFrom(backgroundColor: AppColors.danger)
                  : null,
              onPressed: enabled ? onSend : null,
              child: sending
                  ? const SizedBox(
                      width: 20,
                      height: 20,
                      child: CircularProgressIndicator(
                        strokeWidth: 2,
                        color: AppColors.bgElev,
                      ),
                    )
                  : const Text('보내기'),
            ),
          ),
        ),
      ),
    );
  }
}

/// 발송 확인 — **여기가 마지막 문**이다.
///
/// 단계 변경 시트와 같은 이유로 두되(폰은 손가락이 스친다) 문구가 더 세다:
/// 단계는 되돌릴 수 있지만 메일은 못 되돌린다. 웹의 확인 모달과 같은 내용에
/// **받는 사람 이름**을 더한다 — 폰은 목록에서 잘못 눌러 들어오기 쉽고,
/// 그때 "누구에게 가는지" 가 화면 어디에도 없으면 걸러지지 않는다.
Future<bool?> showMailConfirmSheet(
  BuildContext context, {
  required String applicantName,
  required MailPreset preset,
  required String subject,
  required String body,
}) {
  return showModalBottomSheet<bool>(
    context: context,
    backgroundColor: AppColors.bgElev,
    isScrollControlled: true,
    showDragHandle: true,
    // 단계 변경 시트와 같은 모양 — 위 모서리만 둥글다
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
            Text(
              '$applicantName 님에게 발송',
              style: const TextStyle(
                fontFamily: AppType.fontFamily,
                fontSize: AppType.h2,
                fontWeight: FontWeight.w700,
                color: AppColors.text,
                shadows: AppTextShadow.heading,
              ),
            ),
            const SizedBox(height: AppSpace.s1),
            const Text(
              // 웹 확인 모달과 같은 문장
              '이 내용 그대로 지원자에게 발송됩니다. 되돌릴 수 없습니다.',
              style: TextStyle(
                fontFamily: AppType.fontFamily,
                fontSize: AppType.sm,
                height: 1.5,
                // §1: 적갈은 판단에만 — 되돌릴 수 없다는 것이 그 판단이다
                color: AppColors.danger,
              ),
            ),
            const SizedBox(height: AppSpace.s4),

            // 보낼 것을 다시 보여 준다. 본문이 길면 이 안에서만 스크롤한다
            Flexible(
              child: Container(
                width: double.infinity,
                padding: const EdgeInsets.all(AppSpace.s3),
                decoration: BoxDecoration(
                  color: AppColors.bgSunken,
                  borderRadius: AppShape.ctl,
                  border: Border.all(
                    color: AppColors.border,
                    width: AppShape.borderW,
                  ),
                ),
                child: SingleChildScrollView(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Text(
                        subject,
                        style: const TextStyle(
                          fontFamily: AppType.fontFamily,
                          fontSize: AppType.body,
                          fontWeight: AppType.wSemiBold,
                          color: AppColors.text,
                        ),
                      ),
                      const SizedBox(height: AppSpace.s2),
                      Text(body, style: _text),
                    ],
                  ),
                ),
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
                      style: preset.danger
                          ? FilledButton.styleFrom(
                              backgroundColor: AppColors.danger,
                            )
                          : null,
                      onPressed: () => Navigator.pop(sheetContext, true),
                      child: const Text('발송'),
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
