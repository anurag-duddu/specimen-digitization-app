import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/connection_config.dart';
import 'package:specimen_digitization/src/production_startup.dart';
import 'auth_before_backend_test.dart' show AuthOnlySession;
import 'widget_test.dart' show TestRepository;

const validConfig = ConnectionConfig(
  apiUrl: 'https://collection.example.test',
  siteKey: 'test-enterprise-site-key',
);

void main() {
  final authOnlyConfigurations = <String, ConnectionConfig>{
    'absent backend settings': const ConnectionConfig(apiUrl: '', siteKey: ''),
    'site key without API': const ConnectionConfig(apiUrl: '', siteKey: 'key'),
    'API without site key': ConnectionConfig(
      apiUrl: validConfig.apiUrl,
      siteKey: '',
    ),
    'invalid API URL': ConnectionConfig(
      apiUrl: 'http://localhost',
      siteKey: validConfig.siteKey,
    ),
    'authentication emulator in production': ConnectionConfig(
      apiUrl: validConfig.apiUrl,
      siteKey: validConfig.siteKey,
      authEmulatorHost: 'localhost:9099',
    ),
  };
  for (final entry in authOnlyConfigurations.entries) {
    test('${entry.key}: auth available, no App Check or repository', () async {
      final session = AuthOnlySession();
      addTearDown(session.controller.close);
      final calls = <String>[];
      final result = await initializeProduction(
        firebaseConfigured: true,
        config: entry.value,
        web: true,
        initializeSession: () async {
          calls.add('firebase');
          return session;
        },
        activateAppCheck: () async {
          calls.add('app-check');
        },
        createRepository: (uri, auth) {
          calls.add('repository');
          return TestRepository();
        },
      );
      expect(result.session, same(session));
      expect(result.repository, isNull);
      expect(result.setupMessage, collectionPendingMessage);
      expect(calls, ['firebase']);
      expect(session.tokenCalls, 0);
      expect(session.verificationRequests, 0);
    });
  }

  test(
    'placeholder Firebase configuration performs no initialization',
    () async {
      final calls = <String>[];
      final result = await initializeProduction(
        firebaseConfigured: false,
        config: validConfig,
        web: true,
        initializeSession: () async {
          calls.add('firebase');
          throw StateError('placeholder must not initialize');
        },
        activateAppCheck: () async {
          calls.add('app-check');
        },
        createRepository: (uri, auth) {
          calls.add('repository');
          return TestRepository();
        },
      );
      expect(calls, isEmpty);
      expect(result.session, isNull);
      expect(result.repository, isNull);
      expect(result.setupMessage, contains('no live Firebase configuration'));
    },
  );

  test(
    'failed Firebase initialization stays in setup without backend',
    () async {
      final calls = <String>[];
      final result = await initializeProduction(
        firebaseConfigured: true,
        config: validConfig,
        web: true,
        initializeSession: () async {
          calls.add('firebase');
          throw StateError('local test Firebase failure');
        },
        activateAppCheck: () async {
          calls.add('app-check');
        },
        createRepository: (uri, auth) {
          calls.add('repository');
          return TestRepository();
        },
      );
      expect(calls, ['firebase']);
      expect(result.session, isNull);
      expect(result.repository, isNull);
      expect(result.setupMessage, isNotEmpty);
      expect(result.setupMessage, isNot(contains('local test')));
    },
  );

  test(
    'App Check failure preserves auth and does not create repository',
    () async {
      final session = AuthOnlySession();
      addTearDown(session.controller.close);
      final calls = <String>[];
      final result = await initializeProduction(
        firebaseConfigured: true,
        config: validConfig,
        web: true,
        initializeSession: () async {
          calls.add('firebase');
          return session;
        },
        activateAppCheck: () async {
          calls.add('app-check');
          throw StateError('local test App Check failure');
        },
        createRepository: (uri, auth) {
          calls.add('repository');
          return TestRepository();
        },
      );
      expect(calls, ['firebase', 'app-check']);
      expect(result.session, same(session));
      expect(result.repository, isNull);
      expect(result.setupMessage, collectionPendingMessage);
      expect(session.tokenCalls, 0);
    },
  );

  test(
    'valid backend waits for App Check before constructing repository',
    () async {
      final session = AuthOnlySession();
      addTearDown(session.controller.close);
      final repository = TestRepository();
      final calls = <String>[];
      final result = await initializeProduction(
        firebaseConfigured: true,
        config: validConfig,
        web: true,
        initializeSession: () async {
          calls.add('firebase');
          return session;
        },
        activateAppCheck: () async {
          await Future<void>.delayed(Duration.zero);
          calls.add('app-check');
        },
        createRepository: (uri, auth) {
          expect(uri, Uri.parse(validConfig.apiUrl));
          expect(auth, same(session));
          expect(calls, ['firebase', 'app-check']);
          calls.add('repository');
          return repository;
        },
      );
      expect(calls, ['firebase', 'app-check', 'repository']);
      expect(result.session, same(session));
      expect(result.repository, same(repository));
      expect(result.setupMessage, isNull);
      expect(session.tokenCalls, 0);
      expect(session.verificationRequests, 0);
    },
  );
}
