/// 공고 등록·수정 — 웹 `Postings.tsx` 의 [+ 공고 등록]. 앱엔 없던 화면이다.
///
/// **앱에서 무언가를 만드는 첫 화면이다.** 지금까지 앱은 읽고 단계만 바꿨다.
/// 그래서 이 화면에만 **살아 있는 입력칸**이 있다 — 설정의 잠긴 칸(`_LockedField`,
/// 글자가 보조색)과 달리 글자가 본문색이고 실제로 타이핑된다.
///
/// 웹은 모달이지만 앱은 별도 화면이다. 375px 에서 모달은 화면을 거의 다 덮어
/// 모달일 이유가 없고, 뒤로가기가 그대로 취소가 된다.
///
/// **한 화면이 둘을 다 한다.** [posting] 이 없으면 등록(`POST /postings`),
/// 있으면 그 공고 수정(`PATCH /postings/{id}`) 이다. 칸이 셋으로 똑같아서
/// 화면을 둘로 나누면 같은 폼을 두 벌 들고 있게 된다.
///
/// **웹에는 둘 다 없다** — `Postings.tsx` 의 `[+]` 는 핸들러가 없고, 수정 화면도
/// 없다. 공고를 만들고 고칠 수 있는 곳은 지금 앱뿐이다(2026-09-03).
library;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../api/api_error.dart';
import '../auth/authed_client.dart';
import '../data/posting_repository.dart';
import '../data/repositories.dart';
import '../models/job_posting.dart';
import '../theme/tokens.dart';
import '../utils/format.dart';
import '../widgets/app_top_bar.dart';

class PostingFormScreen extends StatefulWidget {
  const PostingFormScreen({super.key, this.posting, this.repository});

  /// 고칠 공고. **없으면 등록**이다
  final JobPosting? posting;

  /// 테스트가 가짜를 넣는 자리
  final PostingRepository? repository;

  @override
  State<PostingFormScreen> createState() => _PostingFormScreenState();
}

class _PostingFormScreenState extends State<PostingFormScreen> {
  final _title = TextEditingController();

  late final PostingRepository _repo =
      widget.repository ??
      RepositoryScope.of(context)?.postings ??
      PostingRepository(authedClient());

  /// 보내는 중 — 버튼을 잠근다. 두 번 누르면 공고가 두 개 생긴다
  bool _sending = false;

  /// 비워 두면 상시 채용이다 — ERD `job_postings.deadline` 이 NULL 가능
  DateTime? _deadline;

  /// 등록의 기본값은 웹과 같다. 만들자마자 지원을 받는 것이 가장 흔하다.
  /// 수정이면 지금 값에서 시작한다
  PostingStatus _status = PostingStatus.open;

  /// 고치는 중인가 — 제목·버튼 글자·보낼 곳이 갈린다
  bool get _editing => widget.posting != null;

  @override
  void initState() {
    super.initState();

    // 수정이면 지금 값을 채워 넣는다. 빈 칸에서 시작하면 안 건드릴 값까지
    // 다시 적어야 하고, 뭐가 들어 있었는지도 안 보인다
    final posting = widget.posting;
    if (posting != null) {
      _title.text = posting.title;
      _status = posting.status;
      _deadline = posting.deadline;
    }

    // 제목이 비면 버튼이 잠긴다 — 글자마다 다시 그려야 그게 보인다
    _title.addListener(() => setState(() {}));
  }

  @override
  void dispose() {
    _title.dispose();
    super.dispose();
  }

  bool get _canSubmit => _title.text.trim().isNotEmpty && !_sending;

  Future<void> _pickDeadline() async {
    final now = DateTime.now();
    final current = _deadline;

    // 이미 마감이 지난 공고를 고치는 경우 원래 값이 [firstDate] 보다 앞선다 —
    // 그대로 넘기면 달력이 뜨지 않고 터진다. 그때는 오늘부터 편다
    final initial = current == null || current.isBefore(now)
        ? now.add(const Duration(days: 14))
        : current;

    final picked = await showDatePicker(
      context: context,
      initialDate: initial,
      // 지난 날짜로 마감을 걸 이유가 없다 — 서버도 422 로 막는다
      firstDate: now,
      lastDate: DateTime(now.year + 2),
      helpText: '마감일',
      cancelText: '취소',
      confirmText: '확인',
    );
    if (picked != null) setState(() => _deadline = picked);
  }

  Future<void> _submit() async {
    // 화면이 닫힌 뒤에도 토스트는 띄워야 한다 — 닫히기 전에 잡아 둔다
    final messenger = ScaffoldMessenger.of(context);
    final navigator = Navigator.of(context);
    final posting = widget.posting;

    setState(() => _sending = true);

    try {
      final saved = posting == null
          ? await _repo.create(
              title: _title.text.trim(),
              status: _status,
              deadline: _deadline,
            )
          : await _repo.update(
              posting.id,
              title: _title.text.trim(),
              status: _status,
              // 안 건드렸으면 안 보낸다 — 지난 마감일을 되보내면 서버가
              // 422 로 막아 제목조차 못 고친다(posting_repository.dart)
              changeDeadline: _deadline != posting.deadline,
              deadline: _deadline,
            );
      if (!mounted) return;

      // 저장된 공고를 들려 보낸다. 부른 쪽이 이걸로 목록·헤더를 맞춘다 —
      // 그대로 두면 방금 고친 것이 안 보여 저장이 안 된 줄 안다
      navigator.pop(saved);
      messenger.showSnackBar(
        SnackBar(
          content: Text(
            '${saved.title} — 공고를 ${posting == null ? '등록' : '수정'}했습니다',
          ),
        ),
      );
    } on ApiError catch (e) {
      if (!mounted) return;
      // 화면을 닫지 않는다. 닫으면 적어 둔 것이 다 사라진다
      setState(() => _sending = false);
      messenger.showSnackBar(SnackBar(content: Text(e.message)));
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.bg,
      appBar: AppTopBar(title: _editing ? '공고 수정' : '공고 등록', showBack: true),
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
                    // 서버가 200자까지 받는다(`PostingCreate.title`). 넘겨 보내
                    // 422 를 받느니 애초에 안 들어가게 한다. 글자수 표시는
                    // 달지 않는다 — 공고명이 200자에 닿는 일은 없다
                    inputFormatters: [LengthLimitingTextInputFormatter(200)],
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
          _SubmitBar(
            label: _editing ? '저장' : '등록',
            enabled: _canSubmit,
            sending: _sending,
            onSubmit: _submit,
          ),
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
  const _SubmitBar({
    required this.label,
    required this.enabled,
    required this.sending,
    required this.onSubmit,
  });

  /// 등록이면 "등록", 수정이면 "저장" — 무엇을 하는 버튼인지 화면 제목만으로는
  /// 모르고, 이미 있는 공고에 "등록" 이 붙어 있으면 새로 만드는 줄 안다
  final String label;
  final bool enabled;
  final bool sending;
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
              // 공고명이 없으면 못 만든다 — 서버에 보내 422 를 받지 않는다
              onPressed: enabled ? onSubmit : null,
              child: sending
                  // 글자를 지우지 않고 그 자리에 스피너를 둔다 —
                  // 버튼 크기가 변하면 눌린 자리가 흔들린다(단계 변경과 같은 방식)
                  ? const SizedBox(
                      width: 20,
                      height: 20,
                      child: CircularProgressIndicator(
                        strokeWidth: 2,
                        color: AppColors.bgElev,
                      ),
                    )
                  : Text(label),
            ),
          ),
        ),
      ),
    );
  }
}
