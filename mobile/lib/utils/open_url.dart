/// 바깥으로 나가는 주소 열기 — 지금은 첨부 파일뿐이다 (큐 8 4단계, 2026-09-03).
///
/// 함수 하나를 통로로 둔다: 테스트가 진짜 브라우저를 띄우지 않게 가짜를 끼울
/// 자리가 필요하고, 나중에 앱 안 뷰어로 바꾸더라도 부르는 쪽은 그대로여야 한다.
library;

import 'package:url_launcher/url_launcher.dart';

/// 주소를 열어 성공 여부를 돌려준다.
typedef UrlOpener = Future<bool> Function(String url);

/// 기본 구현 — 기기의 브라우저(또는 그 형식을 여는 앱)로 넘긴다.
///
/// `externalApplication` 인 이유: 인앱 웹뷰로 열면 PDF 가 그냥 다운로드되거나
/// 빈 화면이 되는 기기가 있다. 브라우저에 맡기면 형식별 처리가 알아서 된다.
Future<bool> openInBrowser(String url) =>
    launchUrl(Uri.parse(url), mode: LaunchMode.externalApplication);
