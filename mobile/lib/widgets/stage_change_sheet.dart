/// 단계 변경 확인 시트 — 시안(2026-08-28) 1번.
///
/// **메일이 자동 발송돼 되돌릴 수 없는 동작이다.** 고르는 순간 실행되면 안 되고,
/// 무엇이 일어나는지 읽고 취소할 수 있어야 한다.
///
/// 왜 다이얼로그가 아니라 바텀시트인가 (시안):
/// 엄지가 닿는 아래쪽에 놓이고, 아래로 밀어 닫는 동작이 곧 취소가 된다.
///
/// 치수(시안): 선택지 행 56dp · 버튼 48dp · 시트 여백 16dp · 손잡이 32×4dp
library;

import 'package:flutter/material.dart';

import '../models/applicant.dart';
import '../models/stage.dart';
import '../theme/tokens.dart';

/// 시트를 열고, 확정하면 `(단계, 사유)` 를 돌려준다. 취소하면 null.
Future<({Stage stage, String? reason})?> showStageChangeSheet(
  BuildContext context, {
  required Applicant applicant,
}) {
  return showModalBottomSheet<({Stage stage, String? reason})>(
    context: context,
    backgroundColor: AppColors.bgElev,
    // 사유 입력이 열리면 키보드가 올라온다 — 시트가 가려지지 않게
    isScrollControlled: true,
    shape: const RoundedRectangleBorder(
      borderRadius: BorderRadius.vertical(top: AppShape.rCard),
    ),
    builder: (_) => _StageChangeSheet(applicant: applicant),
  );
}

class _StageChangeSheet extends StatefulWidget {
  const _StageChangeSheet({required this.applicant});

  final Applicant applicant;

  @override
  State<_StageChangeSheet> createState() => _StageChangeSheetState();
}

class _StageChangeSheetState extends State<_StageChangeSheet> {
  Stage? _picked;
  final _reason = TextEditingController();

  @override
  void initState() {
    super.initState();
    _reason.addListener(() => setState(() {}));
  }

  @override
  void dispose() {
    _reason.dispose();
    super.dispose();
  }

  Stage get _from => widget.applicant.currentStage;

  /// 시안: **불합격은 사유 없이 못 넘어간다**(D8).
  /// 서버 422 를 기다렸다 보여 주는 대신 그 자리에서 버튼을 잠근다.
  bool get _canSubmit {
    final to = _picked;
    if (to == null) return false;
    if (to == Stage.rejected) return _reason.text.trim().isNotEmpty;
    return true;
  }

  @override
  Widget build(BuildContext context) {
    final picked = _picked;

    return SafeArea(
      top: false,
      child: Padding(
        // 키보드가 올라오면 그만큼 밀어 올린다
        padding: EdgeInsets.only(
          bottom: MediaQuery.viewInsetsOf(context).bottom,
        ),
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(AppSpace.s4),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            mainAxisSize: MainAxisSize.min,
            children: [
              const _Handle(),
              const SizedBox(height: AppSpace.s4),

              const Text(
                '단계 변경',
                style: TextStyle(
                  fontFamily: AppType.fontFamily,
                  fontSize: AppType.h2,
                  fontWeight: FontWeight.w700,
                  color: AppColors.text,
                  shadows: AppTextShadow.heading,
                ),
              ),
              const SizedBox(height: AppSpace.s1),
              Text(
                '지금은 ${_from.label}입니다. 옮길 단계를 고르세요.',
                style: const TextStyle(
                  fontFamily: AppType.fontFamily,
                  fontSize: AppType.sm,
                  color: AppColors.textSub,
                ),
              ),

              const SizedBox(height: AppSpace.s4),
              // 시안: **갈 수 있는 단계만 보여준다** — 409 를 받을 일이 없다
              for (final to in _from.allowedNext)
                _Choice(
                  stage: to,
                  description: _from.describeMoveTo(to),
                  selected: picked == to,
                  onTap: () => setState(() => _picked = to),
                ),

              // 불합격을 고르면 사유 칸이 펼쳐진다 (D8)
              if (picked == Stage.rejected) ...[
                const SizedBox(height: AppSpace.s3),
                _ReasonField(controller: _reason),
              ],

              // 시안: **메일 경고는 나가는 단계에만.** 늘 띄우면 경고를 안 읽게 된다
              if (picked != null && picked.notifiesApplicant) ...[
                const SizedBox(height: AppSpace.s4),
                const _MailWarning(),
              ],

              const SizedBox(height: AppSpace.s4),
              Row(
                children: [
                  Expanded(
                    child: SizedBox(
                      height: AppType.menuItemHeight,
                      child: OutlinedButton(
                        onPressed: () => Navigator.pop(context),
                        child: const Text('취소'),
                      ),
                    ),
                  ),
                  const SizedBox(width: AppSpace.s3),
                  Expanded(
                    child: SizedBox(
                      height: AppType.menuItemHeight,
                      child: FilledButton(
                        onPressed: _canSubmit
                            ? () => Navigator.pop(context, (
                                stage: picked!,
                                reason: picked == Stage.rejected
                                    ? _reason.text.trim()
                                    : null,
                              ))
                            : null,
                        // 시안: 라벨이 "확인"이 아니다 —
                        // 무엇이 일어나는지 버튼이 말한다
                        child: Text(
                          picked == null ? '단계 선택' : '${picked.label}으로 변경',
                        ),
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
}

/// 시안: 손잡이 32×4dp. 아래로 밀어 닫을 수 있다는 표시다.
class _Handle extends StatelessWidget {
  const _Handle();

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Container(
        width: 32,
        height: 4,
        decoration: const BoxDecoration(
          color: AppColors.border,
          borderRadius: AppShape.pill,
        ),
      ),
    );
  }
}

/// 선택지 한 줄 — 시안: 행 높이 56dp.
class _Choice extends StatelessWidget {
  const _Choice({
    required this.stage,
    required this.description,
    required this.selected,
    required this.onTap,
  });

  final Stage stage;
  final String description;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      selected: selected,
      button: true,
      child: Material(
        color: selected ? AppColors.sproutSoft : AppColors.bgElev,
        borderRadius: AppShape.ctl,
        clipBehavior: Clip.antiAlias,
        child: InkWell(
          onTap: onTap,
          highlightColor: AppColors.bgSunken,
          splashColor: AppColors.bgSunken,
          child: Container(
            constraints: const BoxConstraints(minHeight: 56),
            padding: const EdgeInsets.symmetric(horizontal: AppSpace.s3),
            child: Row(
              children: [
                Icon(
                  selected
                      ? Icons.radio_button_checked
                      : Icons.radio_button_unchecked,
                  size: 20,
                  color: selected ? AppColors.leaf : AppColors.textSub,
                ),
                const SizedBox(width: AppSpace.s3),
                Text(
                  stage.label,
                  softWrap: false,
                  style: TextStyle(
                    fontFamily: AppType.fontFamily,
                    fontSize: AppType.sm,
                    fontWeight: AppType.wSemiBold,
                    color: selected ? AppColors.leaf : AppColors.text,
                  ),
                ),
                const SizedBox(width: AppSpace.s2),
                Expanded(
                  child: Text(
                    description,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    softWrap: false,
                    style: const TextStyle(
                      fontFamily: AppType.fontFamily,
                      fontSize: AppType.caption,
                      color: AppColors.textSub,
                    ),
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

/// 불합격 사유 — D8. 비어 있으면 변경 버튼이 잠긴다.
class _ReasonField extends StatelessWidget {
  const _ReasonField({required this.controller});

  final TextEditingController controller;

  @override
  Widget build(BuildContext context) {
    return TextField(
      controller: controller,
      maxLines: 3,
      minLines: 2,
      style: const TextStyle(
        fontFamily: AppType.fontFamily,
        fontSize: AppType.body,
        color: AppColors.text,
      ),
      decoration: const InputDecoration(
        labelText: '불합격 사유',
        hintText: '지원자에게 보낼 안내에 들어갑니다',
        labelStyle: TextStyle(
          fontFamily: AppType.fontFamily,
          fontSize: AppType.sm,
          color: AppColors.textSub,
        ),
        hintStyle: TextStyle(
          fontFamily: AppType.fontFamily,
          fontSize: AppType.sm,
          color: AppColors.textSub,
        ),
        filled: true,
        fillColor: AppColors.bgElev,
        contentPadding: EdgeInsets.all(AppSpace.s3),
        border: OutlineInputBorder(
          borderRadius: AppShape.ctl,
          borderSide: BorderSide(color: AppColors.border),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: AppShape.ctl,
          borderSide: BorderSide(color: AppColors.border),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: AppShape.ctl,
          borderSide: BorderSide(color: AppColors.leaf),
        ),
      ),
    );
  }
}

/// 메일 경고 — 시안: **색 하나로 알리지 않는다.**
/// 적갈 바탕 + 삼각 아이콘 + 문구 세 겹이다 (05-design §10 접근성).
class _MailWarning extends StatelessWidget {
  const _MailWarning();

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(AppSpace.s3),
      decoration: BoxDecoration(
        color: AppColors.dangerSoft,
        borderRadius: AppShape.ctl,
        border: Border.all(color: AppColors.danger, width: AppShape.borderW),
      ),
      child: const Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(Icons.warning_amber, size: 20, color: AppColors.danger),
          SizedBox(width: AppSpace.s2),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(
                  '지원자에게 안내 메일이 나갑니다',
                  style: TextStyle(
                    fontFamily: AppType.fontFamily,
                    fontSize: AppType.sm,
                    fontWeight: AppType.wSemiBold,
                    color: AppColors.danger,
                  ),
                ),
                SizedBox(height: AppSpace.s1),
                Text(
                  '보낸 메일은 취소할 수 없습니다. 확인하고 변경하세요.',
                  style: TextStyle(
                    fontFamily: AppType.fontFamily,
                    fontSize: AppType.caption,
                    color: AppColors.text,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
