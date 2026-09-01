/// 상세 화면의 "지원 정보" 패널.
///
/// 이력:
/// - 목업(`mockup-mobile.html` `.dlist`)은 라벨을 왼쪽 88px 열에 두는 2단 그리드
/// - 시안(2026-08-28)이 **항목마다 카드 한 장**으로 바꿨다. 그때는 필드가
///   학력·경력·지원일 셋뿐이라 괜찮았다
/// - **앱 UI 초안(2026-09-01)이 다시 한 카드 안 목록으로 되돌렸다.** 배포판 웹에
///   맞춰 연락처·이메일·기술·평점이 늘면서 카드 여섯 장이 벽이 됐기 때문이다.
///   기준 우선순위는 목업 < 시안 < 초안 (docs/01_role/app.md §3)
library;

import 'package:flutter/material.dart';

import '../theme/tokens.dart';
import 'detail_blocks.dart';

class DetailFieldList extends StatelessWidget {
  const DetailFieldList({super.key, required this.fields});

  /// 라벨 → 값. 순서가 화면 순서다.
  final Map<String, String> fields;

  @override
  Widget build(BuildContext context) {
    return DetailPanel(
      title: '지원 정보',
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        mainAxisSize: MainAxisSize.min,
        children: [
          for (final entry in fields.entries)
            _FieldRow(label: entry.key, value: entry.value),
        ],
      ),
    );
  }
}

/// 라벨 왼쪽 · 값 오른쪽. 라벨 열 폭을 고정해 값의 시작선이 맞는다 —
/// 훑을 때 값만 세로로 읽히게 하려는 것이다.
class _FieldRow extends StatelessWidget {
  const _FieldRow({required this.label, required this.value});

  final String label;
  final String value;

  /// 가장 긴 라벨("연락처")이 들어가는 폭
  static const _labelWidth = 60.0;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: AppSpace.s1),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: _labelWidth,
            child: Text(
              label,
              style: const TextStyle(
                fontFamily: AppType.fontFamily,
                fontSize: AppType.sm,
                color: AppColors.textSub,
              ),
            ),
          ),
          const SizedBox(width: AppSpace.s3),
          Expanded(
            child: Text(
              value,
              style: const TextStyle(
                fontFamily: AppType.fontFamily,
                fontSize: AppType.sm,
                height: 1.5,
                color: AppColors.text,
              ),
            ),
          ),
        ],
      ),
    );
  }
}
