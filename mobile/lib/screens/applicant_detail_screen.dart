import 'package:flutter/material.dart';

/// 지원자 상세.
///
/// **뼈대 단계다.** 지원 정보·단계 이력 타임라인·평가 목록·단계 변경 버튼은
/// 다음 큐에서 만든다 (role/app.md §3).
///
/// 마지막 화면이라 앞으로 가는 버튼이 없다 — AppBar 의 뒤로가기로 돌아온다.
class ApplicantDetailScreen extends StatelessWidget {
  const ApplicantDetailScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('지원자 상세')),
      body: const SizedBox.shrink(),
    );
  }
}
