/// 실시간 면접(WebRTC) — 지원자 화면 (2026-09-09, §3-1 앱-웹 통일).
///
/// 웹의 [InterviewLive.tsx]([frontend/app/src/pages/InterviewLive.tsx]) 와
/// 같은 자리다. 담당자(웹 [InterviewRoom.tsx])의 얼굴을 크게 보여 주고 내
/// 카메라를 작게 겹친다.
///
/// [InterviewScreen] (AI 면접) 과 **다른 화면·다른 라우트**다. 카메라를
/// 공유하지 않고 시나리오도 다르다 — 저것은 아르가 진행하는 비대면 면접,
/// 이것은 사람 대 사람 화상 면접이다.
library;

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_webrtc/flutter_webrtc.dart';

import '../data/interview_room_service.dart';
import '../theme/tokens.dart';

class InterviewLiveScreen extends StatefulWidget {
  const InterviewLiveScreen({
    super.key,
    required this.token,
    this.serviceOverride,
  });

  /// 메일 링크의 토큰 — 없으면 담당자가 아직 면접방을 안 연 것이다.
  final String? token;

  /// 테스트가 가짜 서비스를 주입할 때만 쓴다. 실기기에서는 null.
  final InterviewRoomService? serviceOverride;

  @override
  State<InterviewLiveScreen> createState() => _InterviewLiveScreenState();
}

class _InterviewLiveScreenState extends State<InterviewLiveScreen> {
  InterviewRoomService? _service;
  final _localRenderer = RTCVideoRenderer();
  final _remoteRenderer = RTCVideoRenderer();
  bool _renderersReady = false;

  @override
  void initState() {
    super.initState();
    unawaited(_bootstrap());
  }

  Future<void> _bootstrap() async {
    final token = widget.token;
    if (token == null) return;

    await _localRenderer.initialize();
    await _remoteRenderer.initialize();
    if (!mounted) return;
    setState(() => _renderersReady = true);

    final service = widget.serviceOverride ?? InterviewRoomService(token);
    service.addListener(_onServiceChange);
    _service = service;
    if (widget.serviceOverride == null) {
      await service.start();
    }
    _onServiceChange();
  }

  void _onServiceChange() {
    if (!mounted) return;
    final s = _service;
    if (s == null) return;
    _localRenderer.srcObject = s.localStream;
    _remoteRenderer.srcObject = s.remoteStream;
    setState(() {});
  }

  @override
  void dispose() {
    _service?.removeListener(_onServiceChange);
    _service?.dispose();
    _localRenderer.dispose();
    _remoteRenderer.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (widget.token == null) {
      return const _MessageScaffold(
        title: '유효하지 않은 링크',
        body: '안내 메일의 링크를 다시 확인해 주세요.',
      );
    }
    if (!_renderersReady) {
      return const Scaffold(
        backgroundColor: AppColors.bg,
        body: SizedBox.shrink(),
      );
    }

    final service = _service;
    final phase = service?.phase ?? RoomPhase.preparing;
    final error = service?.errorMessage;
    final muted = service?.muted ?? false;
    final waiting = phase != RoomPhase.live;

    return Scaffold(
      backgroundColor: AppColors.bg,
      body: SafeArea(
        child: Column(
          children: [
            _TopBar(phase: phase),
            Expanded(
              child: Stack(
                children: [
                  // 담당자 화면. 지원자가 봐야 하는 얼굴이라 크게.
                  Positioned.fill(
                    child: Container(
                      color: AppColors.bgSunken,
                      child: RTCVideoView(
                        _remoteRenderer,
                        objectFit: RTCVideoViewObjectFit
                            .RTCVideoViewObjectFitContain,
                      ),
                    ),
                  ),
                  if (waiting)
                    _Overlay(
                      phase: phase,
                      error: error,
                    ),
                  // 내 얼굴. 좌우 뒤집기는 flutter_webrtc 의 mirror 옵션으로.
                  Positioned(
                    right: AppSpace.s4,
                    bottom: AppSpace.s4,
                    width: 120,
                    height: 160,
                    child: ClipRRect(
                      borderRadius: AppShape.card,
                      child: Container(
                        color: AppColors.bgElev,
                        child: RTCVideoView(
                          _localRenderer,
                          mirror: true,
                          objectFit: RTCVideoViewObjectFit
                              .RTCVideoViewObjectFitCover,
                        ),
                      ),
                    ),
                  ),
                ],
              ),
            ),
            _ActionBar(
              muted: muted,
              onToggleMute: service?.toggleMute,
              onLeave: () async {
                final nav = Navigator.of(context);
                await service?.leave();
                if (!mounted) return;
                nav.maybePop();
              },
            ),
          ],
        ),
      ),
    );
  }
}

class _TopBar extends StatelessWidget {
  const _TopBar({required this.phase});

  final RoomPhase phase;

  @override
  Widget build(BuildContext context) {
    final live = phase == RoomPhase.live;
    return Container(
      padding: const EdgeInsets.symmetric(
        horizontal: AppSpace.s4,
        vertical: AppSpace.s3,
      ),
      decoration: const BoxDecoration(
        color: AppColors.bgChrome,
        border: Border(
          bottom: BorderSide(color: AppColors.borderSoft),
        ),
      ),
      child: Row(
        children: [
          RichText(
            text: const TextSpan(
              style: TextStyle(
                fontFamily: AppType.fontFamily,
                fontSize: AppType.h1,
                fontWeight: AppType.wSemiBold,
                color: AppColors.text,
              ),
              children: [
                TextSpan(text: 'A', style: TextStyle(color: AppColors.accent)),
                TextSpan(text: 'rda'),
              ],
            ),
          ),
          const Spacer(),
          Container(
            width: 8,
            height: 8,
            margin: const EdgeInsets.only(right: AppSpace.s2),
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: live ? AppColors.ok : AppColors.neutral,
            ),
          ),
          Text(
            phaseLabel(phase),
            style: const TextStyle(
              fontFamily: AppType.fontFamily,
              fontSize: AppType.sm,
              color: AppColors.textSub,
            ),
          ),
        ],
      ),
    );
  }
}

class _Overlay extends StatelessWidget {
  const _Overlay({required this.phase, this.error});

  final RoomPhase phase;
  final String? error;

  @override
  Widget build(BuildContext context) {
    return Positioned.fill(
      child: Container(
        color: const Color(0xB3070B14),
        alignment: Alignment.center,
        padding: const EdgeInsets.all(AppSpace.s5),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              phaseLabel(phase),
              textAlign: TextAlign.center,
              style: const TextStyle(
                fontFamily: AppType.fontFamily,
                fontSize: AppType.h1,
                fontWeight: AppType.wSemiBold,
                color: AppColors.text,
              ),
            ),
            const SizedBox(height: AppSpace.s3),
            Text(
              error ?? '면접관이 들어오면 자동으로 연결됩니다. 잠시만 기다려 주세요.',
              textAlign: TextAlign.center,
              style: const TextStyle(
                fontFamily: AppType.fontFamily,
                fontSize: AppType.body,
                color: AppColors.textSub,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _ActionBar extends StatelessWidget {
  const _ActionBar({
    required this.muted,
    required this.onToggleMute,
    required this.onLeave,
  });

  final bool muted;
  final VoidCallback? onToggleMute;
  final Future<void> Function() onLeave;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(
        horizontal: AppSpace.s4,
        vertical: AppSpace.s3,
      ),
      decoration: const BoxDecoration(
        color: AppColors.bgChrome,
        border: Border(top: BorderSide(color: AppColors.borderSoft)),
      ),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          _BarButton(
            label: muted ? '마이크 켜기' : '마이크 끄기',
            onPressed: onToggleMute,
          ),
          _BarButton(
            label: '면접 나가기',
            emphasis: true,
            onPressed: () => onLeave(),
          ),
        ],
      ),
    );
  }
}

class _BarButton extends StatelessWidget {
  const _BarButton({
    required this.label,
    this.onPressed,
    this.emphasis = false,
  });

  final String label;
  final VoidCallback? onPressed;
  final bool emphasis;

  @override
  Widget build(BuildContext context) {
    return TextButton(
      onPressed: onPressed,
      style: TextButton.styleFrom(
        minimumSize: const Size(120, AppLayout.minTouchTarget),
        backgroundColor:
            emphasis ? AppColors.dangerSoft : AppColors.bgSunken,
        foregroundColor:
            emphasis ? AppColors.danger : AppColors.text,
        shape: const RoundedRectangleBorder(borderRadius: AppShape.ctl),
        textStyle: const TextStyle(
          fontFamily: AppType.fontFamily,
          fontSize: AppType.body,
          fontWeight: AppType.wSemiBold,
        ),
      ),
      child: Text(label),
    );
  }
}

class _MessageScaffold extends StatelessWidget {
  const _MessageScaffold({required this.title, required this.body});

  final String title;
  final String body;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.bg,
      body: SafeArea(
        child: Center(
          child: Padding(
            padding: const EdgeInsets.all(AppSpace.s5),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(
                  title,
                  textAlign: TextAlign.center,
                  style: const TextStyle(
                    fontFamily: AppType.fontFamily,
                    fontSize: AppType.h1,
                    fontWeight: AppType.wSemiBold,
                    color: AppColors.text,
                  ),
                ),
                const SizedBox(height: AppSpace.s3),
                Text(
                  body,
                  textAlign: TextAlign.center,
                  style: const TextStyle(
                    fontFamily: AppType.fontFamily,
                    fontSize: AppType.body,
                    color: AppColors.textSub,
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
