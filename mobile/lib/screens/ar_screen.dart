/// 아르 (에이전트) — 앱 UI 초안(2026-09-01) 조각 14.
///
/// 05-design §0.5: 사이드바 하단 아르 정사각형이 **전 화면 공통 에이전트 진입점**
/// 이고, 누르면 사이드바 오른쪽으로 패널이 늘어난다 — **768px 이하는 덮는 오버레이**
/// ([ADR-0009](../../docs/03_decision/0009-에이전트-UI-위치.md) 2026-08-31 개정).
/// 앱은 그 오버레이 쪽이라 전체 화면 시트로 올린다.
///
/// **서버에 붙었다** (큐 8 5단계, 2026-09-03) — `POST /agent/chat`.
/// 대화 이력은 서버가 저장하지 않아 화면이 들고 매번 같이 보낸다. 시트를 닫으면
/// 대화가 사라지는 것은 그래서다(웹도 같다).
///
/// 05-design §1 (2026-09-01 팀장 확정): 앰버는 **사람의 확정을 기다리는 것**에만
/// 쓴다.
///
/// - **명단 카드**(목데이터 시절의 `_FindingsCard`)는 확정 버튼이 없어 정보
///   블록이었다. 서버 응답에는 그런 구조가 아예 없어서(글 + 도구 호출뿐)
///   이제 안 그린다.
/// - **확인 카드는 되살렸다.** 서버가 `pending_action` 을 주면 쓰기 도구가
///   아직 실행되지 않은 것이고, 사람이 눌러야 `POST /agent/confirm` 이 돈다 —
///   §1 이 앰버를 쓰라고 한 바로 그 자리다. 이 화면 문서가 예고해 둔 대로다.
library;

import 'package:flutter/material.dart';

import '../api/api_error.dart';
import '../auth/authed_client.dart';
import '../data/agent_repository.dart';
import '../models/applicant.dart';
import '../models/ar_message.dart';
import '../models/stage.dart';
import '../routes.dart';
import '../theme/tokens.dart';

/// 전 화면 공통 진입점이 여는 시트.
Future<void> showArSheet(BuildContext context) {
  return Navigator.of(context).push(
    MaterialPageRoute(fullscreenDialog: true, builder: (_) => const ArScreen()),
  );
}

class ArScreen extends StatefulWidget {
  const ArScreen({super.key, this.messages, this.repository});

  /// 테스트가 대화를 미리 채워 넣는 자리
  final List<ArMessage>? messages;

  /// 테스트가 가짜를 넣는 자리 (큐 8 5단계)
  final AgentRepository? repository;

  @override
  State<ArScreen> createState() => _ArScreenState();
}

class _ArScreenState extends State<ArScreen> {
  late final AgentRepository _repo =
      widget.repository ?? AgentRepository(authedClient());

  late final List<ArMessage> _thread = [...?widget.messages];

  /// 서버로 매번 같이 보내는 이력 — 서버가 저장하지 않는다
  final _history = <ArHistoryEntry>[];

  final _draft = TextEditingController();
  final _scroll = ScrollController();

  /// 사람의 확인을 기다리는 제안. 있으면 앰버 점선 카드가 뜬다
  ArPendingAction? _pending;

  bool _sending = false;

  @override
  void initState() {
    super.initState();
    _draft.addListener(() => setState(() {}));
  }

  @override
  void dispose() {
    _draft.dispose();
    _scroll.dispose();
    super.dispose();
  }

  bool get _canSend => !_sending && _draft.text.trim().isNotEmpty;

  void _push(ArMessage message) {
    setState(() => _thread.add(message));
    // 새 줄이 화면 밖에 생기면 아무 일도 안 일어난 것처럼 보인다
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!_scroll.hasClients) return;
      _scroll.animateTo(
        _scroll.position.maxScrollExtent,
        duration: AppMotion.base,
        curve: Curves.easeOut,
      );
    });
  }

  Future<void> _send() async {
    final message = _draft.text.trim();
    if (message.isEmpty || _sending) return;

    _draft.clear();
    setState(() {
      _pending = null;
      _sending = true;
    });
    _push(ArMessage(speaker: ArSpeaker.me, text: message));

    try {
      final reply = await _repo.chat(message, _history);
      if (!mounted) return;

      // 무엇을 했는지 먼저 — 답이 짧아도 뭘 뒤졌는지는 보여야 한다
      for (final call in reply.toolCalls) {
        _push(ArMessage(speaker: ArSpeaker.log, text: _toolLine(call)));
      }
      if (reply.text.trim().isNotEmpty) {
        _push(ArMessage(speaker: ArSpeaker.ar, text: reply.text.trim()));
      }
      if (reply.pending != null) setState(() => _pending = reply.pending);

      // 이력의 assistant 자리는 비울 수 없다 — 답이 없으면 확인 요청 문장을
      // 대신 넣는다(웹과 같은 처리)
      final assistant = reply.text.trim().isNotEmpty
          ? reply.text.trim()
          : (reply.pending?.description ?? '(확인 대기)');
      _history
        ..add((role: 'user', content: message))
        ..add((role: 'assistant', content: assistant));
    } on ApiError catch (e) {
      if (!mounted) return;
      _push(ArMessage(speaker: ArSpeaker.error, text: e.message));
    } finally {
      if (mounted) setState(() => _sending = false);
    }
  }

  /// 확인 카드의 [확인] — **쓰기 도구가 실제로 도는 유일한 자리다.**
  Future<void> _confirm() async {
    final action = _pending;
    if (action == null || _sending) return;

    setState(() => _sending = true);
    try {
      final ok = await _repo.confirm(action);
      if (!mounted) return;
      setState(() => _pending = null);
      _push(
        ArMessage(
          speaker: ok ? ArSpeaker.log : ArSpeaker.error,
          text: ok ? '실행했습니다 — ${action.description}' : '실행하지 못했습니다',
        ),
      );
    } on ApiError catch (e) {
      if (!mounted) return;
      _push(ArMessage(speaker: ArSpeaker.error, text: e.message));
    } finally {
      if (mounted) setState(() => _sending = false);
    }
  }

  /// 도구 한 줄 — 웹 `logLine` 과 같은 모양이다.
  static String _toolLine(ArToolCall call) {
    final args = call.input.entries
        .map((e) => '${e.key}: ${e.value}')
        .take(3)
        .join(' · ');
    return args.isEmpty ? call.name : '${call.name} — $args';
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.bg,
      body: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const _ArHeader(),
          Expanded(
            child: _thread.isEmpty && _pending == null
                ? const _EmptyThread()
                : ListView(
                    controller: _scroll,
                    padding: const EdgeInsets.all(AppSpace.s4),
                    children: [
                      for (final message in _thread) ...[
                        _Line(message: message),
                        if (message.findings != null) ...[
                          const SizedBox(height: AppSpace.s2),
                          _FindingsCard(findings: message.findings!),
                        ],
                        const SizedBox(height: AppSpace.s3),
                      ],
                      if (_sending) const _Thinking(),
                      if (_pending != null)
                        _PendingCard(
                          action: _pending!,
                          busy: _sending,
                          onConfirm: _confirm,
                          onCancel: () => setState(() => _pending = null),
                        ),
                    ],
                  ),
          ),
          _InputBar(
            controller: _draft,
            enabled: !_sending,
            canSend: _canSend,
            onSend: _send,
          ),
        ],
      ),
    );
  }
}

/// 아직 아무 말도 안 했을 때. 시트를 닫으면 대화가 사라지므로 여기로 자주 온다.
class _EmptyThread extends StatelessWidget {
  const _EmptyThread();

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(AppSpace.s6),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const ArAvatar(size: 56),
            const SizedBox(height: AppSpace.s3),
            const Text(
              '무엇을 찾아 드릴까요?',
              style: TextStyle(
                fontFamily: AppType.fontFamily,
                fontSize: AppType.body,
                fontWeight: AppType.wSemiBold,
                color: AppColors.text,
              ),
            ),
            const SizedBox(height: AppSpace.s2),
            const Text(
              '"면접 단계 지원자 보여줘" 처럼 말하면 됩니다.',
              textAlign: TextAlign.center,
              style: TextStyle(
                fontFamily: AppType.fontFamily,
                fontSize: AppType.sm,
                height: 1.5,
                color: AppColors.textSub,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// 보내는 중 — 답이 오기까지 몇 초 걸린다. 아무 표시가 없으면 안 눌린 줄 안다.
class _Thinking extends StatelessWidget {
  const _Thinking();

  @override
  Widget build(BuildContext context) => const Padding(
    padding: EdgeInsets.only(bottom: AppSpace.s3),
    child: Text(
      '생각하는 중…',
      style: TextStyle(
        fontFamily: AppType.fontFamily,
        fontSize: AppType.sm,
        color: AppColors.textSub,
      ),
    ),
  );
}

/// 대화 한 줄 — 말풍선이거나(아르·나) 가운데 회색 줄이거나(도구·오류).
class _Line extends StatelessWidget {
  const _Line({required this.message});

  final ArMessage message;

  @override
  Widget build(BuildContext context) {
    if (message.speaker == ArSpeaker.ar || message.speaker == ArSpeaker.me) {
      return _Bubble(message: message);
    }

    // 도구 로그·오류는 대화가 아니다 — 말풍선으로 그리면 아르가 한 말처럼 읽힌다
    final isError = message.speaker == ArSpeaker.error;
    return Text(
      message.text,
      textAlign: TextAlign.center,
      style: TextStyle(
        fontFamily: AppType.fontFamily,
        fontSize: AppType.caption,
        height: 1.5,
        // §1: 적갈은 판단에만 — 실패가 그 판단이다
        color: isError ? AppColors.danger : AppColors.textSub,
      ),
    );
  }
}

/// 확인 카드 — **앰버 점선** (05-design §1).
///
/// 서버가 `pending_action` 을 줬다는 것은 **쓰기 도구가 아직 실행되지 않았다**는
/// 뜻이다. 사람이 눌러야 `POST /agent/confirm` 이 돈다 — §1 이 앰버를 쓰라고 한
/// 바로 그 자리다("앰버 점선 = AI 제안 / 잎초록 실선 = 사람 확정").
class _PendingCard extends StatelessWidget {
  const _PendingCard({
    required this.action,
    required this.busy,
    required this.onConfirm,
    required this.onCancel,
  });

  final ArPendingAction action;
  final bool busy;
  final VoidCallback onConfirm;
  final VoidCallback onCancel;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(AppSpace.s4),
      decoration: BoxDecoration(
        color: AppColors.aiSoft,
        borderRadius: AppShape.card,
        border: Border.all(
          color: AppColors.ai,
          width: AppShape.borderW,
          // §1: 제안은 점선. 사람이 확정하면 실선이 된다
          strokeAlign: BorderSide.strokeAlignInside,
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const Text(
            '아르의 제안',
            style: TextStyle(
              fontFamily: AppType.fontFamily,
              fontSize: AppType.caption,
              fontWeight: FontWeight.w700,
              color: AppColors.ai,
            ),
          ),
          const SizedBox(height: AppSpace.s2),
          Text(
            // 서버가 만든 문장을 그대로 쓴다 — 앱이 지어내면 실제로 실행될
            // 것과 화면 문구가 갈린다
            action.description,
            style: const TextStyle(
              fontFamily: AppType.fontFamily,
              fontSize: AppType.body,
              height: 1.6,
              color: AppColors.text,
            ),
          ),
          const SizedBox(height: AppSpace.s4),
          Row(
            children: [
              Expanded(
                child: SizedBox(
                  height: AppLayout.minTouchTarget,
                  child: OutlinedButton(
                    onPressed: busy ? null : onCancel,
                    child: const Text('취소'),
                  ),
                ),
              ),
              const SizedBox(width: AppSpace.s3),
              Expanded(
                child: SizedBox(
                  height: AppLayout.minTouchTarget,
                  child: FilledButton(
                    onPressed: busy ? null : onConfirm,
                    child: const Text('확인'),
                  ),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

/// 머리 — 아바타 · 이름 · 부제 · 닫기. 배포판과 같은 흰 패널이다.
class _ArHeader extends StatelessWidget {
  const _ArHeader();

  @override
  Widget build(BuildContext context) {
    return Container(
      // 배포판(2026-09-01)은 머리도 흰 패널이다. 연두 바탕이던 것을 맞췄다 —
      // 아르가 사는 자리가 사이드바라 연두로 뒀었지만, 웹이 흰색으로 갔다
      decoration: const BoxDecoration(
        color: AppColors.bgElev,
        border: Border(
          bottom: BorderSide(color: AppColors.border, width: AppShape.borderW),
        ),
      ),
      child: SafeArea(
        bottom: false,
        child: Padding(
          padding: const EdgeInsets.fromLTRB(
            AppSpace.s4,
            AppSpace.s2,
            AppSpace.s2,
            AppSpace.s2,
          ),
          child: Row(
            children: [
              const ArAvatar(size: 32),
              const SizedBox(width: AppSpace.s2),
              // 배포판은 이름과 부제가 한 줄이다 — "아르  에이전트"
              const Text(
                '아르',
                style: TextStyle(
                  fontFamily: AppType.fontFamily,
                  fontSize: AppType.h2,
                  fontWeight: FontWeight.w700,
                  color: AppColors.text,
                  shadows: AppTextShadow.heading,
                ),
              ),
              const SizedBox(width: AppSpace.s2),
              const Expanded(
                child: Text(
                  // 배포판 문구. "채용 도우미" 였던 것을 맞췄다
                  '에이전트',
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    fontFamily: AppType.fontFamily,
                    fontSize: AppType.sm,
                    color: AppColors.textSub,
                  ),
                ),
              ),
              _CloseButton(onPressed: () => Navigator.pop(context)),
            ],
          ),
        ),
      ),
    );
  }
}

class _CloseButton extends StatelessWidget {
  const _CloseButton({required this.onPressed});

  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      button: true,
      label: '닫기',
      child: Material(
        color: Colors.transparent,
        shape: const CircleBorder(),
        clipBehavior: Clip.antiAlias,
        child: InkWell(
          onTap: onPressed,
          highlightColor: AppColors.sunkenHover,
          splashColor: AppColors.sunkenHover,
          // §9 터치 타깃 44
          child: const SizedBox(
            width: AppLayout.minTouchTarget,
            height: AppLayout.minTouchTarget,
            child: Icon(Icons.close, size: 24, color: AppColors.text),
          ),
        ),
      ),
    );
  }
}

/// 아르 얼굴 — 진입점(FAB·상단바)과 시트 머리가 같이 쓴다.
class ArAvatar extends StatelessWidget {
  const ArAvatar({super.key, required this.size});

  final double size;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: size,
      height: size,
      clipBehavior: Clip.antiAlias,
      // 바탕은 흰색이다 — assets/images/ar.png 이 흰 배경이라 같은 색이어야
      // 원 가장자리에 이음매가 안 보인다.
      //
      // **테두리를 두지 않는다.** 원형 클립이 이미지를 바깥 원까지 그려서 링이
      // 군데군데 덮이고, 남은 조각만 초록 틈처럼 보였다. 웹도 링 없이 캐릭터만 쓴다.
      //
      // 그림은 런처 아이콘 원본에서 **여백을 잘라 낸** 것이다. 원본은 캔버스의
      // 75%만 그림이라 원 안이 휑했다. 자를 때 뿔이 원에 걸리지 않도록
      // 세로 반지름보다 큰 한 변(766 중 740)을 썼다
      decoration: const BoxDecoration(
        color: AppColors.bgElev,
        shape: BoxShape.circle,
      ),
      child: Image.asset(
        'assets/images/ar.png',
        fit: BoxFit.cover,
        excludeFromSemantics: true,
      ),
    );
  }
}

/// 말풍선 — 아르는 왼쪽 흰 카드, 나는 오른쪽 잎초록.
class _Bubble extends StatelessWidget {
  const _Bubble({required this.message});

  final ArMessage message;

  @override
  Widget build(BuildContext context) {
    final mine = message.speaker == ArSpeaker.me;

    // 배포판은 아르 말풍선 왼쪽에 작은 아바타를 둔다 — 누가 한 말인지가
    // 색·모양 말고 얼굴로도 읽힌다
    if (!mine) {
      return Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const ArAvatar(size: 28),
          const SizedBox(width: AppSpace.s2),
          Flexible(child: _bubble(mine: false)),
        ],
      );
    }

    return Align(alignment: Alignment.centerRight, child: _bubble(mine: true));
  }

  Widget _bubble({required bool mine}) {
    return Container(
      constraints: const BoxConstraints(maxWidth: 280),
      padding: const EdgeInsets.symmetric(
        horizontal: AppSpace.s3,
        vertical: AppSpace.s3,
      ),
      decoration: BoxDecoration(
        color: mine ? AppColors.leaf : AppColors.bgElev,
        // 말하는 쪽 모서리만 각지게 — 누가 한 말인지 모양으로도 갈린다
        borderRadius: BorderRadius.only(
          topLeft: mine ? AppShape.rCard : const Radius.circular(2),
          topRight: mine ? const Radius.circular(2) : AppShape.rCard,
          bottomLeft: AppShape.rCard,
          bottomRight: AppShape.rCard,
        ),
        border: mine
            ? null
            : Border.all(color: AppColors.border, width: AppShape.borderW),
        boxShadow: mine ? null : AppShadow.card,
      ),
      child: Text(
        message.text,
        style: TextStyle(
          fontFamily: AppType.fontFamily,
          fontSize: AppType.body,
          height: 1.5,
          color: mine ? AppColors.bgElev : AppColors.text,
          // §2: 색 채움 위 밝은 글자엔 onFill
          shadows: mine ? AppTextShadow.onFill : null,
        ),
      ),
    );
  }
}

/// 아르가 찾아 준 지원자 명단 — **읽기만 하는 정보 블록이다.**
///
/// 05-design §1 (2026-09-01 팀장 확정): 앰버는 **사람의 확정을 기다리는 것**에만
/// 쓴다. 이 카드에는 확정 버튼이 없으므로 앰버 점선이 아니라 상세의 아르의 요약과
/// 같은 정보 블록(`--bg-sunken` + `--border-soft`)이다.
///
/// **단계 변경 버튼을 여기 두지 않는다.** 같은 일을 두 자리에서 할 수 있으면
/// 어느 쪽이 진짜인지 헷갈린다 — 단계 변경은 지원자 상세 하단 하나로 모은다.
/// 서버는 여전히 `pending_action → /agent/confirm` 2단을 갖고 있고, 앱이 그 길을
/// 쓰게 되면 그때 §1 대로 앰버 점선 카드를 되살린다.
class _FindingsCard extends StatelessWidget {
  const _FindingsCard({required this.findings});

  final ArFindings findings;

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: Alignment.centerLeft,
      child: Container(
        constraints: const BoxConstraints(maxWidth: 300),
        padding: const EdgeInsets.all(AppSpace.s3),
        decoration: BoxDecoration(
          color: AppColors.bgSunken,
          borderRadius: AppShape.card,
          border: Border.all(
            color: AppColors.borderSoft,
            width: AppShape.borderW,
          ),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              // 출처는 제목이 말한다 — §1 의 "아르의 요약"과 같은 방식
              findings.title,
              style: const TextStyle(
                fontFamily: AppType.fontFamily,
                fontSize: AppType.caption,
                fontWeight: FontWeight.w700,
                color: AppColors.text,
              ),
            ),
            for (final applicant in findings.applicants)
              _FoundRow(applicant: applicant),
          ],
        ),
      ),
    );
  }
}

/// 명단의 한 줄 — 이름 · 재료 · 아르의 요지 · [지원자 정보 보기].
///
/// 면접에 부를지 정하려면 이력서·평가·메모까지 봐야 하는데 그게 전부 상세에 있다.
/// 그래서 "이력서 보기" 가 아니라 상세로 보낸다 — 이력서 열람은 아직 없기도 하다(W5).
///
/// 아르 화면은 `Navigator.push` 로 떠 있어, 상세를 열었다 돌아와도 명단이 남는다.
class _FoundRow extends StatelessWidget {
  const _FoundRow({required this.applicant});

  final FoundApplicant applicant;

  /// **껍데기만 만들어 넘긴다.** 명단에는 id·이름·재료뿐이고 나머지는 상세가
  /// 어차피 id 로 다시 받는다(캘린더 행과 같은 처리, 큐 8 4단계).
  void _openDetail(BuildContext context) {
    final stub = Applicant(
      id: applicant.applicationId,
      jobPostingId: 0,
      name: applicant.name,
      email: '',
      currentStage: Stage.applied,
      createdAt: DateTime.now(),
    );
    Navigator.pushNamed(context, Routes.applicantDetail, arguments: (stub, ''));
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(top: AppSpace.s3),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(
            applicant.name,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(
              fontFamily: AppType.fontFamily,
              fontSize: AppType.sm,
              fontWeight: AppType.wSemiBold,
              color: AppColors.text,
            ),
          ),
          Text(
            applicant.meta,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(
              fontFamily: AppType.fontFamily,
              fontSize: AppType.caption,
              color: AppColors.textSub,
            ),
          ),
          if (applicant.gist != null) ...[
            const SizedBox(height: AppSpace.s2),
            Text(
              // 상세의 아르의 요약 요지와 같은 값이다. 여기서 줄이지 않는다 —
              // 에이전트가 이미 2문장·160자로 만들어 준다(35ba4b5)
              applicant.gist!,
              style: const TextStyle(
                fontFamily: AppType.fontFamily,
                fontSize: AppType.caption,
                height: 1.55,
                color: AppColors.text,
              ),
            ),
          ],
          const SizedBox(height: AppSpace.s2),
          _ActionButton(
            label: '지원자 정보 보기',
            filled: false,
            onTap: () => _openDetail(context),
          ),
        ],
      ),
    );
  }
}

class _ActionButton extends StatelessWidget {
  const _ActionButton({
    required this.label,
    required this.filled,
    required this.onTap,
  });

  final String label;
  final bool filled;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    return Material(
      // 사람이 확정하는 버튼이라 **잎초록 실선** — 제안(앰버 점선)과 대비된다
      color: filled ? AppColors.leaf : AppColors.bgElev,
      borderRadius: AppShape.ctl,
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: onTap,
        highlightColor: filled ? AppColors.leafStrong : AppColors.bgSunken,
        splashColor: filled ? AppColors.leafStrong : AppColors.bgSunken,
        child: Container(
          height: AppLayout.minTouchTarget,
          alignment: Alignment.center,
          decoration: BoxDecoration(
            borderRadius: AppShape.ctl,
            border: filled
                ? null
                : Border.all(color: AppColors.border, width: AppShape.borderW),
          ),
          child: Text(
            label,
            softWrap: false,
            style: TextStyle(
              fontFamily: AppType.fontFamily,
              fontSize: AppType.sm,
              fontWeight: AppType.wSemiBold,
              color: filled ? AppColors.bgElev : AppColors.textSub,
              shadows: filled ? AppTextShadow.onFill : null,
            ),
          ),
        ),
      ),
    );
  }
}

/// 입력줄 — **큐 8 5단계에서 잠금을 풀었다** (2026-09-03).
///
/// 05-design §9 터치 타깃 44. 여러 줄 입력을 받되(질문이 길어질 수 있다)
/// 화면을 다 먹지 않게 4줄에서 멈추고 안에서 스크롤한다.
class _InputBar extends StatelessWidget {
  const _InputBar({
    required this.controller,
    required this.enabled,
    required this.canSend,
    required this.onSend,
  });

  final TextEditingController controller;
  final bool enabled;
  final bool canSend;
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
      child: SafeArea(
        top: false,
        child: Padding(
          padding: const EdgeInsets.all(AppSpace.s3),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Expanded(
                child: Container(
                  constraints: const BoxConstraints(
                    minHeight: AppLayout.minTouchTarget,
                  ),
                  padding: const EdgeInsets.symmetric(
                    horizontal: AppSpace.s4,
                    vertical: AppSpace.s1,
                  ),
                  alignment: Alignment.centerLeft,
                  decoration: BoxDecoration(
                    color: AppColors.bgSunken,
                    borderRadius: AppShape.pill,
                    border: Border.all(
                      color: AppColors.border,
                      width: AppShape.borderW,
                    ),
                  ),
                  child: TextField(
                    controller: controller,
                    enabled: enabled,
                    minLines: 1,
                    maxLines: 4,
                    // 서버가 2000자까지 받는다(`ChatRequest.message`)
                    maxLength: 2000,
                    textInputAction: TextInputAction.send,
                    onSubmitted: (_) => canSend ? onSend() : null,
                    style: const TextStyle(
                      fontFamily: AppType.fontFamily,
                      fontSize: AppType.body,
                      color: AppColors.text,
                    ),
                    decoration: const InputDecoration(
                      isDense: true,
                      border: InputBorder.none,
                      // 알약 안이라 글자수 표시가 들어갈 자리가 없다
                      counterText: '',
                      hintText: '아르에게 물어보기',
                      hintStyle: TextStyle(
                        fontFamily: AppType.fontFamily,
                        fontSize: AppType.body,
                        color: AppColors.textSub,
                      ),
                    ),
                  ),
                ),
              ),
              const SizedBox(width: AppSpace.s2),
              Semantics(
                button: true,
                label: '보내기',
                child: Material(
                  color: canSend ? AppColors.leaf : AppColors.bgSunken,
                  shape: const CircleBorder(),
                  clipBehavior: Clip.antiAlias,
                  child: InkWell(
                    onTap: canSend ? onSend : null,
                    child: SizedBox(
                      width: AppLayout.minTouchTarget,
                      height: AppLayout.minTouchTarget,
                      child: Icon(
                        Icons.arrow_forward,
                        size: 20,
                        color: canSend ? AppColors.bgElev : AppColors.textSub,
                      ),
                    ),
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
