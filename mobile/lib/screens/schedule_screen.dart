/// 면접 시간 조율 — 지원자용 (2026-09-08).
///
/// 후보 시간을 고르면 **그 자리에서 확정된다** (ADR-0016: 지원자의 선택이므로
/// 담당자 승인 없이 즉시 확정). 되돌릴 수 없어서 화면이 먼저 물어본다.
///
/// ## 아래쪽 '아르에게 묻기'
///
/// 사용자가 말한 "채팅방" 자리다. 다만 **사람과 하는 대화가 아니고, 대화도
/// 아니다**: 서버가 stateless 라 한 번 물으면 한 번 답하고 끝이며 앞 질문을
/// 기억하지 않는다(`POST /public/schedule/{t}/faq`). 그래서 말풍선을 쌓아
/// 두되 "이어지는 대화"인 척하지 않고, 답이 공고 범위 안이라는 것을 적어 둔다.
/// 연봉·평가·다른 지원자는 서버 프롬프트가 답하지 않는다.
///
/// 담당자와 직접 주고받는 채팅은 서버에 없다 — 만들려면 백엔드부터다.
library;

import 'package:flutter/material.dart';

import '../api/api_error.dart';
import '../data/applicant_demo.dart';
import '../data/applicant_portal_repository.dart';
import '../models/applicant_extra.dart';
import '../theme/tokens.dart';
import '../utils/format.dart';
import 'applicant_shell.dart';

class ScheduleScreen extends StatefulWidget {
  const ScheduleScreen({super.key, required this.token, this.portal});

  final String? token;
  final ApplicantPortalRepository? portal;

  @override
  State<ScheduleScreen> createState() => _ScheduleScreenState();
}

class _ScheduleScreenState extends State<ScheduleScreen> {
  late final ApplicantPortalRepository _portal =
      widget.portal ?? applicantPortal();

  final _question = TextEditingController();

  SchedulePublic? _data;
  String? _error;
  bool _sending = false;

  /// 아르와 주고받은 것. **대화가 아니라 기록이다** — 서버는 앞 질문을 모른다
  final _asked = <({String question, String? answer})>[];
  bool _asking = false;

  @override
  void initState() {
    super.initState();
    if (widget.token != null) _load();
  }

  @override
  void dispose() {
    _question.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    setState(() => _error = null);
    try {
      final data = await _portal.schedule(widget.token!);
      if (!mounted) return;
      setState(() => _data = data);
    } on ApiError catch (e) {
      if (!mounted) return;
      setState(() => _error = e.message);
    }
  }

  Future<void> _confirm(ScheduleSlot slot) async {
    final ok = await showSlotConfirmSheet(context, slot: slot);
    if (ok != true || !mounted || _sending) return;
    setState(() {
      _sending = true;
      _error = null;
    });
    try {
      final next = await _portal.confirmSlot(widget.token!, slot.id);
      if (!mounted) return;
      setState(() {
        _data = next;
        _sending = false;
      });
    } on ApiError catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e.message;
        _sending = false;
      });
    }
  }

  Future<void> _ask() async {
    final text = _question.text.trim();
    if (text.isEmpty || _asking) return;
    setState(() {
      _asking = true;
      _asked.add((question: text, answer: null));
    });
    _question.clear();
    try {
      final answer = await _portal.askAr(widget.token!, text);
      if (!mounted) return;
      setState(() {
        _asked[_asked.length - 1] = (question: text, answer: answer);
        _asking = false;
      });
    } on ApiError catch (e) {
      if (!mounted) return;
      setState(() {
        _asked[_asked.length - 1] = (question: text, answer: e.message);
        _asking = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    if (widget.token == null) {
      return const ApplicantMissing(what: '면접 시간 제안');
    }
    final data = _data;
    if (data == null) {
      return _error == null
          ? const Center(child: CircularProgressIndicator())
          : _Failed(message: _error!, onRetry: _load);
    }

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
        const SizedBox(height: AppSpace.s4),

        switch (data.status) {
          ScheduleStatus.confirmed => _Confirmed(slot: data.confirmedSlot),
          ScheduleStatus.expired => const _Note(
            text: '선택 기한이 지났습니다. 담당자에게 문의해 주세요.',
            tone: AppColors.danger,
          ),
          ScheduleStatus.proposed => _Slots(
            slots: data.slots,
            busy: _sending,
            onPick: _confirm,
          ),
        },

        if (_error != null) ...[
          const SizedBox(height: AppSpace.s3),
          _Note(text: _error!, tone: AppColors.danger),
        ],

        const SizedBox(height: AppSpace.s6),
        const Divider(color: AppColors.borderSoft, height: 1),
        const SizedBox(height: AppSpace.s4),

        const Text(
          '아르에게 묻기',
          style: TextStyle(
            fontFamily: AppType.fontFamily,
            fontSize: AppType.body,
            fontWeight: AppType.wSemiBold,
            color: AppColors.text,
          ),
        ),
        const SizedBox(height: AppSpace.s2),
        const Text(
          '공고에 대해 궁금한 것을 물어보세요. 한 번에 하나씩 답합니다.',
          style: TextStyle(
            fontFamily: AppType.fontFamily,
            fontSize: AppType.caption,
            color: AppColors.textSub,
          ),
        ),
        const SizedBox(height: AppSpace.s3),

        for (final turn in _asked) ...[
          _Bubble(text: turn.question, mine: true),
          const SizedBox(height: AppSpace.s2),
          _Bubble(text: turn.answer ?? '답변을 만들고 있습니다…', mine: false),
          const SizedBox(height: AppSpace.s3),
        ],

        TextField(
          controller: _question,
          enabled: !_asking,
          minLines: 1,
          maxLines: 3,
          onSubmitted: (_) => _ask(),
          style: const TextStyle(
            fontFamily: AppType.fontFamily,
            fontSize: AppType.sm,
            color: AppColors.text,
          ),
          decoration: const InputDecoration(
            isDense: true,
            filled: true,
            fillColor: AppColors.bgSunken,
            hintText: '예: 면접은 어떻게 진행되나요?',
            hintStyle: TextStyle(
              fontFamily: AppType.fontFamily,
              fontSize: AppType.sm,
              color: AppColors.textSub,
            ),
            contentPadding: EdgeInsets.symmetric(
              horizontal: AppSpace.s3,
              vertical: AppSpace.s3,
            ),
            border: OutlineInputBorder(
              borderRadius: AppShape.ctl,
              borderSide: BorderSide(
                color: AppColors.border,
                width: AppShape.borderW,
              ),
            ),
            enabledBorder: OutlineInputBorder(
              borderRadius: AppShape.ctl,
              borderSide: BorderSide(
                color: AppColors.border,
                width: AppShape.borderW,
              ),
            ),
            focusedBorder: OutlineInputBorder(
              borderRadius: AppShape.ctl,
              borderSide: BorderSide(
                color: AppColors.accent,
                width: AppShape.borderW,
              ),
            ),
          ),
        ),
        const SizedBox(height: AppSpace.s3),
        SizedBox(
          height: AppLayout.minTouchTarget,
          child: OutlinedButton(
            onPressed: _asking ? null : _ask,
            child: Text(_asking ? '묻는 중…' : '물어보기'),
          ),
        ),
      ],
    );
  }
}

class _Slots extends StatelessWidget {
  const _Slots({required this.slots, required this.busy, required this.onPick});

  final List<ScheduleSlot> slots;
  final bool busy;
  final ValueChanged<ScheduleSlot> onPick;

  @override
  Widget build(BuildContext context) {
    if (slots.isEmpty) {
      return const _Note(text: '후보 시간이 없습니다.', tone: AppColors.textSub);
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const Text(
          '가능한 시간을 골라 주세요.',
          style: TextStyle(
            fontFamily: AppType.fontFamily,
            fontSize: AppType.sm,
            color: AppColors.textSub,
          ),
        ),
        const SizedBox(height: AppSpace.s3),
        for (final slot in slots) ...[
          Material(
            color: AppColors.bgElev,
            shape: const RoundedRectangleBorder(
              borderRadius: AppShape.card,
              side: BorderSide(
                color: AppColors.border,
                width: AppShape.borderW,
              ),
            ),
            clipBehavior: Clip.antiAlias,
            child: InkWell(
              onTap: busy ? null : () => onPick(slot),
              highlightColor: AppColors.bgSunken,
              splashColor: AppColors.bgSunken,
              child: Padding(
                padding: const EdgeInsets.all(AppSpace.s4),
                child: Row(
                  children: [
                    Expanded(child: _SlotText(slot: slot)),
                    const Icon(
                      Icons.chevron_right,
                      size: 20,
                      color: AppColors.textSub,
                    ),
                  ],
                ),
              ),
            ),
          ),
          const SizedBox(height: AppSpace.s2),
        ],
      ],
    );
  }
}

class _SlotText extends StatelessWidget {
  const _SlotText({required this.slot});

  final ScheduleSlot slot;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          formatDate(slot.startAt),
          style: const TextStyle(
            fontFamily: AppType.fontFamily,
            fontSize: AppType.body,
            fontWeight: AppType.wSemiBold,
            fontFeatures: AppType.tabularNums,
            color: AppColors.text,
          ),
        ),
        const SizedBox(height: AppSpace.s1),
        Text(
          '${formatTime(slot.startAt)} – ${formatTime(slot.endAt)}',
          style: const TextStyle(
            fontFamily: AppType.fontFamily,
            fontSize: AppType.sm,
            fontFeatures: AppType.tabularNums,
            color: AppColors.textSub,
          ),
        ),
      ],
    );
  }
}

class _Confirmed extends StatelessWidget {
  const _Confirmed({required this.slot});

  final ScheduleSlot? slot;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(AppSpace.s4),
      decoration: BoxDecoration(
        color: AppColors.okSoft,
        borderRadius: AppShape.card,
        border: Border.all(color: AppColors.ok, width: AppShape.borderW),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            '면접 시간이 확정됐습니다',
            style: TextStyle(
              fontFamily: AppType.fontFamily,
              fontSize: AppType.sm,
              fontWeight: AppType.wSemiBold,
              color: AppColors.okText,
            ),
          ),
          if (slot != null) ...[
            const SizedBox(height: AppSpace.s3),
            _SlotText(slot: slot!),
          ],
        ],
      ),
    );
  }
}

class _Bubble extends StatelessWidget {
  const _Bubble({required this.text, required this.mine});

  final String text;

  /// 내가 물은 것인가. 아르 답과 좌우로 갈라 둔다
  final bool mine;

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: mine ? Alignment.centerRight : Alignment.centerLeft,
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 280),
        child: Container(
          padding: const EdgeInsets.symmetric(
            horizontal: AppSpace.s3,
            vertical: AppSpace.s2,
          ),
          decoration: BoxDecoration(
            color: mine ? AppColors.accentSoft : AppColors.bgElev,
            borderRadius: AppShape.card,
            border: Border.all(
              color: mine ? AppColors.accent : AppColors.border,
              width: AppShape.borderW,
            ),
          ),
          child: Text(
            text,
            style: TextStyle(
              fontFamily: AppType.fontFamily,
              fontSize: AppType.sm,
              height: 1.6,
              color: mine ? AppColors.accentText : AppColors.text,
            ),
          ),
        ),
      ),
    );
  }
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

class _Failed extends StatelessWidget {
  const _Failed({required this.message, required this.onRetry});

  final String message;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(AppSpace.s5),
        child: Column(
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
              child: OutlinedButton(
                onPressed: onRetry,
                child: const Text('다시 시도'),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// 시간 확정 확인. **되돌릴 수 없다** — 고르는 즉시 확정이고 담당자 승인이 없다
Future<bool?> showSlotConfirmSheet(
  BuildContext context, {
  required ScheduleSlot slot,
}) {
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
              '이 시간으로 확정',
              style: TextStyle(
                fontFamily: AppType.fontFamily,
                fontSize: AppType.h2,
                fontWeight: FontWeight.w700,
                color: AppColors.text,
                shadows: AppTextShadow.heading,
              ),
            ),
            const SizedBox(height: AppSpace.s3),
            _SlotText(slot: slot),
            const SizedBox(height: AppSpace.s3),
            const Text(
              '누르면 바로 확정됩니다. 되돌리려면 담당자에게 문의해야 합니다.',
              style: TextStyle(
                fontFamily: AppType.fontFamily,
                fontSize: AppType.sm,
                height: 1.5,
                color: AppColors.textSub,
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
                      onPressed: () => Navigator.pop(sheetContext, true),
                      child: const Text('확정'),
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
