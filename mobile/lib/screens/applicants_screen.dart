import 'package:flutter/material.dart';

import '../routes.dart';

/// 공고 하나의 지원자 리스트.
///
/// **뼈대 단계다.** 단계 탭 필터·퍼널 바·리스트는 다음 큐에서 만든다.
/// 모바일은 칸반을 쓰지 않는다 (05-design §9).
class ApplicantsScreen extends StatelessWidget {
  const ApplicantsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('지원자')),
      body: Center(
        child: FilledButton(
          onPressed: () => Navigator.pushNamed(context, Routes.applicantDetail),
          child: const Text('지원자 상세 보기'),
        ),
      ),
    );
  }
}
