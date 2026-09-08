import 'package:firebase_app_check/firebase_app_check.dart';
import 'package:flutter/foundation.dart';
import 'package:firebase_auth/firebase_auth.dart';
import 'package:firebase_core/firebase_core.dart';
import 'package:flutter/material.dart';
import 'firebase_options.dart';
import 'src/api_repository.dart';
import 'src/auth.dart';
import 'src/models.dart';
import 'src/workspace.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  SessionAccess? session;
  SpecimenRepository? repository;
  String? setupMessage;
  const apiUrl = String.fromEnvironment('SPECIMEN_API_BASE_URL');
  const localSynthetic = bool.fromEnvironment('SPECIMEN_LOCAL_SYNTHETIC');
  try {
    if (localSynthetic) {
      final uri = Uri.parse(apiUrl);
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
      if (options.appId.endsWith(':ci-placeholder')) {
        setupMessage =
            'This verification build has no live Firebase configuration. Configure Firebase Authentication and the application API to connect to a collection.';
      } else if (apiUrl.isEmpty) {
        setupMessage =
            'The application API is not configured. Set SPECIMEN_API_BASE_URL in the approved build configuration.';
      } else {
        await Firebase.initializeApp(options: options);
        const siteKey = String.fromEnvironment('SPECIMEN_RECAPTCHA_SITE_KEY');
        if (kIsWeb && siteKey.isEmpty) {
          throw StateError('App Check site key missing');
        }
        await FirebaseAppCheck.instance.activate(
          providerWeb: kIsWeb ? ReCaptchaV3Provider(siteKey) : null,
        );
        final auth = FirebaseAuth.instance;
        const emulatorHost = String.fromEnvironment(
          'SPECIMEN_AUTH_EMULATOR_HOST',
        );
        if (emulatorHost.isNotEmpty) {
          await auth.useAuthEmulator(emulatorHost, 9099);
        }
        session = FirebaseSession(auth);
        repository = ApiSpecimenRepository(
          baseUrl: Uri.parse(apiUrl),
          token: session.token,
          appCheckToken: () => FirebaseAppCheck.instance.getToken(),
        );
      }
    }
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
    home: session == null || repository == null
        ? Scaffold(
            body: Center(
              child: Padding(
                padding: const EdgeInsets.all(32),
                child: ConstrainedBox(
                  constraints: const BoxConstraints(maxWidth: 560),
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      if (synthetic)
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
                        style: TextStyle(
                          fontSize: 22,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                      const SizedBox(height: 12),
                      Text(
                        setupMessage ??
                            'Configure Firebase Authentication and the application API to begin.',
                        textAlign: TextAlign.center,
                      ),
                    ],
                  ),
                ),
              ),
            ),
          )
        : StreamBuilder<bool>(
            stream: session!.changes,
            initialData: session!.signedIn,
            builder: (context, snapshot) => snapshot.data == true
                ? CollectionWorkspace(
                    key: ValueKey(session!.userId),
                    repository: repository!,
                    session: session!,
                  )
                : SignInScreen(session: session!),
          ),
  );
}
