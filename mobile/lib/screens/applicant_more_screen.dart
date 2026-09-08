/// 지원자 더보기 — 내 정보 · 지원 현황 · 나가기 (2026-09-08).
///
/// 담당자 더보기([MoreScreen])와 다른 화면이다: 설정할 것이 거의 없다.
/// 지원자에게 계정이 없어서 비밀번호도, 알림 설정도, 권한도 없다.
///
/// **여기 있는 것이 지원자가 아는 자기 정보의 전부다.** 서버가 지원자에게
/// 주는 것은 이름·공고·단계·지원일 넷뿐이고(`PortalStatusOut`), 평가도
/// 담당자 이름도 불합격 사유도 내려오지 않는다.
library;

import 'package:flutter/material.dart';

import '../api/api_error.dart';
import '../data/applicant_demo.dart';
import '../data/applicant_portal_repository.dart';
import '../models/applicant_portal.dart';
import '../theme/tokens.dart';
import '../utils/format.dart';
import 'applicant_shell.dart';

class ApplicantMoreScreen extends StatefulWidget {
  const ApplicantMoreScreen({
    super.key,
    required this.token,
    required this.onLeave,
    this.portal,
  });

  final String? token;

  /// 지원자로서 나가기. 셸이 저장소를 비우고 로그인으로 보낸다
  final Future<void> Function() onLeave;

  final ApplicantPortalRepository? portal;

  @override
  State<ApplicantMoreScreen> createState() => _ApplicantMoreScreenState();
}

class _ApplicantMoreScreenState extends State<ApplicantMoreScreen> {
  late final ApplicantPortalRepository _portal =
      widget.portal ?? applicantPortal();

  PortalStatus? _status;
  String? _error;

  @override
  void initState() {
    super.initState();
    if (widget.token != null) _load();
  }

  Future<void> _load() async {
    setState(() => _error = null);
    try {
      final status = await _portal.status(widget.token!);
      if (!mounted) return;
      setState(() => _status = status);
    } on ApiError catch (e) {
      if (!mounted) return;
      setState(() => _error = e.message);
    }
  }

  @override
  Widget build(BuildContext context) {
    final status = _status;

    return ListView(
      padding: const EdgeInsets.all(AppSpace.s4),
      children: [
        if (widget.token == null)
          const ApplicantMissing(what: '지원 현황 링크')
        else if (status == null && _error == null)
          const Padding(
            padding: EdgeInsets.symmetric(vertical: AppSpace.s7),
            child: Center(child: CircularProgressIndicator()),
          )
        else if (status == null)
          _Card(
            child: Text(
              _error!,
              style: const TextStyle(
                fontFamily: AppType.fontFamily,
                fontSize: AppType.sm,
                color: AppColors.danger,
              ),
            ),
          )
        else ...[
          _Profile(status: status),
          const SizedBox(height: AppSpace.s3),
          _Card(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const _Label('지원 현황'),
                const SizedBox(height: AppSpace.s3),
                Text(
                  status.postingTitle,
                  style: const TextStyle(
                    fontFamily: AppType.fontFamily,
                    fontSize: AppType.body,
                    fontWeight: AppType.wSemiBold,
                    color: AppColors.text,
                  ),
                ),
                const SizedBox(height: AppSpace.s2),
                // 서버가 준 말을 그대로. 내부 단계값으로 되돌리지 않는다 —
                // 담당자가 통보하기 전에 화면이 먼저 말하면 안 된다
                Text(
                  status.stageLabel,
                  style: const TextStyle(
                    fontFamily: AppType.fontFamily,
                    fontSize: AppType.h2,
                    fontWeight: AppType.wSemiBold,
                    color: AppColors.accentText,
                  ),
                ),
                const SizedBox(height: AppSpace.s2),
                Text(
                  '${formatDate(status.submittedAt)} 접수',
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
        ],

        const SizedBox(height: AppSpace.s5),
        SizedBox(
          height: AppLayout.minTouchTarget,
          child: OutlinedButton(
            onPressed: widget.onLeave,
            child: const Text('로그아웃'),
          ),
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

/// 이니셜 아바타 + 이름. **사진은 없다** — `applications` 에 사진 컬럼이 없다
class _Profile extends StatelessWidget {
  const _Profile({required this.status});

  final PortalStatus status;

  @override
  Widget build(BuildContext context) {
    final name = status.applicantName;
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
              name.isEmpty ? '?' : name.characters.first,
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
                  name,
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
                const Text(
                  '지원자',
                  style: TextStyle(
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
