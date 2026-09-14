import 'dart:async';

import 'package:firebase_app_check/firebase_app_check.dart';
import 'package:flutter/foundation.dart';
import 'package:firebase_auth/firebase_auth.dart';
import 'package:firebase_core/firebase_core.dart';
import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'firebase_options.dart';
import 'src/api_repository.dart';
import 'src/app/app_router.dart';
import 'src/app/routes.dart';
import 'src/app/session_notifier.dart';
import 'src/app_check.dart';
import 'src/auth.dart';
import 'src/connection_config.dart';
import 'src/email_link_browser.dart';
import 'src/magic_link.dart';
import 'src/models.dart';
import 'src/production_startup.dart';
import 'src/theme/app_theme.dart';
import 'src/workspace.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final emailLinkBrowser = createEmailLinkBrowser();
  SessionAccess? session;
  SpecimenRepository? repository;
  String? setupMessage;
  const apiUrl = String.fromEnvironment('SPECIMEN_API_BASE_URL');
  const localSynthetic = bool.fromEnvironment('SPECIMEN_LOCAL_SYNTHETIC');
  const config = ConnectionConfig(
    apiUrl: apiUrl,
    siteKey: String.fromEnvironment('SPECIMEN_RECAPTCHA_SITE_KEY'),
    synthetic: localSynthetic,
    authEmulatorHost: String.fromEnvironment('SPECIMEN_AUTH_EMULATOR_HOST'),
  );
  try {
    if (localSynthetic) {
      final uri = config.validate(web: kIsWeb);
      if (!['localhost', '127.0.0.1', '::1', '10.0.2.2'].contains(uri.host)) {
        throw StateError('Synthetic access is restricted to a local API');
      }
      session = LocalFixtureSession(baseUrl: uri);
      repository = ApiSpecimenRepository(
        baseUrl: uri,
        token: session.token,
        expectedMode: 'synthetic',
      );
    } else {
      final options = DefaultFirebaseOptions.currentPlatform;
      final startup = await initializeProduction(
        firebaseConfigured: !options.appId.endsWith(':ci-placeholder'),
        config: config,
        web: kIsWeb,
        initializeSession: () async {
          await Firebase.initializeApp(options: options);
          return FirebaseSession(FirebaseAuth.instance);
        },
        activateAppCheck: () => activateProductionAppCheck(config, web: kIsWeb),
        createRepository: (uri, session) => ApiSpecimenRepository(
          baseUrl: uri,
          expectedMode: 'production',
          expectedUserId: () => session.userId,
          token: session.token,
          appCheckToken: () => FirebaseAppCheck.instance.getToken(),
        ),
      );
      session = startup.session;
      repository = startup.repository;
      setupMessage = startup.setupMessage;
    }
  } on FormatException catch (error) {
    setupMessage = error.message;
  } catch (_) {
    setupMessage = localSynthetic
        ? 'Test setup could not be completed. Check the demo API address.'
        : 'Setup could not be completed. Ask your administrator to check the sign-in and API configuration.';
  }
  runApp(
    SpecimenDigitizationApp(
      session: session,
      repository: repository,
      setupMessage: setupMessage,
      synthetic: localSynthetic,
      emailLinkBrowser: emailLinkBrowser,
    ),
  );
}

/// The application: one theme, one router, one workspace controller.
class SpecimenDigitizationApp extends StatefulWidget {
  const SpecimenDigitizationApp({
    super.key,
    this.session,
    this.repository,
    this.setupMessage,
    this.synthetic = false,
    this.emailLinkBrowser,
    this.initialLocation = AppRoutes.setup,
  });

  /// A browser for the incoming email sign-in link, on web.
  final EmailLinkBrowser? emailLinkBrowser;

  /// The session, or null in a build with no sign-in configured.
  final SessionAccess? session;

  /// The collection API, or null before one is configured.
  final SpecimenRepository? repository;

  /// What the build already knows is missing.
  final String? setupMessage;

  /// True for the local fixture build.
  final bool synthetic;

  /// Where the window starts. A test uses this to open a deep link.
  final String initialLocation;

  @override
  State<SpecimenDigitizationApp> createState() =>
      _SpecimenDigitizationAppState();
}

class _SpecimenDigitizationAppState extends State<SpecimenDigitizationApp> {
  late final AppSessionNotifier _sessionNotifier;
  WorkspaceController? _workspace;
  MagicLinkController? _magicLink;
  late final GoRouter _router;

  @override
  void initState() {
    super.initState();
    _sessionNotifier = AppSessionNotifier(session: widget.session)
      ..addListener(_sessionChanged);
    final SessionAccess? session = widget.session;
    if (session is EmailLinkAccess) {
      _magicLink = MagicLinkController(
        access: session as EmailLinkAccess,
        browser: widget.emailLinkBrowser ?? createEmailLinkBrowser(),
      );
      unawaited(_magicLink!.initialize());
    }
    final SpecimenRepository? repository = widget.repository;
    if (session != null && repository != null) {
      _workspace = WorkspaceController(
        repository: repository,
        session: session,
      );
    }
    _router = buildAppRouter(
      sessionNotifier: _sessionNotifier,
      controller: _workspace,
      magicLink: _magicLink,
      setupMessage: widget.setupMessage,
      synthetic: widget.synthetic,
      initialLocation: widget.initialLocation,
    );
    _sessionChanged();
  }

  /// Starts collection loading the moment the session is signed in and
  /// verified, and never before, so an unverified account sends no token.
  void _sessionChanged() {
    if (_sessionNotifier.signedIn && _sessionNotifier.verified) {
      _workspace?.start();
    } else {
      _workspace?.resetSession();
    }
  }

  @override
  void dispose() {
    _sessionNotifier
      ..removeListener(_sessionChanged)
      ..dispose();
    _router.dispose();
    _magicLink?.dispose();
    _workspace?.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final WorkspaceController? workspace = _workspace;
    final Widget app = MaterialApp.router(
      title: 'Specimen Digitization',
      debugShowCheckedModeBanner: false,
      theme: _lightTheme,
      darkTheme: _darkTheme,
      themeMode: ThemeMode.system,
      routerConfig: _router,
    );
    return workspace == null
        ? app
        : WorkspaceScope(controller: workspace, child: app);
  }
}

/// The page transitions the motion document specifies (section 6.1).
///
/// The mobile entries restate Flutter's own defaults so a future SDK change is
/// a visible diff; the desktop and web entries move off the zoom transition
/// onto the Material 3 forward transition.
const PageTransitionsTheme specimenPageTransitions = PageTransitionsTheme(
  builders: <TargetPlatform, PageTransitionsBuilder>{
    TargetPlatform.android: PredictiveBackPageTransitionsBuilder(),
    TargetPlatform.iOS: CupertinoPageTransitionsBuilder(),
    TargetPlatform.macOS: CupertinoPageTransitionsBuilder(),
    TargetPlatform.windows: FadeForwardsPageTransitionsBuilder(),
    TargetPlatform.linux: FadeForwardsPageTransitionsBuilder(),
    TargetPlatform.fuchsia: FadeForwardsPageTransitionsBuilder(),
  },
);

final ThemeData _lightTheme = AppTheme.light().copyWith(
  pageTransitionsTheme: specimenPageTransitions,
);

final ThemeData _darkTheme = AppTheme.dark().copyWith(
  pageTransitionsTheme: specimenPageTransitions,
);
