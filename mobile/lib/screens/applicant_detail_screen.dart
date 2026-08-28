import 'package:flutter/material.dart';

import '../models/applicant.dart';
import '../theme/tokens.dart';
import '../utils/format.dart';
import '../widgets/detail_section.dart';
import '../widgets/stage_label.dart';

/// 지원자 상세 — `mockup-mobile.html` 의 `.dpanel` 을 옮긴 것.
///
/// 목업은 한 페이지 안의 전체 화면 오버레이(`transform:translateX`)로 만들었지만,
/// 앱에서는 별도 화면으로 밀어 올린다. Navigator 가 같은 슬라이드 전환을 주므로
/// 보이는 결과는 같고, 뒤로가기·상태 관리는 플랫폼이 맡는다.
///
/// **헤더·지원 정보까지 만들었다.** 단계 변경 버튼은 다음 조각이다.
class ApplicantDetailScreen extends StatelessWidget {
  const ApplicantDetailScreen({super.key, required this.applicant});

  final Applicant applicant;

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
              child: DetailFieldList(
                fields: {
                  '학력': applicant.education ?? '—',
                  '경력': applicant.careerLabel,
                  '지원일': formatDate(applicant.createdAt),
                },
              ),
            ),
          ),
          const _StageChangeBar(),
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
/// **아직 누르면 아무 일도 일어나지 않는다.** 실제 단계 변경은 큐 8번(API 연동)이고,
/// 어떤 단계로 옮길지 고르는 UI 는 목업에 없다. 모양만 목업대로 맞춰 뒀다.
class _StageChangeBar extends StatelessWidget {
  const _StageChangeBar();

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
              // 큐 8번에서 단계 선택 → API 호출 → 토스트(§6) 로 채운다.
              // 지금은 목업과 같이 눌러도 아무 일도 일어나지 않는다
              onPressed: () {},
              child: const Text('단계 변경'),
            ),
          ),
        ),
      ),
    );
  }
}
