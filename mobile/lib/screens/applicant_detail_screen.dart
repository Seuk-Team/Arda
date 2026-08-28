import 'package:flutter/material.dart';

import '../models/applicant.dart';
import '../routes.dart';
import '../theme/tokens.dart';
import '../utils/format.dart';
import '../widgets/detail_section.dart';
import '../widgets/stage_change_sheet.dart';
import '../widgets/stage_label.dart';

/// 지원자 상세 — `mockup-mobile.html` 의 `.dpanel` 을 옮긴 것.
///
/// 목업은 한 페이지 안의 전체 화면 오버레이(`transform:translateX`)로 만들었지만,
/// 앱에서는 별도 화면으로 밀어 올린다. Navigator 가 같은 슬라이드 전환을 주므로
/// 보이는 결과는 같고, 뒤로가기·상태 관리는 플랫폼이 맡는다.
///
/// 시안 2·3번에 따라 단계 이력·평가는 별도 화면으로 나갔고, 여기서는 그 입구만 둔다.
class ApplicantDetailScreen extends StatelessWidget {
  const ApplicantDetailScreen({
    super.key,
    required this.applicant,
    required this.postingTitle,
  });

  final Applicant applicant;

  /// 단계 이력 화면의 부제에 쓴다 — "김도현 · 백엔드 개발자 (신입)"
  final String postingTitle;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.bg,
      body: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          _Header(applicant: applicant),
          Expanded(
            child: SingleChildScrollView(
              // 시안: 화면 여백 16dp
              padding: const EdgeInsets.all(AppSpace.s4),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  DetailFieldList(
                    fields: {
                      '학력': applicant.education ?? '—',
                      '경력': applicant.careerLabel,
                      '지원일': formatDate(applicant.createdAt),
                    },
                  ),

                  // 시안 2·3번: 단계 이력과 평가는 상세 안의 섹션이 아니라
                  // 별도 화면이다. 코멘트가 길어 여기 끼우면 지원 정보가 밀린다
                  const SizedBox(height: AppSpace.s3),
                  _LinkRow(
                    icon: Icons.history,
                    label: '단계 이력',
                    onTap: () => Navigator.pushNamed(
                      context,
                      Routes.stageHistory,
                          arguments: (applicant, postingTitle),
                    ),
                  ),
                  const SizedBox(height: AppSpace.s3),
                  _LinkRow(
                    icon: Icons.star_outline,
                    label: '평가',
                    onTap: () => Navigator.pushNamed(
                      context,
                      Routes.evaluations,
                      arguments: applicant,
                    ),
                  ),
                ],
              ),
            ),
          ),
          _StageChangeBar(applicant: applicant),
        ],
      ),
    );
  }
}

/// 상세 헤더 — 시안(2026-08-28): 왼쪽 뒤로가기 · 이름 · 오른쪽 단계 칩.
///
/// 목업(.dhead)은 오른쪽 위 X 로 닫는 오버레이였지만, 시안은 전 화면이
/// 왼쪽 뒤로가기(←)를 쓴다. 공고 → 지원자 → 상세로 파고드는 계층이라
/// 안드로이드의 뒤로가기와 방향이 같다.
class _Header extends StatelessWidget {
  const _Header({required this.applicant});

  final Applicant applicant;

  @override
  Widget build(BuildContext context) {
    return Container(
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
            AppSpace.s2,
            AppSpace.s2,
            AppSpace.s4,
            AppSpace.s2,
          ),
          child: Row(
            children: [
              _BackButton(onPressed: () => Navigator.pop(context)),
              const SizedBox(width: AppSpace.s2),
              // 05-design §7: 긴 이름은 한 줄 ellipsis
              Expanded(
                child: Text(
                  applicant.name,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  softWrap: false,
                  style: const TextStyle(
                    fontFamily: AppType.fontFamily,
                    fontSize: AppType.h1,
                    fontWeight: FontWeight.w700,
                    letterSpacing: -0.22,
                    color: AppColors.text,
                    shadows: AppTextShadow.heading,
                  ),
                ),
              ),
              const SizedBox(width: AppSpace.s3),
              StageLabel(stage: applicant.currentStage),
            ],
          ),
        ),
      ),
    );
  }
}

/// 뒤로가기 — 시안은 테두리 없는 맨 화살표다. 44×44 터치 타깃은 유지한다 (§9).
class _BackButton extends StatelessWidget {
  const _BackButton({required this.onPressed});

  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      button: true,
      label: '뒤로',
      child: Material(
        color: Colors.transparent,
        shape: const CircleBorder(),
        clipBehavior: Clip.antiAlias,
        child: InkWell(
          onTap: onPressed,
          // §5: 모바일은 hover 없음 전제 — press 만 정의한다
          highlightColor: AppColors.bgSunken,
          splashColor: AppColors.bgSunken,
          child: const SizedBox(
            width: AppLayout.minTouchTarget,
            height: AppLayout.minTouchTarget,
            child: Icon(Icons.arrow_back, size: 24, color: AppColors.text),
          ),
        ),
      ),
    );
  }
}
/// 목업 `.dfoot` — 화면 아래에 붙는 단계 변경 줄.
///
/// 05-design §10: 드래그가 없는 환경의 **유일한 단계 이동 수단**이다.
/// 모바일은 칸반을 쓰지 않으므로(§9) 이 버튼이 그 자리를 대신한다.
///
/// 누르면 확인 시트가 열린다(시안 1번). **시트에서 확정해도 아직 서버에 보내지
/// 않는다** — 실제 호출은 큐 8번(API 연동)이다. 지금은 고른 값을 토스트로 되비춘다.
class _StageChangeBar extends StatelessWidget {
  const _StageChangeBar({required this.applicant});

  final Applicant applicant;

  /// 시안 1번: 고르는 순간 실행되지 않는다. 시트에서 확정해야 넘어간다.
  Future<void> _openSheet(BuildContext context) async {
    final picked = await showStageChangeSheet(context, applicant: applicant);
    if (picked == null || !context.mounted) return;

    // 05-design §6: 단계 이동 성공·실패는 토스트로 — 조용히 지나가면 안 된다.
    // 큐 8번에서 이 자리가 실제 API 호출 결과로 바뀐다.
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(
          '${applicant.name} — ${picked.stage.label}으로 변경 '
          '(아직 저장되지 않음)',
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: const BoxDecoration(
        color: AppColors.bgElev,
        border: Border(
          top: BorderSide(color: AppColors.border, width: AppShape.borderW),
        ),
      ),
      // SafeArea 를 높이 제약 **바깥**에 둔다. 안쪽에 두면 내비게이션 바가
      // 차지하는 만큼 72px 안에서 깎여 버튼 위아래 여백이 사라진다
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
              onPressed: () => _openSheet(context),
              child: const Text('단계 변경'),
            ),
          ),
        ),
      ),
    );
  }
}

/// 다른 화면으로 가는 줄 — 단계 이력·평가.
///
/// 시안 2·3번이 둘을 별도 화면으로 뺐다. 상세에 그대로 끼우면
/// 코멘트가 길어 지원 정보가 아래로 밀린다.
class _LinkRow extends StatelessWidget {
  const _LinkRow({
    required this.icon,
    required this.label,
    required this.onTap,
  });

  final IconData icon;
  final String label;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: AppColors.bgElev,
      shape: const RoundedRectangleBorder(
        borderRadius: AppShape.card,
        side: BorderSide(color: AppColors.border, width: AppShape.borderW),
      ),
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: onTap,
        // §5: 모바일은 hover 없음 전제 — press 만 정의한다
        highlightColor: AppColors.bgSunken,
        splashColor: AppColors.bgSunken,
        child: Container(
          // §9 터치 타깃
          constraints: const BoxConstraints(minHeight: AppLayout.minTouchTarget),
          padding: const EdgeInsets.all(AppSpace.s4),
          child: Row(
            children: [
              Icon(icon, size: 20, color: AppColors.textSub),
              const SizedBox(width: AppSpace.s3),
              Expanded(
                child: Text(
                  label,
                  style: const TextStyle(
                    fontFamily: AppType.fontFamily,
                    fontSize: AppType.body,
                    fontWeight: AppType.wSemiBold,
                    color: AppColors.text,
                  ),
                ),
              ),
              const Icon(
                Icons.chevron_right,
                size: 20,
                color: AppColors.textSub,
              ),
            ],
          ),
        ),
      ),
    );
  }
}
