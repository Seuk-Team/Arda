/// 지원자 홈 — 내 지원 현황과 내 면접 (2026-09-08).
///
/// **탭 셸 밖이다.** 하단 탭바도 아르 버튼도 없고, 로그인한 사람도 없다.
/// 지원자에게 계정이 없어서(서버에 지원자용 로그인이 아예 없다) 여기서 신분은
/// 저장해 둔 **링크 토큰**이 전부다.
///
/// ## 카드가 둘로 나뉘어 있는 이유
///
/// 지원 현황(`/public/applications/status/{t}`)과 면접
/// (`/public/interview/{t}`)이 **서로 모르는 사이**다. `PortalStatusOut` 에
/// 면접 세션이 실려 있지 않아, 현황을 봐도 "면접 보러 가기" 로 이어지는 길이
/// 없다. 그래서 링크를 받은 만큼 카드를 따로 그린다.
/// 백엔드가 현황에 면접을 실어 주면 한 흐름으로 합친다.
///
/// ## 죽은 링크를 남겨 두지 않는다
///
/// 포털 토큰은 7일이고 다시 받으면 이전 것이 그 자리에서 죽는다. 그래서 못
/// 여는 카드는 사유를 적고 **지울 수 있게** 둔다 — 안 그러면 앱을 켤 때마다
/// 같은 오류가 쌓인다.
library;

import 'package:flutter/material.dart';

import '../api/api_error.dart';
import '../auth/applicant_store.dart';
import '../data/applicant_demo.dart';
import '../data/applicant_portal_repository.dart';
import '../models/applicant_portal.dart';
import '../routes.dart';
import '../theme/tokens.dart';
import '../utils/format.dart';
import '../widgets/app_top_bar.dart';

/// 카드 한 장이 될 것. 셋 중 하나다
sealed class ApplicantCard {
  const ApplicantCard(this.token);

  final ApplicantToken token;
}

class PortalCard extends ApplicantCard {
  const PortalCard(super.token, this.status);

  final PortalStatus status;
}

class InterviewCard extends ApplicantCard {
  const InterviewCard(super.token, this.interview);

  final InterviewPublic interview;
}

/// 못 연 링크. 지우는 것 말고 할 일이 없다
class DeadCard extends ApplicantCard {
  const DeadCard(super.token, this.message);

  final String message;
}

class ApplicantHomeScreen extends StatefulWidget {
  const ApplicantHomeScreen({super.key, this.portal, this.store});

  /// 테스트가 가짜를 넣는 자리
  final ApplicantPortalRepository? portal;
  final ApplicantStore? store;

  @override
  State<ApplicantHomeScreen> createState() => _ApplicantHomeScreenState();
}

class _ApplicantHomeScreenState extends State<ApplicantHomeScreen> {
  late final ApplicantPortalRepository _portal =
      widget.portal ?? applicantPortal();
  late final ApplicantStore _store = widget.store ?? const ApplicantStore();

  Future<List<ApplicantCard>>? _future;

  @override
  void initState() {
    super.initState();
    _future = _load();
  }

  /// 저장해 둔 링크를 **한꺼번에** 물어본다. 순서대로 기다리면 링크 셋에
  /// 왕복이 셋 쌓인다
  Future<List<ApplicantCard>> _load() async {
    final tokens = await _store.read();
    return Future.wait(tokens.map(_one));
  }

  Future<ApplicantCard> _one(ApplicantToken token) async {
    try {
      return switch (token.kind) {
        ApplicantTokenKind.portal => PortalCard(
          token,
          await _portal.status(token.token),
        ),
        ApplicantTokenKind.interview => InterviewCard(
          token,
          await _portal.interview(token.token),
        ),
      };
    } on ApiError catch (e) {
      // 못 연 것도 카드로 남긴다. 통째로 실패시키면 멀쩡한 링크까지 안 보인다
      return DeadCard(token, e.message);
    }
  }

  // 화살표로 쓰면 안 된다 — 대입식이 Future 를 돌려줘 setState 가 "콜백이
  // async 다" 라고 단언에 걸린다
  void _reload() {
    setState(() {
      _future = _load();
    });
  }

  Future<void> _forget(ApplicantToken token) async {
    await _store.remove(token);
    if (!mounted) return;
    _reload();
  }

  /// 지원자로서 나가기. 담당자 토큰은 건드리지 않는다 — 저장소가 아예 다르다
  Future<void> _leave() async {
    await _store.clear();
    if (!mounted) return;
    Navigator.pushReplacementNamed(context, Routes.login);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: const AppTopBar(title: '내 지원'),
      body: FutureBuilder<List<ApplicantCard>>(
        future: _future,
        builder: (context, snapshot) {
          if (snapshot.connectionState == ConnectionState.waiting) {
            return const Center(child: CircularProgressIndicator());
          }
          final cards = snapshot.data ?? const <ApplicantCard>[];
          return ListView(
            padding: const EdgeInsets.all(AppSpace.s4),
            children: [
              if (cards.isEmpty)
                const _Empty()
              else
                for (final card in cards) ...[
                  _Card(card: card, onForget: () => _forget(card.token)),
                  const SizedBox(height: AppSpace.s3),
                ],
              const SizedBox(height: AppSpace.s4),
              Center(
                child: TextButton(
                  onPressed: _leave,
                  child: const Text('다른 링크로 들어가기'),
                ),
              ),
            ],
          );
        },
      ),
    );
  }
}

class _Empty extends StatelessWidget {
  const _Empty();

  @override
  Widget build(BuildContext context) {
    return const Padding(
      padding: EdgeInsets.symmetric(vertical: AppSpace.s8),
      child: Text(
        '저장된 링크가 없습니다.\n메일로 받은 링크로 다시 들어와 주세요.',
        textAlign: TextAlign.center,
        style: TextStyle(
          fontFamily: AppType.fontFamily,
          fontSize: AppType.sm,
          color: AppColors.textSub,
        ),
      ),
    );
  }
}

class _Card extends StatelessWidget {
  const _Card({required this.card, required this.onForget});

  final ApplicantCard card;
  final VoidCallback onForget;

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
      child: switch (card) {
        PortalCard(:final status) => _PortalBody(status: status),
        InterviewCard(:final interview) => _InterviewBody(interview: interview),
        DeadCard(:final message) => _DeadBody(
          message: message,
          onForget: onForget,
        ),
      },
    );
  }
}

class _PortalBody extends StatelessWidget {
  const _PortalBody({required this.status});

  final PortalStatus status;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const _CardLabel('내 지원 현황'),
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
        // 서버가 준 말을 그대로 쓴다. 내부 단계값으로 되돌려 우리 색을 칠하지
        // 않는다 — `rejected` 를 "불합격" 으로 바꿔 그리면 담당자가 통보하기
        // 전에 화면이 먼저 말하게 된다(backend/app/api/portal.py)
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
    );
  }
}

class _InterviewBody extends StatelessWidget {
  const _InterviewBody({required this.interview});

  final InterviewPublic interview;

  /// 지원자가 지금 무엇을 아는가. 상태값을 그대로 보여 주지 않는다
  String get _line => switch (interview.status) {
    InterviewStatus.pending when interview.consentRequired => '동의 후 시작할 수 있습니다',
    InterviewStatus.pending => '아직 시작하지 않았습니다',
    InterviewStatus.inProgress => '진행 중입니다',
    InterviewStatus.done => '완료했습니다',
    InterviewStatus.expired => '링크 유효 기간이 지났습니다',
  };

  bool get _open =>
      interview.status == InterviewStatus.pending ||
      interview.status == InterviewStatus.inProgress;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const _CardLabel('AI 면접'),
        const SizedBox(height: AppSpace.s3),
        Text(
          interview.postingTitle,
          style: const TextStyle(
            fontFamily: AppType.fontFamily,
            fontSize: AppType.body,
            fontWeight: AppType.wSemiBold,
            color: AppColors.text,
          ),
        ),
        const SizedBox(height: AppSpace.s2),
        Text(
          _line,
          style: const TextStyle(
            fontFamily: AppType.fontFamily,
            fontSize: AppType.sm,
            color: AppColors.textSub,
          ),
        ),
        if (_open) ...[
          const SizedBox(height: AppSpace.s4),
          SizedBox(
            height: AppLayout.minTouchTarget,
            child: FilledButton(
              onPressed: () => Navigator.pushNamed(
                context,
                Routes.interview,
                arguments: interview.token,
              ),
              child: Text(
                interview.status == InterviewStatus.inProgress
                    ? '이어서 보기'
                    : '면접 보러 가기',
              ),
            ),
          ),
        ],
      ],
    );
  }
}

class _DeadBody extends StatelessWidget {
  const _DeadBody({required this.message, required this.onForget});

  final String message;
  final VoidCallback onForget;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const _CardLabel('열 수 없는 링크'),
        const SizedBox(height: AppSpace.s3),
        Text(
          message,
          style: const TextStyle(
            fontFamily: AppType.fontFamily,
            fontSize: AppType.sm,
            color: AppColors.danger,
          ),
        ),
        const SizedBox(height: AppSpace.s3),
        Align(
          alignment: Alignment.centerRight,
          child: TextButton(onPressed: onForget, child: const Text('지우기')),
        ),
      ],
    );
  }
}

class _CardLabel extends StatelessWidget {
  const _CardLabel(this.text);

  final String text;

  @override
  Widget build(BuildContext context) {
    return Text(
      text,
      style: const TextStyle(
        fontFamily: AppType.fontFamily,
        fontSize: AppType.caption,
        fontWeight: AppType.wSemiBold,
        color: AppColors.textSub,
      ),
    );
  }
}
