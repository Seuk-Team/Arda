/// 인적성 검사 — 지원자용 (2026-09-08).
///
/// 문항도 척도 라벨도 **서버가 준 것을 그대로** 쓴다. 앱이 문장을 지어내면
/// 지원자가 실제로 본 문장과 서버가 스냅샷해 둔 문장이 갈린다.
///
/// **전 문항 필수, 재제출 없다**(서버가 막는다). 그래서 화면이 먼저 막는다:
/// 안 고른 문항이 남아 있으면 제출 버튼이 안 살아나고, 몇 개 남았는지 적는다.
/// 다 풀고 나서 422 를 맞는 것보다 낫다.
library;

import 'package:flutter/material.dart';

import '../api/api_error.dart';
import '../data/applicant_portal_repository.dart';
import '../models/applicant_extra.dart';
import '../theme/tokens.dart';
import 'applicant_shell.dart';

class AptitudeScreen extends StatefulWidget {
  const AptitudeScreen({super.key, required this.token, this.portal});

  /// 없으면 담당자가 아직 안 보낸 것이다
  final String? token;

  final ApplicantPortalRepository? portal;

  @override
  State<AptitudeScreen> createState() => _AptitudeScreenState();
}

class _AptitudeScreenState extends State<AptitudeScreen> {
  late final ApplicantPortalRepository _portal =
      widget.portal ?? ApplicantPortalRepository();

  AptitudePublic? _data;
  String? _error;
  bool _sending = false;

  /// 문항 키 → 고른 점수
  final _answers = <String, int>{};

  @override
  void initState() {
    super.initState();
    if (widget.token != null) _load();
  }

  Future<void> _load() async {
    setState(() => _error = null);
    try {
      final data = await _portal.aptitude(widget.token!);
      if (!mounted) return;
      setState(() => _data = data);
    } on ApiError catch (e) {
      if (!mounted) return;
      setState(() => _error = e.message);
    }
  }

  int get _left => (_data?.questions.length ?? 0) - _answers.length;

  Future<void> _submit() async {
    if (_sending || _left != 0) return;
    setState(() {
      _sending = true;
      _error = null;
    });
    try {
      final next = await _portal.submitAptitude(widget.token!, _answers);
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

  @override
  Widget build(BuildContext context) {
    if (widget.token == null) {
      return const ApplicantMissing(what: '인적성 검사');
    }
    final data = _data;
    if (data == null) {
      return _error == null
          ? const Center(child: CircularProgressIndicator())
          : _Failed(message: _error!, onRetry: _load);
    }

    if (data.status != AptitudeStatus.pending) {
      return _Closed(status: data.status);
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
        const SizedBox(height: AppSpace.s3),
        const Text(
          '각 문장이 자신과 얼마나 맞는지 골라 주세요.\n정답은 없습니다.',
          style: TextStyle(
            fontFamily: AppType.fontFamily,
            fontSize: AppType.sm,
            height: 1.6,
            color: AppColors.textSub,
          ),
        ),
        const SizedBox(height: AppSpace.s5),

        for (var i = 0; i < data.questions.length; i++) ...[
          _Question(
            index: i + 1,
            question: data.questions[i],
            labels: data.likertLabels,
            picked: _answers[data.questions[i].key],
            onPick: (v) => setState(() => _answers[data.questions[i].key] = v),
          ),
          const SizedBox(height: AppSpace.s5),
        ],

        if (_error != null) ...[
          _Note(text: _error!, tone: AppColors.danger),
          const SizedBox(height: AppSpace.s3),
        ],

        SizedBox(
          height: AppLayout.minTouchTarget,
          child: FilledButton(
            onPressed: (_sending || _left != 0) ? null : _submit,
            child: Text(
              _sending
                  ? '보내는 중…'
                  : _left == 0
                  ? '제출하기'
                  : '$_left문항 남았습니다',
            ),
          ),
        ),
        const SizedBox(height: AppSpace.s3),
        const Text(
          '제출하면 다시 고칠 수 없습니다.',
          textAlign: TextAlign.center,
          style: TextStyle(
            fontFamily: AppType.fontFamily,
            fontSize: AppType.caption,
            color: AppColors.textSub,
          ),
        ),
      ],
    );
  }
}

class _Question extends StatelessWidget {
  const _Question({
    required this.index,
    required this.question,
    required this.labels,
    required this.picked,
    required this.onPick,
  });

  final int index;
  final AptitudeQuestion question;
  final Map<int, String> labels;
  final int? picked;
  final ValueChanged<int> onPick;

  @override
  Widget build(BuildContext context) {
    // 서버가 준 척도 그대로. 라벨이 안 오면 숫자만 그린다
    final steps = labels.keys.toList()..sort();
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text(
          '$index. ${question.text}',
          style: const TextStyle(
            fontFamily: AppType.fontFamily,
            fontSize: AppType.body,
            height: 1.5,
            color: AppColors.text,
          ),
        ),
        const SizedBox(height: AppSpace.s3),
        Row(
          children: [
            for (final step in steps) ...[
              Expanded(
                child: _Step(
                  value: step,
                  label: labels[step] ?? '$step',
                  on: picked == step,
                  onTap: () => onPick(step),
                ),
              ),
              if (step != steps.last) const SizedBox(width: AppSpace.s2),
            ],
          ],
        ),
      ],
    );
  }
}

class _Step extends StatelessWidget {
  const _Step({
    required this.value,
    required this.label,
    required this.on,
    required this.onTap,
  });

  final int value;
  final String label;
  final bool on;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      selected: on,
      button: true,
      label: label,
      child: Material(
        color: on ? AppColors.accentSoft : AppColors.bgSunken,
        shape: RoundedRectangleBorder(
          borderRadius: AppShape.ctl,
          side: BorderSide(
            color: on ? AppColors.accent : AppColors.borderSoft,
            width: AppShape.borderW,
          ),
        ),
        clipBehavior: Clip.antiAlias,
        child: InkWell(
          onTap: onTap,
          highlightColor: AppColors.sunkenHover,
          splashColor: AppColors.sunkenHover,
          child: Container(
            // §9 터치 타깃 — 다섯 칸이라 좁아서 높이로 벌어 준다
            height: 64,
            padding: const EdgeInsets.symmetric(horizontal: 2, vertical: 6),
            alignment: Alignment.center,
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Text(
                  '$value',
                  style: TextStyle(
                    fontFamily: AppType.fontFamily,
                    fontSize: AppType.body,
                    fontWeight: AppType.wSemiBold,
                    fontFeatures: AppType.tabularNums,
                    color: on ? AppColors.accentText : AppColors.text,
                  ),
                ),
                const SizedBox(height: 2),
                Text(
                  label,
                  maxLines: 2,
                  textAlign: TextAlign.center,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    fontFamily: AppType.fontFamily,
                    fontSize: 10,
                    height: 1.2,
                    color: on ? AppColors.accentText : AppColors.textSub,
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _Closed extends StatelessWidget {
  const _Closed({required this.status});

  final AptitudeStatus status;

  @override
  Widget build(BuildContext context) {
    final done = status == AptitudeStatus.submitted;
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(AppSpace.s6),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(
              done ? Icons.check_circle_outline : Icons.schedule,
              size: 28,
              color: done ? AppColors.okText : AppColors.neutral,
            ),
            const SizedBox(height: AppSpace.s3),
            Text(
              done
                  ? '인적성 검사를 제출했습니다.\n결과는 담당자만 봅니다.'
                  : '인적성 검사 기한이 지났습니다.\n담당자에게 문의해 주세요.',
              textAlign: TextAlign.center,
              style: TextStyle(
                fontFamily: AppType.fontFamily,
                fontSize: AppType.sm,
                height: 1.6,
                color: done ? AppColors.textSub : AppColors.danger,
              ),
            ),
          ],
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
