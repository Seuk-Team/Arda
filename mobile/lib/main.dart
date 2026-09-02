import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart' show rootBundle;

import 'auth/auth_service.dart';
import 'auth/current_user.dart';
import 'models/applicant.dart';
import 'models/job_posting.dart';
import 'routes.dart';
import 'screens/applicant_detail_screen.dart';
import 'screens/applicants_screen.dart';
import 'screens/evaluation_queue_screen.dart';
import 'screens/evaluations_screen.dart';
import 'screens/posting_new_screen.dart';
import 'screens/settings_screen.dart';
import 'screens/home_shell.dart';
import 'screens/stage_history_screen.dart';
import 'screens/launch_screen.dart';
import 'screens/login_screen.dart';
import 'theme/app_theme.dart';

void main() {
  _registerFontLicense();
  runApp(ArdaApp());
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
  ArdaApp({super.key, this.auth, this.initialRoute});

  /// 테스트가 가짜 인증을 넣는 자리. 평소에는 null 이라 진짜가 만들어진다
  final AuthService? auth;

  /// 테스트가 시작 화면(토큰 확인)을 건너뛰는 자리
  final String? initialRoute;

  /// 로그인한 사람. 시작 화면·로그인 화면이 채우고 더보기·설정이 읽는다 (큐 7)
  final _user = CurrentUser();

  @override
  Widget build(BuildContext context) {
    return CurrentUserScope(notifier: _user, auth: auth, child: _app());
  }

  Widget _app() {
    return MaterialApp(
      title: '아르다',
      debugShowCheckedModeBanner: false,
      theme: buildAppTheme(),
      // 05-design §0-4: 라이트 온리. 기기가 다크 모드여도 따라가지 않는다
      themeMode: ThemeMode.light,
      // 첫 화면은 시작 화면이다 — 저장된 토큰이 아직 쓸 수 있으면 홈으로,
      // 아니면 로그인으로 보낸다. 토큰이 12시간짜리라 켤 때마다 로그인시키면
      // 그 12시간이 의미가 없다 (큐 7).
      //
      // 개발 중 로그인을 건너뛰려면: flutter run --route=/
      initialRoute: initialRoute ?? Routes.launch,
      routes: {
        Routes.home: (_) => const HomeShell(),
        Routes.launch: (_) => LaunchScreen(auth: auth),
        Routes.login: (_) => LoginScreen(auth: auth),
        Routes.evaluationQueue: (_) => const EvaluationQueueScreen(),
        Routes.settings: (_) => const SettingsScreen(),
        Routes.postingNew: (_) => const PostingNewScreen(),
      },
      // 지원자·상세는 "어느 공고/누구"를 인자로 받으므로 routes 표가 아니라 여기서 만든다
      onGenerateRoute: (settings) {
        if (settings.name == Routes.applicants) {
          final posting = settings.arguments! as JobPosting;
          return MaterialPageRoute(
            settings: settings,
            builder: (_) => ApplicantsScreen(posting: posting),
          );
        }
        if (settings.name == Routes.stageHistory) {
          final args = settings.arguments! as (Applicant, String);
          return MaterialPageRoute(
            settings: settings,
            builder: (_) =>
                StageHistoryScreen(applicant: args.$1, postingTitle: args.$2),
          );
        }
        if (settings.name == Routes.evaluations) {
          final applicant = settings.arguments! as Applicant;
          return MaterialPageRoute(
            settings: settings,
            builder: (_) => EvaluationsScreen(applicant: applicant),
          );
        }
        if (settings.name == Routes.applicantDetail) {
          final args = settings.arguments! as (Applicant, String);
          return MaterialPageRoute(
            settings: settings,
            builder: (_) => ApplicantDetailScreen(
              applicant: args.$1,
              postingTitle: args.$2,
            ),
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
