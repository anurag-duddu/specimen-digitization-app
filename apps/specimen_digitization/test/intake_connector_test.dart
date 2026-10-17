import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/screens/intake/bulk_intake_controller.dart';
import 'package:specimen_digitization/src/screens/intake/bulk_intake_repository.dart';
import 'package:specimen_digitization/src/screens/intake/intake_auth_session.dart';
import 'package:specimen_digitization/src/screens/intake/intake_source_picker.dart';
import 'package:specimen_digitization/src/theme/app_theme.dart';
import 'package:specimen_ui/specimen_ui.dart';

// Transport and OAuth fixtures only; this suite cannot establish live provider
// or institutional acceptance.
class ConnectorRepository implements BulkIntakeRepository {
  final List<Json> accounts = [];
  final List<(String, String, Json?)> calls = [];
  bool configured = true, deny = false, failPicker = false;
  Json? pending;
  String? emptyAccount;
  bool loseCompletionReply = false;
  Completer<Json>? delayedPoll;
  Json account(String id, String provider, {String access = 'folders'}) => {
    'id': id,
    'provider': provider,
    'access': access,
    'account_id': 'identity-$id',
    'account_label': '$id@example.test',
    'state': 'connected',
  };
  @override
  Future<Json> intakeRequest(
    CollectionScope scope,
    String method,
    String path, {
    Json? body,
    Map<String, String>? query,
    Uint8List? bytes,
    int? offset,
  }) async {
    calls.add((method, path, body));
    if (method == 'GET' &&
        path == '/connections/first' &&
        delayedPoll != null) {
      return delayedPoll!.future;
    }
    if (path == '/connections' && method == 'GET') {
      return {
        'configured': configured,
        'items': accounts
            .where((a) => a['provider'] == query?['provider'])
            .toList(),
      };
    }
    if (path == '/connections' && method == 'POST') {
      if (!configured) {
        throw const ApiFailure(
          'Provider setup is unavailable.',
          code: 'provider_not_configured',
          details: {'action': 'administrator'},
        );
      }
      pending = {
        ...body!,
        'id': body['reconnect_id'] ?? 'new',
        'state': 'needs_authorization',
        'authorization_url': 'https://provider.example/oauth',
      };
      return pending!;
    }
    if (path == '/connections/complete') {
      final row = {
        ...pending!,
        ...account(
          pending!['id'] as String,
          pending!['provider'] as String,
          access: pending!['access'] as String,
        ),
      };
      if (deny) {
        row['state'] = 'policy_blocked';
        row['error'] = {
          'message': 'Your organization prevents this connection.',
          'action': 'administrator',
        };
      }
      accounts.removeWhere((a) => a['id'] == row['id']);
      accounts.add(row);
      if (loseCompletionReply) {
        throw const ApiFailure('Connection interrupted.', code: 'offline');
      }
      return row;
    }
    if (path.endsWith('/browse')) {
      if (path.split('/')[2] == emptyAccount) return {'items': <Json>[]};
      return {
        'items': [
          {
            'id': 'photo',
            'filename': 'photo.jpg',
            'supported': true,
            'source': {
              'provider': 'dropbox',
              'connection_id': path.split('/')[2],
              'object_id': 'photo',
            },
          },
        ],
      };
    }
    if (path.endsWith('/picker') && method == 'POST') {
      if (failPicker) {
        throw const ApiFailure(
          'Picker temporarily unavailable.',
          code: 'unavailable',
          details: {'action': 'retry'},
        );
      }
      return {'id': 'picker', 'url': 'https://api.example/picker'};
    }
    if (path.contains('/picker/')) return {'state': 'pending'};
    if (path.endsWith('/disconnect')) {
      final index = accounts.indexWhere((a) => a['id'] == path.split('/')[2]);
      accounts[index] = {...accounts[index], 'state': 'disconnected'};
      return accounts[index];
    }
    if (method == 'GET' && path.startsWith('/connections/')) {
      return accounts.firstWhere((a) => a['id'] == path.split('/').last);
    }
    throw StateError('Unexpected $method $path');
  }

  @override
  Future<Uint8List> intakePreview(
    CollectionScope scope,
    String itemId, {
    bool full = false,
  }) async => Uint8List(0);
}

class ConnectorSession implements IntakeAuthSession {
  bool keepOpen = false, closed = false;
  String? pickerUrl;
  @override
  String get returnOrigin => 'https://app.example';
  @override
  Future<Json> authenticate(String url, {bool keepOpen = false}) async {
    this.keepOpen = keepOpen;
    return {'state': 'state', 'code': 'code'};
  }

  @override
  Future<void> openPicker(String url) async => pickerUrl = url;
  @override
  void close() => closed = true;
}

Future<List<ConnectorSession>> mount(
  WidgetTester tester,
  ConnectorRepository repository,
  String provider, {
  double scale = 1,
}) async {
  final sessions = <ConnectorSession>[];
  final controller = BulkIntakeController(
    repository: repository,
    scope: const CollectionScope(
      organizationId: 'org',
      collectionId: 'collection',
      name: 'Collection',
    ),
    userId: 'owner',
  );
  addTearDown(controller.dispose);
  tester.view.physicalSize = const Size(390, 844);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(
    MaterialApp(
      theme: AppTheme.light(),
      home: Scaffold(
        body: MediaQuery(
          data: MediaQueryData(
            size: const Size(390, 844),
            textScaler: TextScaler.linear(scale),
          ),
          child: SingleChildScrollView(
            child: IntakeSourcePicker(
              controller: controller,
              provider: provider,
              authSessionFactory: () {
                final session = ConnectorSession();
                sessions.add(session);
                return session;
              },
            ),
          ),
        ),
      ),
    ),
  );
  await tester.pumpAndSettle();
  return sessions;
}

Future<void> press(WidgetTester tester, String label) async {
  final button = find.widgetWithText(UiButton, label);
  await tester.ensureVisible(button);
  await tester.tap(button);
  await tester.pumpAndSettle();
}

void main() {
  testWidgets(
    'status reconciliation clears reconnect after a lost completion acknowledgement',
    (tester) async {
      final repository = ConnectorRepository()..loseCompletionReply = true;
      await mount(tester, repository, 'google_drive');
      await press(tester, 'Connect Google Drive');
      expect(find.text('Retry connection'), findsOneWidget);
      await tester.pump(const Duration(seconds: 3));
      await tester.pumpAndSettle();
      expect(find.text('Connected'), findsOneWidget);
      expect(find.text('Retry connection'), findsNothing);
      expect(find.text('Connection interrupted.'), findsNothing);
      expect(
        repository.calls.where((c) => c.$1 == 'POST' && c.$2 == '/connections'),
        hasLength(1),
      );
    },
  );

  testWidgets(
    'the same file path in two accounts remains two independent selections',
    (tester) async {
      final repository = ConnectorRepository();
      repository.accounts.addAll([
        repository.account('first', 'dropbox'),
        repository.account('second', 'dropbox'),
      ]);
      await mount(tester, repository, 'dropbox');
      await tester.tap(find.text('Choose an account'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('first@example.test'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('photo.jpg'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('first@example.test'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('second@example.test'));
      await tester.pumpAndSettle();
      final checkbox = tester.widget<UiCheckbox>(
        find.widgetWithText(UiCheckbox, 'photo.jpg'),
      );
      expect(checkbox.value, isFalse);
      await tester.tap(find.text('photo.jpg'));
      await tester.pumpAndSettle();
      expect(find.text('Add 2 photos'), findsOneWidget);
    },
  );

  testWidgets(
    'selected photos stay actionable when another account has an empty folder',
    (tester) async {
      final repository = ConnectorRepository()..emptyAccount = 'empty';
      repository.accounts.addAll([
        repository.account('first', 'dropbox'),
        repository.account('empty', 'dropbox'),
      ]);
      await mount(tester, repository, 'dropbox');
      await tester.tap(find.text('Choose an account'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('first@example.test'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('photo.jpg'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('first@example.test'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('empty@example.test'));
      await tester.pumpAndSettle();
      expect(find.text('photo.jpg'), findsNothing);
      final add = tester.widget<UiButton>(
        find.widgetWithText(UiButton, 'Add 1 photo'),
      );
      expect(add.onPressed, isNotNull);
    },
  );

  testWidgets(
    'expired account remains reconnectable alongside a connected account',
    (tester) async {
      final repository = ConnectorRepository();
      repository.accounts.addAll([
        {
          ...repository.account('expired', 'google_drive'),
          'state': 'needs_authorization',
          'error': {'message': 'Sign in again.', 'action': 'connect'},
        },
        repository.account('valid', 'google_drive'),
      ]);
      await mount(tester, repository, 'google_drive');
      await press(tester, 'Reconnect expired@example.test to resume imports');
      final create = repository.calls.firstWhere(
        (c) => c.$1 == 'POST' && c.$2 == '/connections',
      );
      expect(create.$3!['reconnect_id'], 'expired');
      expect(create.$3!['access'], 'folders');
      expect(repository.calls.last.$2, '/connections/expired/browse');
    },
  );

  testWidgets(
    'delayed poll for previous account cannot replace the selected account',
    (tester) async {
      final repository = ConnectorRepository();
      repository.accounts.addAll([
        repository.account('first', 'dropbox'),
        repository.account('second', 'dropbox'),
      ]);
      await mount(tester, repository, 'dropbox');
      await tester.tap(find.text('Choose an account'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('first@example.test'));
      await tester.pumpAndSettle();
      repository.delayedPoll = Completer<Json>();
      await tester.pump(const Duration(seconds: 3));
      expect(repository.calls.last.$2, '/connections/first');
      await tester.tap(find.text('first@example.test'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('second@example.test'));
      await tester.pumpAndSettle();
      repository.delayedPoll!.complete(repository.account('first', 'dropbox'));
      await tester.pumpAndSettle();
      final choice = tester.widget<UiSelect<String>>(
        find.byType(UiSelect<String>),
      );
      expect(choice.options.map((o) => o.value), contains('second'));
      expect(choice.value, 'second');
      expect(find.text('Connected'), findsOneWidget);
    },
  );

  testWidgets(
    'unconfigured provider offers Connect and explains setup only after attempted connection',
    (tester) async {
      final repository = ConnectorRepository()..configured = false;
      final sessions = await mount(
        tester,
        repository,
        'google_drive',
        scale: 2,
      );
      expect(find.text('Connect Google Drive'), findsOneWidget);
      expect(find.textContaining('administrator'), findsNothing);
      await press(tester, 'Connect Google Drive');
      expect(find.text('Provider setup is unavailable.'), findsOneWidget);
      expect(find.text('Copy administrator details'), findsOneWidget);
      expect(find.text('Retry connection'), findsOneWidget);
      expect(find.textContaining('pending'), findsNothing);
      expect(sessions.single.closed, isTrue);
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets(
    'Google consent continues immediately into Picker using the same popup',
    (tester) async {
      final repository = ConnectorRepository();
      final sessions = await mount(tester, repository, 'google_drive');
      await press(tester, 'Connect Google Drive');
      expect(find.text('Connected'), findsOneWidget);
      expect(find.text('new@example.test'), findsOneWidget);
      expect(sessions, hasLength(1));
      expect(sessions.single.keepOpen, isTrue);
      expect(sessions.single.pickerUrl, 'https://api.example/picker');
      expect(sessions.single.closed, isFalse);
      final create = repository.calls.firstWhere(
        (c) => c.$1 == 'POST' && c.$2 == '/connections',
      );
      expect(create.$3!['access'], 'files');
      expect(repository.calls.any((c) => c.$2.endsWith('/browse')), isFalse);
      await tester.pumpWidget(const SizedBox());
      expect(sessions.single.closed, isTrue);
    },
  );

  testWidgets('Dropbox consent immediately browses photos and closes sign-in', (
    tester,
  ) async {
    final repository = ConnectorRepository();
    final sessions = await mount(tester, repository, 'dropbox');
    await press(tester, 'Connect Dropbox');
    expect(find.text('Connected'), findsOneWidget);
    expect(find.text('photo.jpg'), findsOneWidget);
    expect(sessions.single.closed, isTrue);
    expect(
      repository.calls.where((c) => c.$2.endsWith('/browse')),
      hasLength(1),
    );
  });

  testWidgets(
    'reopening a connected folder account resumes browsing without consent',
    (tester) async {
      final repository = ConnectorRepository();
      repository.accounts.add(repository.account('saved', 'google_drive'));
      final sessions = await mount(tester, repository, 'google_drive');
      expect(find.text('saved@example.test'), findsOneWidget);
      expect(find.text('photo.jpg'), findsOneWidget);
      expect(sessions, isEmpty);
      expect(find.text('Connect Google Drive'), findsNothing);
    },
  );

  testWidgets('multiple accounts require explicit choice before browsing', (
    tester,
  ) async {
    final repository = ConnectorRepository();
    repository.accounts.addAll([
      repository.account('first', 'dropbox'),
      repository.account('second', 'dropbox'),
    ]);
    await mount(tester, repository, 'dropbox');
    expect(repository.calls.any((c) => c.$2.endsWith('/browse')), isFalse);
    expect(find.byType(UiSelect<String>), findsOneWidget);
    await tester.tap(find.text('Choose an account'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('second@example.test'));
    await tester.pumpAndSettle();
    expect(repository.calls.last.$2, '/connections/second/browse');
  });

  testWidgets(
    'policy denial keeps its reason after copying details and retries the existing account',
    (tester) async {
      final repository = ConnectorRepository()..deny = true;
      String? copied;
      tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(
        SystemChannels.platform,
        (call) async {
          if (call.method == 'Clipboard.setData') {
            copied = (call.arguments as Map)['text'] as String;
          }
          return null;
        },
      );
      addTearDown(
        () => tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(
          SystemChannels.platform,
          null,
        ),
      );
      await mount(tester, repository, 'dropbox', scale: 2);
      await press(tester, 'Connect Dropbox');
      const reason = 'Your organization prevents this connection.';
      expect(find.text(reason), findsOneWidget);
      expect(find.text('Connected'), findsNothing);
      await press(tester, 'Copy administrator details');
      expect(copied, contains(reason));
      expect(find.text(reason), findsOneWidget);
      expect(find.text('Administrator details copied'), findsOneWidget);
      expect(find.textContaining('pending'), findsNothing);
      repository.deny = false;
      await press(tester, 'Retry connection');
      expect(find.text('Connected'), findsOneWidget);
      expect(find.text(reason), findsNothing);
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets(
    'expired known account reconnects with its identity and access level',
    (tester) async {
      final repository = ConnectorRepository();
      repository.accounts.add({
        ...repository.account('saved', 'google_drive'),
        'state': 'needs_authorization',
        'error': {'message': 'Sign in again.', 'action': 'connect'},
      });
      await mount(tester, repository, 'google_drive');
      await press(tester, 'Retry connection');
      final create = repository.calls.firstWhere(
        (c) => c.$1 == 'POST' && c.$2 == '/connections',
      );
      expect(create.$3!['reconnect_id'], 'saved');
      expect(create.$3!['access'], 'folders');
      expect(find.text('photo.jpg'), findsOneWidget);
    },
  );

  testWidgets(
    'Picker failure closes popup and Retry uses the already connected account',
    (tester) async {
      final repository = ConnectorRepository()..failPicker = true;
      final sessions = await mount(tester, repository, 'google_drive');
      await press(tester, 'Connect Google Drive');
      expect(sessions.single.closed, isTrue);
      expect(find.text('Connected'), findsOneWidget);
      repository.failPicker = false;
      await press(tester, 'Retry');
      expect(sessions, hasLength(2));
      expect(sessions.last.pickerUrl, isNotNull);
      expect(
        repository.calls.where((c) => c.$1 == 'POST' && c.$2 == '/connections'),
        hasLength(1),
      );
    },
  );
}
