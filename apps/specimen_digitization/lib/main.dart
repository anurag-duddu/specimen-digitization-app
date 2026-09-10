import 'package:firebase_app_check/firebase_app_check.dart';
import 'package:flutter/foundation.dart';
import 'package:firebase_auth/firebase_auth.dart';
import 'package:firebase_core/firebase_core.dart';
import 'package:flutter/material.dart';
import 'firebase_options.dart';
import 'src/api_repository.dart';
import 'src/app_check.dart';
import 'src/auth.dart';
import 'src/connection_config.dart';
import 'src/email_verification.dart';
import 'src/models.dart';
import 'src/production_startup.dart';
import 'src/workspace.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
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
        ? 'Local synthetic setup could not be completed. Check the demo API configuration.'
        : 'Application setup could not be completed. Ask your administrator to check Firebase and the API configuration.';
  }
  runApp(
    SpecimenDigitizationApp(
      session: session,
      repository: repository,
      setupMessage: setupMessage,
      synthetic: localSynthetic,
    ),
  );
}

class SpecimenDigitizationApp extends StatelessWidget {
  const SpecimenDigitizationApp({
    super.key,
    this.session,
    this.repository,
    this.setupMessage,
    this.synthetic = false,
  });
  final SessionAccess? session;
  final SpecimenRepository? repository;
  final String? setupMessage;
  final bool synthetic;
  @override
  Widget build(BuildContext context) => MaterialApp(
    title: 'Specimen Digitization',
    debugShowCheckedModeBanner: false,
    theme: ThemeData(
      useMaterial3: true,
      scaffoldBackgroundColor: const Color(0xfff4f6f3),
      colorScheme: ColorScheme.fromSeed(
        seedColor: const Color(0xff174f3b),
        surface: const Color(0xfff9fbf7),
      ),
      inputDecorationTheme: const InputDecorationTheme(
        border: OutlineInputBorder(),
      ),
      filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(minimumSize: const Size(48, 48)),
      ),
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(minimumSize: const Size(48, 48)),
      ),
      appBarTheme: const AppBarTheme(
        backgroundColor: Color(0xfff4f6f3),
        surfaceTintColor: Colors.transparent,
      ),
    ),
    home: session == null
        ? _ConnectionSetup(setupMessage: setupMessage, synthetic: synthetic)
        : StreamBuilder<bool>(
            stream: session!.changes,
            initialData: session!.signedIn,
            builder: (context, snapshot) => snapshot.data == true
                ? EmailVerificationGate(
                    session: session!,
                    child: repository == null
                        ? _ConnectionSetup(
                            setupMessage:
                                setupMessage ?? collectionPendingMessage,
                            synthetic: synthetic,
                            session: session,
                          )
                        : CollectionWorkspace(
                            key: ValueKey(session!.userId),
                            repository: repository!,
                            session: session!,
                          ),
                  )
                : SignInScreen(session: session!),
          ),
  );
}

class _ConnectionSetup extends StatefulWidget {
  const _ConnectionSetup({
    this.setupMessage,
    this.synthetic = false,
    this.session,
  });
  final String? setupMessage;
  final bool synthetic;
  final SessionAccess? session;

  @override
  State<_ConnectionSetup> createState() => _ConnectionSetupState();
}

class _ConnectionSetupState extends State<_ConnectionSetup> {
  bool _signingOut = false;
  String? _error;

  Future<void> _signOut() async {
    setState(() {
      _signingOut = true;
      _error = null;
    });
    try {
      await widget.session!.signOut();
    } catch (error) {
      if (mounted) setState(() => _error = authErrorMessage(error));
    } finally {
      if (mounted) setState(() => _signingOut = false);
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    body: Center(
      child: SingleChildScrollView(
        padding: const EdgeInsets.all(32),
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 560),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              if (widget.synthetic)
                const Text(
                  'SYNTHETIC ENVIRONMENT — local fixture access only; not museum-approved records.',
                ),
              const Icon(Icons.biotech_outlined, size: 56),
              const SizedBox(height: 24),
              Text(
                'Specimen Digitization',
                style: Theme.of(context).textTheme.headlineMedium,
              ),
              const SizedBox(height: 16),
              const Text(
                'Collection connection required',
                style: TextStyle(fontSize: 22, fontWeight: FontWeight.w600),
              ),
              const SizedBox(height: 12),
              Text(
                widget.setupMessage ??
                    'Configure Firebase Authentication and the application API to begin.',
                textAlign: TextAlign.center,
              ),
              if (_error != null)
                Padding(
                  padding: const EdgeInsets.only(top: 16),
                  child: Semantics(liveRegion: true, child: Text(_error!)),
                ),
              if (widget.session != null) ...[
                const SizedBox(height: 16),
                TextButton(
                  onPressed: _signingOut ? null : _signOut,
                  child: Text(_signingOut ? 'Signing out…' : 'Sign out'),
                ),
              ],
            ],
          ),
        ),
      ),
    ),
  );
}
