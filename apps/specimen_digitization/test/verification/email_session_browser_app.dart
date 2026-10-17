// Browser-only acceptance fixture. No production entry point imports this file.
// Firebase sends the email link through the Auth emulator; collection data is fake.
import 'dart:async';
import 'dart:convert';
import 'dart:js_interop';
import 'dart:js_interop_unsafe';

import 'package:firebase_auth/firebase_auth.dart';
import 'package:firebase_core/firebase_core.dart';
import 'package:flutter/semantics.dart';
import 'package:flutter/widgets.dart';
import 'package:specimen_digitization/main.dart';
import 'package:specimen_digitization/src/auth.dart';
import 'package:specimen_digitization/src/magic_link.dart';
import 'package:specimen_digitization/src/models.dart';

const _project = 'demo-login-journey';
const _emulatorApiIdentifier = 'fake-browser-acceptance-key';
const _emulatorPort = int.fromEnvironment(
  'EMAIL_SESSION_AUTH_PORT',
  defaultValue: 9409,
);
const _intendedRoute = '/c/browser%2Facceptance/queue?status=held';

class _BrowserRepository implements SpecimenRepository {
  int scopeLoads = 0;
  @override
  String get mode => 'synthetic';
  @override
  List<dynamic> get blockers => const [];
  @override
  Future<List<CollectionScope>> scopes() async {
    scopeLoads++;
    return const [
      CollectionScope(
        organizationId: 'browser',
        collectionId: 'acceptance',
        name: 'Browser acceptance fixture',
        permissions: ['reviewer'],
      ),
    ];
  }

  @override
  Future<List<Json>> profiles(CollectionScope scope) async => [];
  @override
  Future<SpecimenPage> specimenPage(
    CollectionScope scope, {
    Map<String, String> filters = const {},
    String? cursor,
  }) async => SpecimenPage([]);
  @override
  dynamic noSuchMethod(Invocation invocation) =>
      throw UnsupportedError('Unexpected collection operation');
}

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  if (Uri.base.scheme != 'http' ||
      !{'localhost', '127.0.0.1'}.contains(Uri.base.host)) {
    throw StateError('Browser acceptance is restricted to loopback.');
  }
  await Firebase.initializeApp(
    options: const FirebaseOptions(
      apiKey: _emulatorApiIdentifier,
      appId: '1:123456789:web:browser-acceptance',
      messagingSenderId: '123456789',
      projectId: _project,
      authDomain: 'localhost',
    ),
  );
  final auth = FirebaseAuth.instance;
  await auth.useAuthEmulator('127.0.0.1', _emulatorPort);
  final session = FirebaseSession(auth);
  final repository = _BrowserRepository();
  // Read-only probes expose no tokens, code, link, or stored Firebase material.
  globalContext.setProperty(
    'emailSessionAcceptanceState'.toJS,
    (() => jsonEncode({
      'signedIn': session.signedIn,
      'verified': session.emailVerified,
      'uid': session.userId,
      'scopeLoads': repository.scopeLoads,
    })).toJS,
  );
  final actionCode = Uri.base.queryParameters['fixtureCode'];
  final browser = MemoryEmailLinkBrowser(
    uri: actionCode == null
        ? null
        : Uri.https('specimen-digitization.web.app', '/', {
            'mode': 'signIn',
            'oobCode': actionCode,
            'apiKey': _emulatorApiIdentifier,
          }),
  );
  SemanticsBinding.instance.ensureSemantics();
  runApp(
    SpecimenDigitizationApp(
      session: session,
      repository: repository,
      synthetic: true,
      emailLinkBrowser: browser,
      initialLocation: actionCode == null ? _intendedRoute : '/setup',
    ),
  );
}
