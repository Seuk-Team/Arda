/// 아르 (에이전트) — 앱 UI 초안(2026-09-01) 조각 14.
///
/// 05-design §0.5: 사이드바 하단 아르 정사각형이 **전 화면 공통 에이전트 진입점**
/// 이고, 누르면 사이드바 오른쪽으로 패널이 늘어난다 — **768px 이하는 덮는 오버레이**
/// ([ADR-0009](../../docs/03_decision/0009-에이전트-UI-위치.md) 2026-08-31 개정).
/// 앱은 그 오버레이 쪽이라 전체 화면 시트로 올린다.
///
/// **아직 서버에 붙지 않았다.** 대화는 목데이터이고 입력칸은 잠겨 있다 —
/// 실제 `POST /agent/chat` 연동은 큐 8이다. 살아 있는 것처럼 보이게 두면
/// 데모에서 오해를 부르므로 입력칸을 **꺼 둔 채로** 둔다.
///
/// 05-design §1 (2026-09-01 팀장 확정): 앰버는 **사람의 확정을 기다리는 것**에만
/// 쓴다. 앱의 아르는 지원자를 **찾아 주기까지**만 하고 확정 버튼을 두지 않으므로,
/// 명단 카드는 앰버 점선이 아니라 정보 블록이다.
///
/// 단계 변경은 지원자 상세 하단 하나로 모은다 — 같은 일을 두 자리에서 할 수 있으면
/// 어느 쪽이 진짜인지 헷갈린다. 서버의 `pending_action → /agent/confirm` 2단은
/// 그대로 있고, 앱이 그 길을 쓰게 되면 그때 §1 대로 앰버 점선 카드를 되살린다.
library;

import 'package:flutter/material.dart';

import '../data/mock_data.dart';
import '../models/ar_message.dart';
import '../routes.dart';
import '../theme/tokens.dart';

/// 전 화면 공통 진입점이 여는 시트.
Future<void> showArSheet(BuildContext context) {
  return Navigator.of(context).push(
    MaterialPageRoute(fullscreenDialog: true, builder: (_) => const ArScreen()),
  );
}

class ArScreen extends StatelessWidget {
  const ArScreen({super.key, this.messages});

  final List<ArMessage>? messages;

  @override
  Widget build(BuildContext context) {
    final thread = messages ?? mockArThread;

    return Scaffold(
      backgroundColor: AppColors.bg,
      body: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const _ArHeader(),
          Expanded(
            child: ListView(
              padding: const EdgeInsets.all(AppSpace.s4),
              children: [
                for (final message in thread) ...[
                  _Bubble(message: message),
                  if (message.findings != null) ...[
                    const SizedBox(height: AppSpace.s2),
                    _FindingsCard(findings: message.findings!),
                  ],
                  const SizedBox(height: AppSpace.s3),
                ],
              ],
            ),
          ),
          const _InputBar(),
        ],
      ),
    );
  }
}

/// 머리 — 아바타 · 이름 · 부제 · 닫기. 배포판과 같은 흰 패널이다.
class _ArHeader extends StatelessWidget {
  const _ArHeader();

  @override
  Widget build(BuildContext context) {
    return Container(
      // 배포판(2026-09-01)은 머리도 흰 패널이다. 연두 바탕이던 것을 맞췄다 —
      // 아르가 사는 자리가 사이드바라 연두로 뒀었지만, 웹이 흰색으로 갔다
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
            AppSpace.s4,
            AppSpace.s2,
            AppSpace.s2,
            AppSpace.s2,
          ),
          child: Row(
            children: [
              const ArAvatar(size: 32),
              const SizedBox(width: AppSpace.s2),
              // 배포판은 이름과 부제가 한 줄이다 — "아르  에이전트"
              const Text(
                '아르',
                style: TextStyle(
                  fontFamily: AppType.fontFamily,
                  fontSize: AppType.h2,
                  fontWeight: FontWeight.w700,
                  color: AppColors.text,
                  shadows: AppTextShadow.heading,
                ),
              ),
              const SizedBox(width: AppSpace.s2),
              const Expanded(
                child: Text(
                  // 배포판 문구. "채용 도우미" 였던 것을 맞췄다
                  '에이전트',
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    fontFamily: AppType.fontFamily,
                    fontSize: AppType.sm,
                    color: AppColors.textSub,
                  ),
                ),
              ),
              _CloseButton(onPressed: () => Navigator.pop(context)),
            ],
          ),
        ),
      ),
    );
  }
}

class _CloseButton extends StatelessWidget {
  const _CloseButton({required this.onPressed});

  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      button: true,
      label: '닫기',
      child: Material(
        color: Colors.transparent,
        shape: const CircleBorder(),
        clipBehavior: Clip.antiAlias,
        child: InkWell(
          onTap: onPressed,
          highlightColor: AppColors.sunkenHover,
          splashColor: AppColors.sunkenHover,
          // §9 터치 타깃 44
          child: const SizedBox(
            width: AppLayout.minTouchTarget,
            height: AppLayout.minTouchTarget,
            child: Icon(Icons.close, size: 24, color: AppColors.text),
          ),
        ),
      ),
    );
  }
}

/// 아르 얼굴 — 진입점(FAB·상단바)과 시트 머리가 같이 쓴다.
class ArAvatar extends StatelessWidget {
  const ArAvatar({super.key, required this.size});

  final double size;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: size,
      height: size,
      clipBehavior: Clip.antiAlias,
      // 바탕은 흰색이다 — assets/images/ar.png 이 흰 배경이라 같은 색이어야
      // 원 가장자리에 이음매가 안 보인다.
      //
      // **테두리를 두지 않는다.** 원형 클립이 이미지를 바깥 원까지 그려서 링이
      // 군데군데 덮이고, 남은 조각만 초록 틈처럼 보였다. 웹도 링 없이 캐릭터만 쓴다.
      //
      // 그림은 런처 아이콘 원본에서 **여백을 잘라 낸** 것이다. 원본은 캔버스의
      // 75%만 그림이라 원 안이 휑했다. 자를 때 뿔이 원에 걸리지 않도록
      // 세로 반지름보다 큰 한 변(766 중 740)을 썼다
      decoration: const BoxDecoration(
        color: AppColors.bgElev,
        shape: BoxShape.circle,
      ),
      child: Image.asset(
        'assets/images/ar.png',
        fit: BoxFit.cover,
        excludeFromSemantics: true,
      ),
    );
  }
}

/// 말풍선 — 아르는 왼쪽 흰 카드, 나는 오른쪽 잎초록.
class _Bubble extends StatelessWidget {
  const _Bubble({required this.message});

  final ArMessage message;

  @override
  Widget build(BuildContext context) {
    final mine = message.speaker == ArSpeaker.me;

    // 배포판은 아르 말풍선 왼쪽에 작은 아바타를 둔다 — 누가 한 말인지가
    // 색·모양 말고 얼굴로도 읽힌다
    if (!mine) {
      return Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const ArAvatar(size: 28),
          const SizedBox(width: AppSpace.s2),
          Flexible(child: _bubble(mine: false)),
        ],
      );
    }

    return Align(alignment: Alignment.centerRight, child: _bubble(mine: true));
  }

  Widget _bubble({required bool mine}) {
    return Container(
      constraints: const BoxConstraints(maxWidth: 280),
      padding: const EdgeInsets.symmetric(
        horizontal: AppSpace.s3,
        vertical: AppSpace.s3,
      ),
      decoration: BoxDecoration(
        color: mine ? AppColors.leaf : AppColors.bgElev,
        // 말하는 쪽 모서리만 각지게 — 누가 한 말인지 모양으로도 갈린다
        borderRadius: BorderRadius.only(
          topLeft: mine ? AppShape.rCard : const Radius.circular(2),
          topRight: mine ? const Radius.circular(2) : AppShape.rCard,
          bottomLeft: AppShape.rCard,
          bottomRight: AppShape.rCard,
        ),
        border: mine
            ? null
            : Border.all(color: AppColors.border, width: AppShape.borderW),
        boxShadow: mine ? null : AppShadow.card,
      ),
      child: Text(
        message.text,
        style: TextStyle(
          fontFamily: AppType.fontFamily,
          fontSize: AppType.body,
          height: 1.5,
          color: mine ? AppColors.bgElev : AppColors.text,
          // §2: 색 채움 위 밝은 글자엔 onFill
          shadows: mine ? AppTextShadow.onFill : null,
        ),
      ),
    );
  }
}

/// 아르가 찾아 준 지원자 명단 — **읽기만 하는 정보 블록이다.**
///
/// 05-design §1 (2026-09-01 팀장 확정): 앰버는 **사람의 확정을 기다리는 것**에만
/// 쓴다. 이 카드에는 확정 버튼이 없으므로 앰버 점선이 아니라 상세의 아르의 요약과
/// 같은 정보 블록(`--bg-sunken` + `--border-soft`)이다.
///
/// **단계 변경 버튼을 여기 두지 않는다.** 같은 일을 두 자리에서 할 수 있으면
/// 어느 쪽이 진짜인지 헷갈린다 — 단계 변경은 지원자 상세 하단 하나로 모은다.
/// 서버는 여전히 `pending_action → /agent/confirm` 2단을 갖고 있고, 앱이 그 길을
/// 쓰게 되면 그때 §1 대로 앰버 점선 카드를 되살린다.
class _FindingsCard extends StatelessWidget {
  const _FindingsCard({required this.findings});

  final ArFindings findings;

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: Alignment.centerLeft,
      child: Container(
        constraints: const BoxConstraints(maxWidth: 300),
        padding: const EdgeInsets.all(AppSpace.s3),
        decoration: BoxDecoration(
          color: AppColors.bgSunken,
          borderRadius: AppShape.card,
          border: Border.all(
            color: AppColors.borderSoft,
            width: AppShape.borderW,
          ),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              // 출처는 제목이 말한다 — §1 의 "아르의 요약"과 같은 방식
              findings.title,
              style: const TextStyle(
                fontFamily: AppType.fontFamily,
                fontSize: AppType.caption,
                fontWeight: FontWeight.w700,
                color: AppColors.text,
              ),
            ),
            for (final applicant in findings.applicants)
              _FoundRow(applicant: applicant),
          ],
        ),
      ),
    );
  }
}

/// 명단의 한 줄 — 이름 · 재료 · 아르의 요지 · [지원자 정보 보기].
///
/// 면접에 부를지 정하려면 이력서·평가·메모까지 봐야 하는데 그게 전부 상세에 있다.
/// 그래서 "이력서 보기" 가 아니라 상세로 보낸다 — 이력서 열람은 아직 없기도 하다(W5).
///
/// 아르 화면은 `Navigator.push` 로 떠 있어, 상세를 열었다 돌아와도 명단이 남는다.
class _FoundRow extends StatelessWidget {
  const _FoundRow({required this.applicant});

  final FoundApplicant applicant;

  void _openDetail(BuildContext context) {
    final target = mockApplicants.firstWhere(
      (a) => a.id == applicant.applicationId,
    );
    final posting = mockPostings.firstWhere((p) => p.id == target.jobPostingId);
    Navigator.pushNamed(
      context,
      Routes.applicantDetail,
      arguments: (target, posting.title),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(top: AppSpace.s3),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(
            applicant.name,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(
              fontFamily: AppType.fontFamily,
              fontSize: AppType.sm,
              fontWeight: AppType.wSemiBold,
              color: AppColors.text,
            ),
          ),
          Text(
            applicant.meta,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(
              fontFamily: AppType.fontFamily,
              fontSize: AppType.caption,
              color: AppColors.textSub,
            ),
          ),
          if (applicant.gist != null) ...[
            const SizedBox(height: AppSpace.s2),
            Text(
              // 상세의 아르의 요약 요지와 같은 값이다. 여기서 줄이지 않는다 —
              // 에이전트가 이미 2문장·160자로 만들어 준다(35ba4b5)
              applicant.gist!,
              style: const TextStyle(
                fontFamily: AppType.fontFamily,
                fontSize: AppType.caption,
                height: 1.55,
                color: AppColors.text,
              ),
            ),
          ],
          const SizedBox(height: AppSpace.s2),
          _ActionButton(
            label: '지원자 정보 보기',
            filled: false,
            onTap: () => _openDetail(context),
          ),
        ],
      ),
    );
  }
}

class _ActionButton extends StatelessWidget {
  const _ActionButton({
    required this.label,
    required this.filled,
    required this.onTap,
  });

  final String label;
  final bool filled;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    return Material(
      // 사람이 확정하는 버튼이라 **잎초록 실선** — 제안(앰버 점선)과 대비된다
      color: filled ? AppColors.leaf : AppColors.bgElev,
      borderRadius: AppShape.ctl,
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: onTap,
        highlightColor: filled ? AppColors.leafStrong : AppColors.bgSunken,
        splashColor: filled ? AppColors.leafStrong : AppColors.bgSunken,
        child: Container(
          height: AppLayout.minTouchTarget,
          alignment: Alignment.center,
          decoration: BoxDecoration(
            borderRadius: AppShape.ctl,
            border: filled
                ? null
                : Border.all(color: AppColors.border, width: AppShape.borderW),
          ),
          child: Text(
            label,
            softWrap: false,
            style: TextStyle(
              fontFamily: AppType.fontFamily,
              fontSize: AppType.sm,
              fontWeight: AppType.wSemiBold,
              color: filled ? AppColors.bgElev : AppColors.textSub,
              shadows: filled ? AppTextShadow.onFill : null,
            ),
          ),
        ),
      ),
    );
  }
}

/// 입력줄 — **아직 잠겨 있다.** 큐 8에서 `POST /agent/chat` 에 붙는다.
class _InputBar extends StatelessWidget {
  const _InputBar();

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: const BoxDecoration(
        color: AppColors.bgElev,
        border: Border(
          top: BorderSide(color: AppColors.border, width: AppShape.borderW),
        ),
      ),
      child: SafeArea(
        top: false,
        child: Padding(
          padding: const EdgeInsets.all(AppSpace.s3),
          child: Row(
            children: [
              Expanded(
                child: Container(
                  height: AppLayout.minTouchTarget,
                  padding: const EdgeInsets.symmetric(horizontal: AppSpace.s4),
                  alignment: Alignment.centerLeft,
                  decoration: BoxDecoration(
                    color: AppColors.bgSunken,
                    borderRadius: AppShape.pill,
                    border: Border.all(
                      color: AppColors.border,
                      width: AppShape.borderW,
                    ),
                  ),
                  child: const Text(
                    '아르에게 물어보기',
                    style: TextStyle(
                      fontFamily: AppType.fontFamily,
                      fontSize: AppType.body,
                      color: AppColors.textSub,
                    ),
                  ),
                ),
              ),
              const SizedBox(width: AppSpace.s2),
              Container(
                width: AppLayout.minTouchTarget,
                height: AppLayout.minTouchTarget,
                alignment: Alignment.center,
                decoration: const BoxDecoration(
                  // 비활성 — 테마의 disabledBackgroundColor 와 같은 단계
                  color: AppColors.bgSunken,
                  shape: BoxShape.circle,
                ),
                child: const Icon(
                  Icons.arrow_forward,
                  size: 20,
                  color: AppColors.textSub,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
