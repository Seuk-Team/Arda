// 위젯 테스트에서 연출을 끈다 (2026-09-08).
//
// 로그인 화면에는 **끝나지 않는 것 둘**이 있다: 배경 노드망(계속 흐른다)과
// 인트로(3.6초). 둘 다 프레임을 계속 걸어서 `pumpAndSettle` 이 영영 안 끝난다.
//
// 화면 코드가 이미 05-design §5 대로 "동작 줄이기" 를 지키고 있으므로
// (`MediaQuery.disableAnimationsOf`), 테스트는 그 스위치를 켜기만 하면 된다 —
// 테스트용 우회로를 코드에 새로 뚫지 않는다.
//
// `MaterialApp` 이 자기 MediaQuery 를 [MediaQuery.fromView] 로 새로 만들기
// 때문에 **밖에서 MediaQuery 로 감싸는 것으로는 안 된다.** 접근성 값을 플랫폼
// 쪽에 심어야 그 안까지 닿는다.

import 'package:flutter_test/flutter_test.dart';

/// 이 테스트 동안 모든 연출을 끈다. 끝나면 원래대로 돌려놓는다
void disableMotion(WidgetTester tester) {
  tester.platformDispatcher.accessibilityFeaturesTestValue =
      const FakeAccessibilityFeatures(disableAnimations: true);
  addTearDown(tester.platformDispatcher.clearAccessibilityFeaturesTestValue);
}
