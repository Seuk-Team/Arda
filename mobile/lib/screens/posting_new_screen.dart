/// 공고 등록 — 웹 `Postings.tsx` 의 [+ 공고 등록]. 앱엔 없던 화면이다(2026-09-02).
///
/// **앱에서 무언가를 만드는 첫 화면이다.** 지금까지 앱은 읽고 단계만 바꿨다.
/// 그래서 이 화면에만 **살아 있는 입력칸**이 있다 — 설정의 잠긴 칸(`_LockedField`,
/// 글자가 보조색)과 달리 글자가 본문색이고 실제로 타이핑된다.
///
/// 웹은 모달이지만 앱은 별도 화면이다. 375px 에서 모달은 화면을 거의 다 덮어
/// 모달일 이유가 없고, 뒤로가기가 그대로 취소가 된다.
///
/// **저장은 아직 없다.** [등록] 은 `POST /job-postings` 자리이고 큐 8이다 —
/// 지금은 고른 값을 토스트로 되비춘다(단계 변경 바와 같은 방식).
library;

import 'package:flutter/material.dart';

import '../models/job_posting.dart';
import '../theme/tokens.dart';
import '../utils/format.dart';
import '../widgets/app_top_bar.dart';

class PostingNewScreen extends StatefulWidget {
  const PostingNewScreen({super.key});

  @override
  State<PostingNewScreen> createState() => _PostingNewScreenState();
}

class _PostingNewScreenState extends State<PostingNewScreen> {
  final _title = TextEditingController();

  /// 비워 두면 상시 채용이다 — ERD `job_postings.deadline` 이 NULL 가능
  DateTime? _deadline;

  /// 웹 기본값과 같다. 만들자마자 지원을 받는 것이 가장 흔한 경우다
  PostingStatus _status = PostingStatus.open;

  @override
  void initState() {
    super.initState();
    // 제목이 비면 [등록] 이 잠긴다 — 글자마다 다시 그려야 그게 보인다
    _title.addListener(() => setState(() {}));
  }

  @override
  void dispose() {
    _title.dispose();
    super.dispose();
  }

  bool get _canSubmit => _title.text.trim().isNotEmpty;

  Future<void> _pickDeadline() async {
    final now = DateTime.now();
    final picked = await showDatePicker(
      context: context,
      initialDate: _deadline ?? now.add(const Duration(days: 14)),
      // 지난 날짜로 마감을 걸 이유가 없다
      firstDate: now,
      lastDate: DateTime(now.year + 2),
      helpText: '마감일',
      cancelText: '취소',
      confirmText: '확인',
    );
    if (picked != null) setState(() => _deadline = picked);
  }

  void _submit() {
    // 큐 8: 여기가 POST /job-postings 가 된다
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text('${_title.text.trim()} — ${_status.label} (아직 저장되지 않음)'),
      ),
    );
    Navigator.pop(context);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.bg,
      appBar: const AppTopBar(title: '공고 등록', showBack: true),
      body: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Expanded(
            child: ListView(
              padding: const EdgeInsets.all(AppSpace.s4),
              children: [
                _Field(
                  label: '공고명',
                  required: true,
                  child: TextField(
                    controller: _title,
                    textInputAction: TextInputAction.next,
                    style: const TextStyle(
                      fontFamily: AppType.fontFamily,
                      fontSize: AppType.body,
                      color: AppColors.text,
                    ),
                    decoration: _inputDecoration('예: 백엔드 개발자 (신입)'),
                  ),
                ),

                _Field(
                  label: '마감일',
                  hint: '비우면 상시 채용이 된다.',
                  child: _PickerBox(
                    // 값이 없을 때는 보조색 — 잠긴 것이 아니라 아직 안 고른 것이다
                    text: _deadline == null ? '연도-월-일' : formatDate(_deadline!),
                    placeholder: _deadline == null,
                    icon: Icons.calendar_today_outlined,
                    onTap: _pickDeadline,
                    onClear: _deadline == null
                        ? null
                        : () => setState(() => _deadline = null),
                  ),
                ),

                _Field(
                  label: '상태',
                  hint: '작성 중은 지원 링크가 열리지 않는다.',
                  // 값이 셋뿐이라 드롭다운 대신 한 줄로 편다 — 한 번에 다 보인다
                  child: Row(
                    children: [
                      for (final s in PostingStatus.values) ...[
                        if (s != PostingStatus.values.first)
                          const SizedBox(width: AppSpace.s2),
                        Expanded(
                          child: _StatusChip(
                            status: s,
                            selected: s == _status,
                            onTap: () => setState(() => _status = s),
                          ),
                        ),
                      ],
                    ],
                  ),
                ),
              ],
            ),
          ),
          _SubmitBar(enabled: _canSubmit, onSubmit: _submit),
        ],
      ),
    );
  }
}

/// 05-design §4: 인풋은 sunken 바탕. 살아 있는 칸이라 글자는 본문색이다.
InputDecoration _inputDecoration(String hint) {
  const outline = OutlineInputBorder(
    borderRadius: AppShape.ctl,
    borderSide: BorderSide(color: AppColors.border, width: AppShape.borderW),
  );

  return InputDecoration(
    isDense: true,
    filled: true,
    fillColor: AppColors.bgSunken,
    hintText: hint,
    hintStyle: const TextStyle(
      fontFamily: AppType.fontFamily,
      fontSize: AppType.body,
      color: AppColors.textSub,
    ),
    contentPadding: const EdgeInsets.symmetric(
      horizontal: AppSpace.s3,
      vertical: AppSpace.s3,
    ),
    border: outline,
    enabledBorder: outline,
    focusedBorder: const OutlineInputBorder(
      borderRadius: AppShape.ctl,
      borderSide: BorderSide(color: AppColors.leaf, width: AppShape.borderW),
    ),
  );
}

/// 라벨 + 입력 + 설명 한 묶음.
class _Field extends StatelessWidget {
  const _Field({
    required this.label,
    required this.child,
    this.hint,
    this.required = false,
  });

  final String label;
  final Widget child;
  final String? hint;
  final bool required;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: AppSpace.s5),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text.rich(
            TextSpan(
              text: label,
              children: [
                if (required)
                  const TextSpan(
                    text: ' *',
                    style: TextStyle(color: AppColors.danger),
                  ),
              ],
            ),
            style: const TextStyle(
              fontFamily: AppType.fontFamily,
              fontSize: AppType.sm,
              fontWeight: AppType.wSemiBold,
              color: AppColors.text,
            ),
          ),
          const SizedBox(height: AppSpace.s2),
          child,
          if (hint != null) ...[
            const SizedBox(height: AppSpace.s1),
            Text(
              hint!,
              style: const TextStyle(
                fontFamily: AppType.fontFamily,
                fontSize: AppType.caption,
                height: 1.5,
                color: AppColors.textSub,
              ),
            ),
          ],
        ],
      ),
    );
  }
}

/// 날짜처럼 눌러서 고르는 칸. 입력칸과 같은 모양이라 같은 줄에 서도 어긋나지 않는다.
class _PickerBox extends StatelessWidget {
  const _PickerBox({
    required this.text,
    required this.placeholder,
    required this.icon,
    required this.onTap,
    this.onClear,
  });

  final String text;
  final bool placeholder;
  final IconData icon;
  final VoidCallback onTap;
  final VoidCallback? onClear;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: AppColors.bgSunken,
      shape: const RoundedRectangleBorder(
        borderRadius: AppShape.ctl,
        side: BorderSide(color: AppColors.border, width: AppShape.borderW),
      ),
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: onTap,
        highlightColor: AppColors.sunkenHover,
        splashColor: AppColors.sunkenHover,
        child: Container(
          height: 46,
          padding: const EdgeInsets.only(left: AppSpace.s3, right: AppSpace.s2),
          child: Row(
            children: [
              Expanded(
                child: Text(
                  text,
                  style: TextStyle(
                    fontFamily: AppType.fontFamily,
                    fontSize: AppType.body,
                    fontFeatures: AppType.tabularNums,
                    color: placeholder ? AppColors.textSub : AppColors.text,
                  ),
                ),
              ),
              if (onClear != null)
                // 고른 뒤에야 지울 것이 생긴다 — 상시 채용으로 되돌리는 길
                AppIconButton(
                  icon: Icons.close,
                  semanticLabel: '마감일 지우기',
                  onPressed: onClear,
                )
              else
                Icon(icon, size: 20, color: AppColors.textSub),
            ],
          ),
        ),
      ),
    );
  }
}

class _StatusChip extends StatelessWidget {
  const _StatusChip({
    required this.status,
    required this.selected,
    required this.onTap,
  });

  final PostingStatus status;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      button: true,
      selected: selected,
      child: Material(
        // §1: 색은 판단에만. 고른 것만 연두로 뜬다
        color: selected ? AppColors.sproutSoft : AppColors.bgSunken,
        shape: RoundedRectangleBorder(
          borderRadius: AppShape.ctl,
          side: BorderSide(
            color: selected ? AppColors.sprout : AppColors.border,
            width: AppShape.borderW,
          ),
        ),
        clipBehavior: Clip.antiAlias,
        child: InkWell(
          onTap: onTap,
          highlightColor: AppColors.sunkenHover,
          splashColor: AppColors.sunkenHover,
          child: Container(
            height: AppLayout.minTouchTarget,
            alignment: Alignment.center,
            child: Text(
              status.label,
              softWrap: false,
              style: TextStyle(
                fontFamily: AppType.fontFamily,
                fontSize: AppType.sm,
                fontWeight: selected ? AppType.wSemiBold : AppType.wRegular,
                color: selected ? AppColors.leaf : AppColors.textSub,
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// 화면 아래에 붙는 등록 줄 — 상세의 [단계 변경] 과 같은 자리·같은 높이.
class _SubmitBar extends StatelessWidget {
  const _SubmitBar({required this.enabled, required this.onSubmit});

  final bool enabled;
  final VoidCallback onSubmit;

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
      // 만큼 72 안에서 깎여 버튼 위아래 여백이 사라진다(상세 하단 바와 같은 이유)
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
              // 공고명이 없으면 못 만든다 — 서버에 보내 400 을 받지 않는다
              onPressed: enabled ? onSubmit : null,
              child: const Text('등록'),
            ),
          ),
        ),
      ),
    );
  }
}
