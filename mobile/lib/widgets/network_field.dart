/// 딥 노드 네트워크 — 로그인 화면 배경 (2026-09-08).
///
/// 05-design §0.0 이 브랜드를 이렇게 정의한다: **어두운 우주 바탕 위 시안 →
/// 블루 → 바이올렛으로 흐르는 노드망.** 웹 로그인은 이미 이걸 깔고 있는데
/// (`frontend/app/src/lib/networkScene.ts`) 앱은 그냥 검은 바탕이었다.
///
/// 깊이는 "구간을 나눠 따로 흐리고 다시 합치는" 방식으로 만든다:
///   1) 노드를 3D 상자에 흩고 원근 투영한다. 화면 크기 s 가 곧 깊이다.
///   2) s 로 세 구간(먼/중간/가까운)을 나눈다.
///   3) 먼 구간일수록 크게 흐리고 그 위에 어두운 안개를 덮는다 → 공기 원근.
///
/// 연결선은 매 프레임 거리로 잇지 않는다. 처음에 최근접 이웃으로 **고정
/// 그래프**를 만들어 두어야 선이 깜빡이지 않고, 그 위로 펄스가 일정한 경로를
/// 흐른다.
///
/// ## 웹보다 가볍게 간다
///
/// 노드 170 → **70**, 블룸은 허브에만 한 겹. 커서 자기장은 뺐다 — 폰에는
/// 커서가 없다. 흐림은 구간마다 [ui.ImageFilter] 레이어 하나씩만 쓴다:
/// 원마다 [MaskFilter] 를 걸면 70번 흐리게 되어 저사양 폰에서 프레임이 떨어진다.
library;

import 'dart:math' as math;
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';

import '../theme/tokens.dart';

/// 노드 수. 웹은 170 이지만 폰은 화면이 작아 그만큼 필요 없다
const _count = 70;

/// 배경 팔레트의 정점들. 노드 색은 이 넷 사이를 오간다 —
/// 05-design §0.0 의 "시안 → 블루 → 바이올렛" 이 이 순서다
const _anchor = <List<int>>[
  [56, 130, 246],
  [34, 211, 238],
  [139, 92, 246],
  [125, 211, 252],
];

/// 성운 — 망 뒤에 깔리는 거대한 색 안개. 빈 공간이 그냥 검게 남으면 "우주" 가
/// 아니라 그냥 어두운 화면이 된다. 아주 느리게 흐른다
const _nebula = <_Neb>[
  _Neb(Color(0xFF3882F6), .22, .26, .95, .22, .000021, 0.0),
  _Neb(Color(0xFF8B5CF6), .78, .22, .82, .19, .000017, 1.9),
  _Neb(Color(0xFF22D3EE), .18, .78, .74, .14, .000025, 5.2),
  _Neb(Color(0xFF10B981), .70, .82, .70, .10, .000013, 3.6),
];

class _Neb {
  const _Neb(this.color, this.x, this.y, this.r, this.a, this.sp, this.ph);

  final Color color;
  final double x, y, r, a, sp, ph;
}

/// 깊이 구간. `max` 는 이 구간에 드는 화면 크기의 상한
const _bands = <_Band>[
  _Band(.70, 3.4, .20),
  _Band(.92, 1.2, .09),
  _Band(9.99, 0, 0),
];

class _Band {
  const _Band(this.max, this.blur, this.fog);

  final double max, blur, fog;
}

class _Node {
  _Node(math.Random rnd)
    : bx = rnd.nextDouble() * 2 - 1,
      by = rnd.nextDouble() * 2 - 1,
      bz = rnd.nextDouble() * 2 - 1,
      hub = rnd.nextDouble() < .16,
      color = _mix(rnd.nextDouble()),
      ph = rnd.nextDouble() * math.pi * 2,
      sp = .00016 + rnd.nextDouble() * .00028,
      amp = .04 + rnd.nextDouble() * .09;

  final double bx, by, bz;
  final bool hub;
  final Color color;
  final double ph, sp, amp;

  /// 매 프레임 다시 채운다 — 투영된 자리와 깊이
  double x = 0, y = 0, s = 1;
  int band = 2;
}

class _Edge {
  _Edge(this.a, this.b, this.ph, this.sp);

  final int a, b;
  final double ph, sp;
}

Color _mix(double u) {
  final f = u.clamp(0.0, .9999) * (_anchor.length - 1);
  final i = f.floor();
  final k = f - i;
  final a = _anchor[i], b = _anchor[i + 1];
  return Color.fromARGB(
    255,
    (a[0] + (b[0] - a[0]) * k).round(),
    (a[1] + (b[1] - a[1]) * k).round(),
    (a[2] + (b[2] - a[2]) * k).round(),
  );
}

class NetworkField extends StatefulWidget {
  const NetworkField({super.key, this.dim = 0});

  /// 인트로 감광 0~1. 배경을 눌러 글자에 자리를 내준다
  final double dim;

  @override
  State<NetworkField> createState() => _NetworkFieldState();
}

class _NetworkFieldState extends State<NetworkField>
    with SingleTickerProviderStateMixin {
  late final Ticker _ticker;
  late final List<_Node> _nodes;
  late final List<_Edge> _edges;

  /// 다시 그릴 때마다 페인터에 넘기는 시각(ms)
  final _clock = ValueNotifier<double>(0);

  @override
  void initState() {
    super.initState();
    // 씨앗을 고정한다 — 다시 그릴 때마다 배치가 새로 뽑히면 화면이 튄다
    final rnd = math.Random(20260908);
    _nodes = [for (var i = 0; i < _count; i++) _Node(rnd)];
    _edges = _link(_nodes, rnd);

    _ticker = createTicker((d) => _clock.value = d.inMicroseconds / 1000.0);
  }

  /// **동작 줄이기면 돌지 않는다** (05-design §5). 한 프레임만 그려 두면
  /// 노드망은 그대로 보이고 움직임만 없다.
  ///
  /// 여기서 판단해야 MediaQuery 를 읽을 수 있다(initState 에서는 아직 없다).
  /// 위젯 테스트도 이 길로 멈춘다 — 끝나지 않는 티커가 있으면
  /// `pumpAndSettle` 이 영영 안 끝난다.
  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    final still = MediaQuery.disableAnimationsOf(context);
    if (still && _ticker.isActive) {
      _ticker.stop();
    } else if (!still && !_ticker.isActive) {
      _ticker.start();
    }
  }

  @override
  void dispose() {
    _ticker.dispose();
    _clock.dispose();
    super.dispose();
  }

  /// 최근접 이웃으로 고정 그래프를 만든다. 허브는 하나 더 잇는다
  static List<_Edge> _link(List<_Node> nodes, math.Random rnd) {
    final out = <_Edge>[];
    for (var i = 0; i < nodes.length; i++) {
      final d = <(double, int)>[];
      for (var j = 0; j < nodes.length; j++) {
        if (i == j) continue;
        final a = nodes[i], b = nodes[j];
        final dx = a.bx - b.bx, dy = a.by - b.by, dz = a.bz - b.bz;
        d.add((dx * dx + dy * dy + dz * dz, j));
      }
      d.sort((p, q) => p.$1.compareTo(q.$1));
      final k = nodes[i].hub ? 3 : 2;
      for (var m = 0; m < k; m++) {
        final j = d[m].$2;
        if (i < j) {
          out.add(
            _Edge(i, j, rnd.nextDouble(), .00012 + rnd.nextDouble() * .00022),
          );
        }
      }
    }
    return out;
  }

  @override
  Widget build(BuildContext context) {
    return RepaintBoundary(
      child: CustomPaint(
        painter: _NetworkPainter(
          nodes: _nodes,
          edges: _edges,
          clock: _clock,
          dim: widget.dim,
        ),
        size: Size.infinite,
      ),
    );
  }
}

class _NetworkPainter extends CustomPainter {
  _NetworkPainter({
    required this.nodes,
    required this.edges,
    required this.clock,
    required this.dim,
  }) : super(repaint: clock);

  final List<_Node> nodes;
  final List<_Edge> edges;
  final ValueNotifier<double> clock;
  final double dim;

  @override
  void paint(Canvas canvas, Size size) {
    final t = clock.value;
    final w = size.width, h = size.height;
    final press = dim.clamp(0.0, 1.0);

    canvas.drawRect(Offset.zero & size, Paint()..color = AppColors.bg);

    // 성운
    for (final n in _nebula) {
      final dx = math.sin(t * n.sp + n.ph) * .05;
      final dy = math.cos(t * n.sp * .8 + n.ph) * .04;
      final c = Offset((n.x + dx) * w, (n.y + dy) * h);
      final r = n.r * math.max(w, h) * .62;
      canvas.drawCircle(
        c,
        r,
        Paint()
          ..shader = ui.Gradient.radial(c, r, [
            n.color.withValues(alpha: n.a * (1 - press * .72)),
            n.color.withValues(alpha: 0),
          ]),
      );
    }

    // 투영 — 화면 크기 s 가 곧 깊이다
    const f = 1.35;
    final cx = w / 2, cy = h / 2;
    for (final nd in nodes) {
      final z = nd.bz + math.sin(t * nd.sp + nd.ph) * nd.amp;
      final s = f / (f + z + 1.25);
      nd.x = cx + nd.bx * w * .82 * s;
      nd.y = cy + nd.by * h * .58 * s;
      nd.s = s;
      nd.band = s < _bands[0].max ? 0 : (s < _bands[1].max ? 1 : 2);
    }

    for (var b = 0; b < _bands.length; b++) {
      final band = _bands[b];
      // 구간마다 레이어 하나. 원마다 MaskFilter 를 걸면 70번 흐려진다
      if (band.blur > 0) {
        canvas.saveLayer(
          Offset.zero & size,
          Paint()
            ..imageFilter = ui.ImageFilter.blur(
              sigmaX: band.blur,
              sigmaY: band.blur,
            ),
        );
      }

      _paintEdges(canvas, b, t, press);
      _paintNodes(canvas, b, press);

      if (band.blur > 0) canvas.restore();

      // 안개 — 먼 구간 위에 덮어 공기 원근을 만든다
      if (band.fog > 0) {
        canvas.drawRect(
          Offset.zero & size,
          Paint()..color = AppColors.bg.withValues(alpha: band.fog),
        );
      }
    }

    // 감광 — 인트로 동안 배경 전체를 누른다
    if (press > .002) {
      canvas.drawRect(
        Offset.zero & size,
        Paint()..color = const Color(0xFF04070E).withValues(alpha: press * .55),
      );
    }
  }

  void _paintEdges(Canvas canvas, int band, double t, double press) {
    final line = Paint()..strokeWidth = 1;
    final pulse = Paint();
    for (final e in edges) {
      final a = nodes[e.a], c = nodes[e.b];
      if (a.band != band && c.band != band) continue;
      final s = (a.s + c.s) / 2;
      final al = math.max(0, s - .55) * .5 * (1 - press * .78);
      if (al <= .004) continue;

      line.color = const Color(0xFF7DD3FC).withValues(alpha: al);
      canvas.drawLine(Offset(a.x, a.y), Offset(c.x, c.y), line);

      // 선을 지나는 펄스 — 고정 그래프라 늘 같은 길을 흐른다
      final u = (t * e.sp + e.ph) % 1;
      final pa = al * 3.4;
      if (pa > .02) {
        pulse.color = AppColors.accent.withValues(alpha: math.min(.85, pa));
        canvas.drawCircle(
          Offset(a.x + (c.x - a.x) * u, a.y + (c.y - a.y) * u),
          1.5 * s,
          pulse,
        );
      }
    }
  }

  void _paintNodes(Canvas canvas, int band, double press) {
    final dot = Paint();
    for (final nd in nodes) {
      if (nd.band != band) continue;
      final r = (nd.hub ? 2.6 : 1.5) * nd.s * 1.15;
      final al =
          math.min(1.0, math.max(.06, (nd.s - .5) * 1.5)) * (1 - press * .72);
      dot.color = nd.color.withValues(alpha: al);
      canvas.drawCircle(Offset(nd.x, nd.y), r, dot);
      if (nd.hub) {
        dot.color = nd.color.withValues(alpha: al * .16);
        canvas.drawCircle(Offset(nd.x, nd.y), r * 4.5, dot);
      }
    }
  }

  @override
  bool shouldRepaint(_NetworkPainter old) => old.dim != dim;
}

/// 로고 — 노드 다섯 개와 그 연결선이 이루는 형태가 곧 A 다
/// (05-design §0.0: 네트워크이면서 이니셜).
///
/// 런처 아이콘도 같은 그림이다 — 앱을 여는 자리와 들어온 자리가 같은 표를 쓴다.
class BrandMark extends StatelessWidget {
  const BrandMark({super.key, this.size = 46});

  final double size;

  @override
  Widget build(BuildContext context) => SizedBox(
    width: size,
    height: size,
    child: CustomPaint(painter: _MarkPainter()),
  );
}

class _MarkPainter extends CustomPainter {
  /// 46 기준 좌표를 비율로 옮긴 것 — 어느 크기로도 같은 그림이 나온다
  static const _apex = Offset(.500, .152);
  static const _left = Offset(.174, .783);
  static const _right = Offset(.826, .783);
  static const _barL = Offset(.317, .609);
  static const _barR = Offset(.683, .609);

  @override
  void paint(Canvas canvas, Size size) {
    Offset p(Offset u) => Offset(u.dx * size.width, u.dy * size.height);
    final k = size.width / 46;

    final line = Paint()
      ..color = const Color(0xFF7DD3FC).withValues(alpha: .5)
      ..strokeWidth = 1.4 * k
      ..strokeCap = StrokeCap.round;
    canvas.drawLine(p(_apex), p(_right), line);
    canvas.drawLine(p(_apex), p(_left), line);
    canvas.drawLine(p(_barL), p(_barR), line);

    void dot(Offset u, double r, Color c) =>
        canvas.drawCircle(p(u), r * k, Paint()..color = c);

    dot(_apex, 3.4, AppColors.accent);
    dot(_right, 3.0, AppColors.accentBlue);
    dot(_left, 3.0, AppColors.accentViolet);
    dot(_barL, 2.4, AppColors.accentText);
    dot(_barR, 2.4, AppColors.accentText);
  }

  @override
  bool shouldRepaint(_MarkPainter old) => false;
}
