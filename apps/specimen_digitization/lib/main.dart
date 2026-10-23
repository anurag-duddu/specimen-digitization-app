import 'dart:async';

import 'package:firebase_app_check/firebase_app_check.dart';
import 'package:flutter/foundation.dart';
import 'package:firebase_auth/firebase_auth.dart';
import 'package:firebase_core/firebase_core.dart';
import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:specimen_ui/specimen_ui.dart';

import 'firebase_options.dart';
import 'src/api_repository.dart';
import 'src/app/app_router.dart';
import 'src/app/routes.dart';
import 'src/app/session_notifier.dart';
import 'src/app_check.dart';
import 'src/app_reload.dart';
import 'src/auth.dart';
import 'src/connection_config.dart';
import 'src/email_link_browser.dart';
import 'src/email_link_source.dart';
import 'src/email_link_source_factory.dart';
import 'src/magic_link.dart';
import 'src/models.dart';
import 'src/production_startup.dart';
import 'src/theme/app_theme.dart';
import 'src/theme/motion_preference.dart';
import 'src/workspace.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final emailLinkBrowser = createEmailLinkBrowser();
  final emailLinkSource = createNativeEmailLinkSource();
  SessionAccess? session;
  SpecimenRepository? repository;
  String? setupMessage;
  const apiUrl = String.fromEnvironment('SPECIMEN_API_BASE_URL');
  const localSynthetic = bool.fromEnvironment('SPECIMEN_LOCAL_SYNTHETIC');
  const androidAppCheckDebug = bool.fromEnvironment(
    'SPECIMEN_ANDROID_APP_CHECK_DEBUG',
  );
  const appleAppCheckDebug = bool.fromEnvironment(
    'SPECIMEN_APPLE_APP_CHECK_DEBUG',
  );
  const appleProfileAppCheckDebug = bool.fromEnvironment(
    'SPECIMEN_APPLE_PROFILE_APP_CHECK_DEBUG',
  );
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
        activateAppCheck: () => activateProductionAppCheck(
          config,
          web: kIsWeb,
          debugBuild: kDebugMode,
          profileBuild: kProfileMode,
          androidDebugRequested: androidAppCheckDebug,
          appleDebugRequested: appleAppCheckDebug,
          appleProfileDebugRequested: appleProfileAppCheckDebug,
        ),
        createRepository: (uri, session) => ApiSpecimenRepository(
          baseUrl: uri,
          expectedMode: 'production',
          expectedUserId: () => session.userId,
          token: session.token,
          freshToken: session is FirebaseSession ? session.freshToken : null,
          appCheckToken: () => FirebaseAppCheck.instance.getToken(),
          freshAppCheckToken: () => FirebaseAppCheck.instance.getToken(true),
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
      emailLinkSource: emailLinkSource,
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
    this.emailLinkStorage,
    this.appReload,
    this.emailLinkSource,
    this.initialLocation = AppRoutes.setup,
    this.motionPreferences,
    this.navigatorObservers = const <NavigatorObserver>[],
  });

  /// A browser for the incoming email sign-in link, on web.
  final EmailLinkBrowser? emailLinkBrowser;

  /// Optional test store; production keeps its existing preferences store.
  final EmailLinkStorage? emailLinkStorage;

  /// Web host reload, replaceable by a recording implementation in tests.
  final AppReload? appReload;

  /// A source created before asynchronous startup can buffer incoming links.
  /// The application owns its lifetime. No native transport is selected here.
  final EmailLinkSource? emailLinkSource;

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

  /// Where the stored "Reduce motion" setting lives. A test passes an
  /// in-memory store so no test reaches the platform preference store
  /// (motion and microinteractions, 6.2b).
  final MotionPreferenceStore? motionPreferences;

  /// Observers installed on the router's navigator. Empty in the app; a test
  /// puts `TransitionDurationObserver` here to pump past a route transition
  /// without naming its duration.
  final List<NavigatorObserver> navigatorObservers;

  @override
  State<SpecimenDigitizationApp> createState() =>
      _SpecimenDigitizationAppState();
}

class _SpecimenDigitizationAppState extends State<SpecimenDigitizationApp> {
  late final AppSessionNotifier _sessionNotifier;
  WorkspaceController? _workspace;
  MagicLinkController? _magicLink;
  late final EmailLinkSource? _emailLinkSource;
  late final GoRouter _router;
  late final MotionPreferenceController _motion;
  late final AppReload? _appReload;
  late bool _wasSignedIn;
  late String? _lastSessionUserId;
  String? _handoffUserId;
  String? _handoffLocation;
  int? _handoffGeneration;
  bool _automaticReloadUsed = false;
  bool _reloading = false;
  int _recoveryEpoch = 0;
  Future<void> _emailSessionCleanup = Future<void>.value();

  @override
  void initState() {
    super.initState();
    _emailLinkSource = widget.emailLinkSource;
    _appReload = widget.appReload ?? createAppReload();
    _wasSignedIn = widget.session?.signedIn ?? false;
    _lastSessionUserId = widget.session?.userId;
    _motion = MotionPreferenceController(
      store: widget.motionPreferences ?? const SharedMotionPreferenceStore(),
    );
    unawaited(_motion.load());
    _sessionNotifier = AppSessionNotifier(session: widget.session)
      ..addListener(_sessionChanged);
    final SessionAccess? session = widget.session;
    if (session is EmailLinkAccess) {
      _magicLink = MagicLinkController(
        access: session as EmailLinkAccess,
        browser: widget.emailLinkBrowser ?? createEmailLinkBrowser(),
        linkSource: _emailLinkSource,
        storage: widget.emailLinkStorage,
      )..addListener(_reconcileEmailSession);
      unawaited(_magicLink!.initialize());
    }
    final SpecimenRepository? repository = widget.repository;
    if (session != null && repository != null) {
      _workspace = WorkspaceController(
        repository: repository,
        session: session,
        reloadApp: _appReload == null
            ? null
            : () async {
                try {
                  await _reloadForAppCheck();
                } catch (_) {
                  // The denial banner remains and already directs the user to
                  // reload. Setup also offers an explicit browser fallback message.
                }
              },
      )..addListener(_workspaceChanged);
    }
    _router = buildAppRouter(
      sessionNotifier: _sessionNotifier,
      controller: _workspace,
      magicLink: _magicLink,
      reloadApp: _appReload == null ? null : _reloadForAppCheck,
      setupMessage: widget.setupMessage,
      synthetic: widget.synthetic,
      initialLocation: widget.initialLocation,
      observers: widget.navigatorObservers,
    );
    _sessionChanged();
  }

  /// Starts collection loading the moment the session is signed in and
  /// verified, and never before, so an unverified account sends no token.
  void _sessionChanged() {
    final session = _sessionNotifier.session;
    final signedIn = _sessionNotifier.signedIn;
    final verified = _sessionNotifier.verified;
    final link = _magicLink;
    if (_wasSignedIn && (!signedIn || _lastSessionUserId != session?.userId)) {
      // An actual established-session transition ends the old request's
      // recovery eligibility. Initial/duplicate signed-out events do not.
      link?.invalidateSessionHandoff();
    }
    if (!signedIn || !verified || _lastSessionUserId != session?.userId) {
      _disarmHandoff();
      _recoveryEpoch++;
    }
    // Only this page's successful request can arm recovery. A restored email,
    // a local incoming link and a Google-only sign-in cannot arm it.
    if (_appReload != null &&
        !_automaticReloadUsed &&
        !_wasSignedIn &&
        signedIn &&
        verified &&
        session != null &&
        link?.emailSentInThisPage != null &&
        link!.sent &&
        !link.handlingLink &&
        link.emailSentInThisPage == normalizedStaffEmail(session.displayName)) {
      _handoffUserId = session.userId;
      _handoffLocation = _reloadLocation;
      _handoffGeneration = link.handoffGeneration;
    }
    _wasSignedIn = signedIn;
    _lastSessionUserId = session?.userId;
    _reconcileEmailSession();
    if (signedIn && verified) {
      _workspace?.start();
    } else {
      _workspace?.resetSession();
    }
  }

  String get _reloadLocation => appReloadLocation(
    _sessionNotifier.pendingLocation ??
        _router.routeInformationProvider.value.uri.toString(),
  );

  void _disarmHandoff() {
    _handoffUserId = null;
    _handoffLocation = null;
    _handoffGeneration = null;
  }

  void _workspaceChanged() {
    final workspace = _workspace;
    if (_handoffUserId == null ||
        workspace == null ||
        !workspace.scopesLoaded ||
        workspace.loading) {
      return;
    }
    final shouldReload =
        !workspace.scopesVerified &&
        _handoffGeneration == _magicLink?.handoffGeneration &&
        _handoffUserId == _sessionNotifier.session?.userId &&
        workspace.error?.appVerificationUnavailable == true;
    final location = _handoffLocation;
    _disarmHandoff();
    if (!shouldReload) return;
    // Consume synchronously before any await or repeated failure notification.
    // A reload starts authenticated and has no send made by its new controller.
    _automaticReloadUsed = true;
    unawaited(
      _reloadForAppCheck(location: location).catchError((Object _) {
        // Keep the ordinary Reload app action if browser reload is unavailable.
      }),
    );
  }

  Future<void> _reloadForAppCheck({String? location}) async {
    if (_reloading || _appReload == null) return;
    final session = _sessionNotifier.session;
    if (session == null ||
        !_sessionNotifier.signedIn ||
        !_sessionNotifier.verified) {
      return;
    }
    final userId = session.userId;
    final epoch = _recoveryEpoch;
    final handoffGeneration = _magicLink?.handoffGeneration;
    final destination = location ?? _reloadLocation;
    _reloading = true;
    try {
      // Reconciliation serializes its clear behind any previous local write.
      await _emailSessionCleanup;
      if (!mounted ||
          epoch != _recoveryEpoch ||
          handoffGeneration != _magicLink?.handoffGeneration ||
          !_sessionNotifier.signedIn ||
          !_sessionNotifier.verified ||
          session.userId != userId ||
          _magicLink?.handlingLink == true ||
          _workspace?.scopesVerified == true ||
          _workspace?.loading == true ||
          _workspace?.error?.appVerificationUnavailable != true) {
        return;
      }
      await _appReload.reload(appReloadLocation(destination));
    } finally {
      _reloading = false;
    }
  }

  void _reconcileEmailSession() {
    final session = _sessionNotifier.session;
    if (session == null ||
        session is! VerifiedEmailAccess ||
        !_sessionNotifier.signedIn ||
        !_sessionNotifier.verified) {
      return;
    }
    final controller = _magicLink;
    if (controller != null &&
        controller.initialized &&
        normalizedStaffEmail(session.displayName) == controller.email &&
        !controller.handlingLink) {
      _emailSessionCleanup = controller.reconcileVerifiedSession(
        session.displayName,
      );
    }
    if (controller?.handlingLink == true) {
      _disarmHandoff();
      _recoveryEpoch++;
    }
  }

  @override
  void dispose() {
    _sessionNotifier
      ..removeListener(_sessionChanged)
      ..dispose();
    _router.dispose();
    _motion.dispose();
    _magicLink
      ?..removeListener(_reconcileEmailSession)
      ..dispose();
    unawaited(_emailLinkSource?.close());
    _recoveryEpoch++;
    _workspace
      ?..removeListener(_workspaceChanged)
      ..dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final WorkspaceController? workspace = _workspace;
    final Widget app = MaterialApp.router(
      title: 'Specimen Digitization',
      debugShowCheckedModeBanner: false,
      theme: AppTheme.light(),
      darkTheme: AppTheme.dark(),
      themeMode: ThemeMode.system,
      routerConfig: _router,
      // `UiTheme` and the density probe sit here rather than above
      // `MaterialApp`, because this is the highest point in the tree where
      // the resolved brightness is known: `themeMode` follows the platform,
      // and a scope above the app would have to guess. Everything a reviewer
      // can see, including every overlay and route, is below this builder,
      // and so is the product's ambient text style: `UiTheme` publishes it
      // with its tokens now, so the application no longer wraps the router in
      // a `DefaultTextStyle` of its own (11 section 5).
      builder: (BuildContext context, Widget? child) =>
          MediaQuery.withClampedTextScaling(
            // The one place the text scale is clamped (11 section 2.1). The
            // control contract promises 200 percent and promises nothing
            // above it, and nothing below 85 percent is worth reading, so the
            // root says so once and no control reads or clamps the scaler
            // itself. On the web the browser's own preference never reaches
            // Flutter, so the scale here is 1.0 until the reviewer's stored
            // setting becomes a product feature.
            minScaleFactor: 0.85,
            maxScaleFactor: 2,
            child: Density(
              child: UiTheme(
                data: Theme.of(context).brightness == Brightness.dark
                    ? _darkTokens
                    : _lightTokens,
                child: child ?? const SizedBox.shrink(),
              ),
            ),
          ),
    );
    // One scope above the router, because an accessibility feature change and
    // a browser media query change both arrive outside the widget tree and
    // would otherwise rebuild nothing (motion and microinteractions, 6.2).
    return MotionScope(
      controller: _motion,
      child: workspace == null
          ? app
          : WorkspaceScope(controller: workspace, child: app),
    );
  }
}

/// The tokens, built once. `UiTheme.of` folds the live density and the live
/// reduced-motion state into these on every read, so the stored value carries
/// only what does not change while the window is open.
final UiThemeData _lightTokens = UiThemeData.light();

/// The dark tokens.
final UiThemeData _darkTokens = UiThemeData.dark();
