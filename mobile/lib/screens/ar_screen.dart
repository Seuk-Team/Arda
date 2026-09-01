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
/// 05-design §1 AI 규약(불변): **앰버 점선 = AI 제안 / 잎초록 실선 = 사람 확정.**
/// 아르가 내놓은 실행 제안은 점선 카드 안에 있고, 승인 버튼을 누르기 전에는
/// 아무 일도 일어나지 않는다(API 도 `pending_action` → `/agent/confirm` 2단이다).
library;

import 'package:flutter/material.dart';

import '../data/mock_data.dart';
import '../models/ar_message.dart';
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
                  if (message.pendingAction != null) ...[
                    const SizedBox(height: AppSpace.s2),
                    _SuggestionCard(action: message.pendingAction!),
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

/// 머리 — 사이드바 색을 그대로 쓴다. 아르가 사는 자리가 사이드바라서,
/// 앱에서도 같은 연두 바탕이어야 "그 아르"로 읽힌다.
class _ArHeader extends StatelessWidget {
  const _ArHeader();

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: const BoxDecoration(
        color: AppColors.sidebarBg,
        border: Border(
          bottom: BorderSide(
            color: AppColors.sidebarLine,
            width: AppShape.borderW,
          ),
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
              const ArAvatar(size: 36),
              const SizedBox(width: AppSpace.s3),
              const Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(
                      '아르',
                      style: TextStyle(
                        fontFamily: AppType.fontFamily,
                        fontSize: AppType.h2,
                        fontWeight: FontWeight.w700,
                        color: AppColors.text,
                        shadows: AppTextShadow.heading,
                      ),
                    ),
                    Text(
                      '채용 도우미',
                      style: TextStyle(
                        fontFamily: AppType.fontFamily,
                        fontSize: AppType.caption,
                        color: AppColors.leaf,
                      ),
                    ),
                  ],
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
      decoration: const BoxDecoration(
        color: AppColors.sidebarBg,
        shape: BoxShape.circle,
        border: Border.fromBorderSide(
          BorderSide(color: AppColors.sidebarLine, width: AppShape.borderW),
        ),
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

    return Align(
      alignment: mine ? Alignment.centerRight : Alignment.centerLeft,
      child: Container(
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
      ),
    );
  }
}

/// 아르 제안 카드 — **앰버 점선**(05-design §1 AI 규약, 불변).
///
/// 실선은 사람이 확정한 것에만 쓴다. 승인 버튼을 눌러야 `/agent/confirm` 이
/// 돌고, 그 전까지는 아무 일도 일어나지 않는다.
class _SuggestionCard extends StatelessWidget {
  const _SuggestionCard({required this.action});

  final PendingAction action;

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: Alignment.centerLeft,
      child: Container(
        constraints: const BoxConstraints(maxWidth: 300),
        padding: const EdgeInsets.all(AppSpace.s3),
        decoration: ShapeDecoration(
          color: AppColors.aiSoft,
          shape: _DashedBorder(color: AppColors.ai, radius: AppShape.rCard),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              // §1: "AI 점수 박스엔 '확정은 담당자가 합니다' 상시 표기"와 같은 결
              '아르 제안 · 확인 필요',
              style: const TextStyle(
                fontFamily: AppType.fontFamily,
                fontSize: AppType.caption,
                fontWeight: FontWeight.w700,
                color: AppColors.ai,
              ),
            ),
            const SizedBox(height: AppSpace.s2),
            Text(
              action.description,
              style: const TextStyle(
                fontFamily: AppType.fontFamily,
                fontSize: AppType.sm,
                color: AppColors.text,
              ),
            ),
            for (final target in action.targets) ...[
              const SizedBox(height: AppSpace.s2),
              Row(
                children: [
                  Expanded(
                    child: Text(
                      target.name,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                        fontFamily: AppType.fontFamily,
                        fontSize: AppType.sm,
                        fontWeight: AppType.wSemiBold,
                        color: AppColors.text,
                      ),
                    ),
                  ),
                  const SizedBox(width: AppSpace.s2),
                  Text(
                    '${target.stageLabel} · ${target.meta}',
                    softWrap: false,
                    style: const TextStyle(
                      fontFamily: AppType.fontFamily,
                      fontSize: AppType.caption,
                      color: AppColors.textSub,
                    ),
                  ),
                ],
              ),
            ],
            const SizedBox(height: AppSpace.s3),
            Row(
              children: [
                Expanded(
                  child: _ActionButton(
                    label: action.confirmLabel,
                    filled: true,
                    // 큐 8: 여기가 POST /agent/confirm 이 된다
                    onTap: null,
                  ),
                ),
                const SizedBox(width: AppSpace.s2),
                Expanded(
                  child: _ActionButton(label: '닫기', filled: false, onTap: null),
                ),
              ],
            ),
          ],
        ),
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

/// 점선 테두리 — Flutter 의 `Border` 에는 dashed 가 없어 직접 그린다.
///
/// 05-design §1 이 **앰버 점선**을 AI 제안의 불변 규약으로 못 박았으므로,
/// 실선으로 대신하지 않는다.
class _DashedBorder extends ShapeBorder {
  const _DashedBorder({
    required this.color,
    required this.radius,
    this.dash = 4,
    this.gap = 3,
    this.width = 1,
  });

  final Color color;
  final Radius radius;
  final double dash;
  final double gap;
  final double width;

  @override
  EdgeInsetsGeometry get dimensions => EdgeInsets.all(width);

  @override
  Path getInnerPath(Rect rect, {TextDirection? textDirection}) =>
      Path()..addRRect(RRect.fromRectAndRadius(rect.deflate(width), radius));

  @override
  Path getOuterPath(Rect rect, {TextDirection? textDirection}) =>
      Path()..addRRect(RRect.fromRectAndRadius(rect, radius));

  @override
  void paint(Canvas canvas, Rect rect, {TextDirection? textDirection}) {
    final paint = Paint()
      ..color = color
      ..style = PaintingStyle.stroke
      ..strokeWidth = width;

    final path = Path()
      ..addRRect(RRect.fromRectAndRadius(rect.deflate(width / 2), radius));

    for (final metric in path.computeMetrics()) {
      var distance = 0.0;
      while (distance < metric.length) {
        final end = (distance + dash).clamp(0.0, metric.length);
        canvas.drawPath(metric.extractPath(distance, end), paint);
        distance = end + gap;
      }
    }
  }

  @override
  ShapeBorder scale(double t) => _DashedBorder(
    color: color,
    radius: radius,
    dash: dash,
    gap: gap,
    width: width * t,
  );
}
