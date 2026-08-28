/// 상세 화면의 항목 카드 — 시안(2026-08-28).
///
/// 라벨을 값 위에 올리고 각 항목을 테두리 카드로 감싼다.
/// 목업(`mockup-mobile.html` `.dlist`)은 라벨을 왼쪽 88px 열에 두는 2단 그리드였지만,
/// 시안이 카드형으로 바꿨다. 라벨이 곧 항목 이름이라 "지원 정보" 같은 구획 제목은
/// 두지 않는다 — 시안 화면에도 제목이 없다.
///
/// 카드 여백·간격은 시안이 공고 리스트에 준 값(카드 여백 16dp · 카드 사이 12dp)을
/// 따랐다. 항목 카드 자체의 수치는 시안에 없다.
library;

import 'package:flutter/material.dart';

import '../theme/tokens.dart';

class DetailFieldList extends StatelessWidget {
  const DetailFieldList({super.key, required this.fields});

  /// 라벨 → 값. 순서가 화면 순서다.
  final Map<String, String> fields;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: [
        for (final (i, entry) in fields.entries.indexed) ...[
          if (i > 0) const SizedBox(height: AppSpace.s3),
          _FieldCard(label: entry.key, value: entry.value),
        ],
      ],
    );
  }
}

class _FieldCard extends StatelessWidget {
  const _FieldCard({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(AppSpace.s4),
      decoration: const BoxDecoration(
        color: AppColors.bgElev,
        borderRadius: AppShape.card,
        border: Border.fromBorderSide(
          BorderSide(color: AppColors.border, width: AppShape.borderW),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(
            label,
            // 라벨은 한 줄 고정 (§2)
            softWrap: false,
            style: const TextStyle(
              fontFamily: AppType.fontFamily,
              fontSize: AppType.caption,
              color: AppColors.textSub,
            ),
          ),
          const SizedBox(height: AppSpace.s1),
          // 값은 길면 줄바꿈한다 — 상세는 다 읽는 화면이라 자르지 않는다
          Text(
            value,
            style: const TextStyle(
              fontFamily: AppType.fontFamily,
              fontSize: AppType.body,
              color: AppColors.text,
              fontFeatures: AppType.tabularNums,
            ),
          ),
        ],
      ),
    );
  }
}
