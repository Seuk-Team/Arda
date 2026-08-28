/// 상세 화면의 한 구획 — 목업 `.dsec` 를 옮긴 것.
///
/// 제목(h2) + 내용, 아래에 옅은 경계선. 지원 정보·첨부 파일·메모가 모두 이 모양이다.
library;

import 'package:flutter/material.dart';

import '../theme/tokens.dart';

class DetailSection extends StatelessWidget {
  const DetailSection({super.key, required this.title, required this.child});

  final String title;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(
        horizontal: AppSpace.s5,
        vertical: AppSpace.s4,
      ),
      decoration: const BoxDecoration(
        // 구획 사이는 --border 보다 옅은 --border-soft 를 쓴다 (목업 .dsec)
        border: Border(
          bottom: BorderSide(
            color: AppColors.borderSoft,
            width: AppShape.borderW,
          ),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(
            title,
            style: const TextStyle(
              fontFamily: AppType.fontFamily,
              fontSize: AppType.h2,
              fontWeight: FontWeight.w700,
              color: AppColors.text,
              // §2: h2 에는 텍스트 그림자를 항상
              shadows: AppTextShadow.heading,
            ),
          ),
          const SizedBox(height: AppSpace.s3),
          child,
        ],
      ),
    );
  }
}

/// 라벨·값 목록 — 목업 `.dlist` (`<dl>` 의 2단 그리드).
///
/// 라벨 열은 88px 고정이라 값의 왼쪽 끝이 항상 같은 자리에서 시작한다.
class DetailFieldList extends StatelessWidget {
  const DetailFieldList({super.key, required this.fields});

  /// 라벨 → 값. 순서가 화면 순서다.
  final Map<String, String> fields;

  static const _labelWidth = 88.0;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        for (final (i, entry) in fields.entries.indexed) ...[
          if (i > 0) const SizedBox(height: AppSpace.s2),
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              SizedBox(
                width: _labelWidth,
                child: Text(
                  entry.key,
                  // 라벨은 한 줄 고정 (§2)
                  softWrap: false,
                  style: const TextStyle(
                    fontFamily: AppType.fontFamily,
                    fontSize: AppType.sm,
                    color: AppColors.textSub,
                  ),
                ),
              ),
              const SizedBox(width: AppSpace.s4),
              // 값은 길면 줄바꿈한다 — 목업 dd 의 overflow-wrap:break-word
              Expanded(
                child: Text(
                  entry.value,
                  style: const TextStyle(
                    fontFamily: AppType.fontFamily,
                    fontSize: AppType.sm,
                    color: AppColors.text,
                    fontFeatures: AppType.tabularNums,
                  ),
                ),
              ),
            ],
          ),
        ],
      ],
    );
  }
}
