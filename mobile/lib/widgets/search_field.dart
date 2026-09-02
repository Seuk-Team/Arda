/// 검색 입력칸 — **공고별 지원자**가 쓴다.
///
/// 웹 `PostingApplicants.tsx` 의 "검색어 입력" 을 옮긴 것이다. 한 공고에 22명이
/// 쌓이면 단계 탭만으로는 못 찾는다.
///
/// 지원자 탭(`applicants_search_screen.dart`)에도 같은 모양의 검색칸이 있지만
/// 그 화면 안의 `_SearchField` 로 따로 있다. **합치지 않았다** — 도는 코드를
/// 건드리지 않기로 했고(CLAUDE.md 리팩터링 금지), 지금 필요한 건 없던 자리에
/// 검색을 더하는 것뿐이다. 둘을 합치는 것은 별도 작업이다.
///
/// [hintText] 는 자리마다 다르다 — 전 공고는 "이름 또는 공고", 여기는 이름뿐이다.
library;

import 'package:flutter/material.dart';

import '../theme/tokens.dart';

class SearchField extends StatelessWidget {
  const SearchField({
    super.key,
    required this.controller,
    required this.hintText,
    required this.onChanged,
    required this.onClear,
  });

  final TextEditingController controller;

  /// 웹 문구를 그대로 쓴다
  final String hintText;

  final ValueChanged<String> onChanged;
  final VoidCallback onClear;

  static const _outline = OutlineInputBorder(
    borderRadius: AppShape.ctl,
    borderSide: BorderSide(color: AppColors.border, width: AppShape.borderW),
  );

  @override
  Widget build(BuildContext context) {
    return TextField(
      controller: controller,
      onChanged: onChanged,
      style: const TextStyle(
        fontFamily: AppType.fontFamily,
        fontSize: AppType.body,
        color: AppColors.text,
      ),
      decoration: InputDecoration(
        isDense: true,
        filled: true,
        fillColor: AppColors.bgSunken,
        hintText: hintText,
        hintStyle: const TextStyle(
          fontFamily: AppType.fontFamily,
          fontSize: AppType.body,
          color: AppColors.textSub,
        ),
        prefixIcon: const Icon(
          Icons.search,
          size: 20,
          color: AppColors.textSub,
        ),
        // 지울 것이 있을 때만 X 를 낸다 — 빈 칸에 X 가 있으면 뭘 지우는지 모른다
        suffixIcon: controller.text.isEmpty
            ? null
            : IconButton(
                icon: const Icon(Icons.close, size: 20),
                color: AppColors.textSub,
                tooltip: '검색어 지우기',
                onPressed: onClear,
              ),
        contentPadding: const EdgeInsets.symmetric(
          horizontal: AppSpace.s3,
          vertical: AppSpace.s3,
        ),
        border: _outline,
        enabledBorder: _outline,
        focusedBorder: const OutlineInputBorder(
          borderRadius: AppShape.ctl,
          borderSide: BorderSide(
            color: AppColors.leaf,
            width: AppShape.borderW,
          ),
        ),
      ),
    );
  }
}
