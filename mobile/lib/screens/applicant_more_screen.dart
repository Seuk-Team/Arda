/// 지원자 더보기 — 내 정보 · 지원 현황 · 로그아웃 (2026-09-08).
///
/// 담당자 더보기([MoreScreen])와 다른 화면이다: 설정할 것이 거의 없다.
/// 비밀번호도(생년월일이다), 알림 설정도, 권한도 없다.
///
/// **여기 있는 것이 지원자가 아는 자기 정보의 전부다.** 서버가 지원자에게
/// 주는 것은 이름·이메일·공고·단계·지원일뿐이고(ADR-0031), 평가도 담당자
/// 이름도 불합격 사유도 내려오지 않는다.
///
/// 셸이 이미 받아 둔 것을 그린다 — 여기서 서버를 다시 부르지 않는다.
library;

import 'package:flutter/material.dart';

import '../models/applicant_me.dart';
import '../theme/tokens.dart';
import '../utils/format.dart';

class ApplicantMoreScreen extends StatelessWidget {
  const ApplicantMoreScreen({
    super.key,
    required this.me,
    required this.onLeave,
  });

  final ApplicantMe me;

  /// 로그아웃. 셸이 토큰을 지우고 로그인 화면으로 보낸다
  final Future<void> Function() onLeave;

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.all(AppSpace.s4),
      children: [
        _Profile(me: me),
        const SizedBox(height: AppSpace.s3),

        for (final app in me.applications) ...[
          _Card(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const _Label('지원 현황'),
                const SizedBox(height: AppSpace.s3),
                Text(
                  app.postingTitle,
                  style: const TextStyle(
                    fontFamily: AppType.fontFamily,
                    fontSize: AppType.body,
                    fontWeight: AppType.wSemiBold,
                    color: AppColors.text,
                  ),
                ),
                const SizedBox(height: AppSpace.s2),
                // 서버가 준 말을 그대로. `rejected` 가 "불합격" 으로 오지 않는
                // 이유가 여기서도 그대로다 — 담당자가 통보하기 전에 앱이 먼저
                // 말하면 사람이 전할 말을 화면이 앞지른다
                Text(
                  app.stageLabel,
                  style: const TextStyle(
                    fontFamily: AppType.fontFamily,
                    fontSize: AppType.h2,
                    fontWeight: AppType.wSemiBold,
                    color: AppColors.accentText,
                  ),
                ),
                const SizedBox(height: AppSpace.s2),
                Text(
                  '${formatDate(app.appliedAt)} 접수',
                  style: const TextStyle(
                    fontFamily: AppType.fontFamily,
                    fontSize: AppType.caption,
                    fontFeatures: AppType.tabularNums,
                    color: AppColors.textSub,
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: AppSpace.s3),
        ],

        const SizedBox(height: AppSpace.s3),
        SizedBox(
          height: AppLayout.minTouchTarget,
          child: OutlinedButton(onPressed: onLeave, child: const Text('로그아웃')),
        ),
        const SizedBox(height: AppSpace.s4),
        const Center(
          child: Text(
            'Arda 0.1.0',
            style: TextStyle(
              fontFamily: AppType.fontFamily,
              fontSize: AppType.caption,
              color: AppColors.textSub,
            ),
          ),
        ),
      ],
    );
  }
}

/// 이니셜 아바타 + 이름 + 이메일. **사진은 없다** — `applications` 에 사진
/// 컬럼이 없다
class _Profile extends StatelessWidget {
  const _Profile({required this.me});

  final ApplicantMe me;

  @override
  Widget build(BuildContext context) {
    return _Card(
      child: Row(
        children: [
          Container(
            width: 56,
            height: 56,
            alignment: Alignment.center,
            decoration: BoxDecoration(
              color: AppColors.accentSoft,
              shape: BoxShape.circle,
              border: Border.all(
                color: AppColors.border,
                width: AppShape.borderW,
              ),
            ),
            child: Text(
              me.name.isEmpty ? '?' : me.name.characters.first,
              style: const TextStyle(
                fontFamily: AppType.fontFamily,
                fontSize: AppType.h2,
                fontWeight: AppType.wSemiBold,
                color: AppColors.accentText,
              ),
            ),
          ),
          const SizedBox(width: AppSpace.s4),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  me.name,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                    fontFamily: AppType.fontFamily,
                    fontSize: AppType.h2,
                    fontWeight: AppType.wSemiBold,
                    color: AppColors.text,
                  ),
                ),
                const SizedBox(height: AppSpace.s1),
                Text(
                  me.email,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                    fontFamily: AppType.fontFamily,
                    fontSize: AppType.sm,
                    color: AppColors.textSub,
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

class _Card extends StatelessWidget {
  const _Card({required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(AppSpace.s4),
      decoration: BoxDecoration(
        color: AppColors.bgElev,
        borderRadius: AppShape.card,
        border: Border.all(color: AppColors.border, width: AppShape.borderW),
        boxShadow: AppShadow.card,
      ),
      child: child,
    );
  }
}

class _Label extends StatelessWidget {
  const _Label(this.text);

  final String text;

  @override
  Widget build(BuildContext context) => Text(
    text,
    style: const TextStyle(
      fontFamily: AppType.fontFamily,
      fontSize: AppType.caption,
      fontWeight: AppType.wSemiBold,
      color: AppColors.textSub,
    ),
  );
}
