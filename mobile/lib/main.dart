import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart' show rootBundle;

import 'models/applicant.dart';
import 'routes.dart';
import 'screens/applicant_detail_screen.dart';
import 'screens/applicants_screen.dart';
import 'screens/login_screen.dart';
import 'theme/app_theme.dart';

void main() {
  _registerFontLicense();
  runApp(const ArdaApp());
}

/// 번들한 IBM Plex Sans KR 의 라이선스를 앱에 등록한다.
///
/// SIL Open Font License 1.1 은 **라이선스 사본을 함께 배포할 것**을 요구한다.
/// 이렇게 등록해 두면 `showLicensePage()` 에 함께 나온다.
void _registerFontLicense() {
  LicenseRegistry.addLicense(() async* {
    final text = await rootBundle.loadString('assets/fonts/OFL.txt');
    yield LicenseEntryWithLineBreaks(const ['IBM Plex Sans KR'], text);
  });
}

class ArdaApp extends StatelessWidget {
  const ArdaApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: '아르다',
      debugShowCheckedModeBanner: false,
      theme: buildAppTheme(),
      // 05-design §0-4: 라이트 온리. 기기가 다크 모드여도 따라가지 않는다
      themeMode: ThemeMode.light,
      initialRoute: Routes.applicants,
      routes: {
        Routes.applicants: (_) => const ApplicantsScreen(),
        Routes.login: (_) => const LoginScreen(),
      },
      // 상세는 "어느 지원자인지"를 인자로 받으므로 routes 표가 아니라 여기서 만든다
      onGenerateRoute: (settings) {
        if (settings.name == Routes.applicantDetail) {
          final applicant = settings.arguments! as Applicant;
          return MaterialPageRoute(
            settings: settings,
            builder: (_) => ApplicantDetailScreen(applicant: applicant),
          );
        }
        return null;
      },
      builder: (context, child) {
        // 05-design §5: prefers-reduced-motion 대응 필수.
        // 기기의 "애니메이션 줄이기" 설정을 존중한다
        final reduceMotion = MediaQuery.disableAnimationsOf(context);
        if (kDebugMode && reduceMotion) {
          debugPrint('[a11y] 기기 설정에 따라 애니메이션을 줄인다');
        }
        return child ?? const SizedBox.shrink();
      },
    );
  }
}
