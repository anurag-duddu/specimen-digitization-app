import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/screens/intake/bulk_intake_controller.dart';
import 'package:specimen_digitization/src/screens/intake/bulk_intake_repository.dart';
import 'package:specimen_digitization/src/screens/intake/intake_auth_session.dart';
import 'package:specimen_digitization/src/screens/intake/intake_source_picker.dart';
import 'package:specimen_digitization/src/screens/intake/intake_picker_host.dart';
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
  bool deferNativeSelection = false;
  ApiFailure? retryFailure;
  int authorizations = 0;
  final List<Json> pickerReplies = [];
  final Map<String, List<Json>> pickerRepliesById = {};
  final List<Json> cancelReplies = [];
  late ConnectorPickerHost host;
  bool nestedFolders = false;
  Completer<Json>? delayedPoll;
  String delayedConnection = 'first';
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
        path == '/connections/$delayedConnection' &&
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
      authorizations++;
      pending = {
        ...body!,
        'id': body['reconnect_id'] ?? 'new',
        'state': 'needs_authorization',
        'authorization_url': 'https://provider.example/oauth',
        if (body['return_origin'] == null &&
            body['provider'] == 'google_drive' &&
            body['access'] == 'files')
          'picker_id': authorizations == 1
              ? 'native-picker'
              : 'native-picker-$authorizations',
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
      if (body?['picked_file_ids'] == 'native-photo') {
        row['selection'] = {
          'state': 'selected',
          'items': [
            {
              'id': 'native-photo',
              'filename': 'native-photo.jpg',
              'supported': true,
              'source': {
                'provider': 'google_drive',
                'connection_id': row['id'],
                'object_id': 'native-photo',
                'version': '1',
              },
            },
          ],
          'failures': <Json>[],
        };
        if (deferNativeSelection) {
          row['selection'] = {
            'state': 'selecting',
            'items': <Json>[],
            'failures': <Json>[],
            'progress': {'processed': 0, 'total': 500},
          };
        }
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
        if (nestedFolders) 'next_cursor': 'next',
        'items': [
          if (nestedFolders && body?['folder'] == '')
            {'id': 'folder', 'filename': 'Folder', 'kind': 'folder'},
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
      final origin = body?['return_origin'] as String?;
      return {
        'id': 'picker',
        'url': Uri.https(
          'api.example',
          '/v1/intake/picker',
          origin == null
              ? null
              : {'embed_origin': origin, 'picker_id': 'picker'},
        ).replace(fragment: 'state=opaque-picker-capability').toString(),
      };
    }
    if (path.contains('/picker/')) {
      if (path.endsWith('/cancel')) {
        return cancelReplies.isEmpty
            ? {'state': 'cancelled'}
            : cancelReplies.removeAt(0);
      }
      if (path.endsWith('/retry') && retryFailure != null) throw retryFailure!;
      final parts = path.split('/');
      final id = path.endsWith('/retry') ? parts[parts.length - 2] : parts.last;
      final replies = pickerRepliesById[id] ?? pickerReplies;
      return replies.isEmpty ? {'state': 'pending'} : replies.removeAt(0);
    }
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
  ConnectorSession({this.native = false});
  final bool native;
  bool keepOpen = false, closed = false;
  String? pickerUrl;
  @override
  String? get returnOrigin => native ? null : 'https://app.example';
  @override
  Future<Json> authenticate(String url, {bool keepOpen = false}) async {
    this.keepOpen = keepOpen;
    return {
      'state': 'state',
      'code': 'code',
      if (native) 'picked_file_ids': 'native-photo',
    };
  }

  @override
  Future<void> openPicker(String url) async => pickerUrl = url;
  @override
  void close() => closed = true;
}

class ConnectorPickerHost extends IntakePickerHost {
  ConnectorPickerHost({this.native = false});
  final bool native;
  final List<ConnectorFrame> frames = [];
  int disposedFrames = 0;
  bool Function()? consentClosed;
  @override
  String? get returnOrigin => native ? null : 'https://app.example';
  @override
  Widget buildFrame({
    required String url,
    required String pickerId,
    required ValueChanged<String> onEvent,
    required ValueChanged<String> onFailure,
  }) => ConnectorFrame(
    key: ValueKey(pickerId),
    host: this,
    url: url,
    pickerId: pickerId,
    onEvent: onEvent,
    onFailure: onFailure,
  );
}

class ConnectorFrame extends StatefulWidget {
  const ConnectorFrame({
    super.key,
    required this.host,
    required this.url,
    required this.pickerId,
    required this.onEvent,
    required this.onFailure,
  });
  final ConnectorPickerHost host;
  final String url, pickerId;
  final ValueChanged<String> onEvent, onFailure;
  @override
  State<ConnectorFrame> createState() => _ConnectorFrameState();
}

class _ConnectorFrameState extends State<ConnectorFrame> {
  @override
  void initState() {
    super.initState();
    expect(widget.host.consentClosed?.call(), isNot(false));
    widget.host.frames.add(widget);
  }

  @override
  void dispose() {
    widget.host.disposedFrames++;
    super.dispose();
  }

  @override
  Widget build(BuildContext context) =>
      const Center(child: Text('Inline Drive fixture'));
}

Future<List<ConnectorSession>> mount(
  WidgetTester tester,
  ConnectorRepository repository,
  String provider, {
  double scale = 1,
  bool native = false,
  bool durablePicker = true,
}) async {
  final sessions = <ConnectorSession>[];
  repository.host = ConnectorPickerHost(native: native)
    ..consentClosed = () => sessions.every((session) => session.closed);
  final controller = BulkIntakeController(
    repository: repository,
    scope: const CollectionScope(
      organizationId: 'org',
      collectionId: 'collection',
      name: 'Collection',
    ),
    userId: 'owner',
  );
  controller.capabilities = {'durable_picker_selection': durablePicker};
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
              pickerHost: repository.host,
              authSessionFactory: () {
                final session = ConnectorSession(native: native);
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
  final button = find.widgetWithText(UiButton, label).evaluate().isNotEmpty
      ? find.widgetWithText(UiButton, label)
      : find.widgetWithText(UiListRow, label);
  await tester.ensureVisible(button);
  await tester.tap(button);
  await tester.pumpAndSettle();
}

Future<void> openOptions(WidgetTester tester, String provider) async {
  await tester.tap(
    find.byWidgetPredicate(
      (widget) =>
          widget is UiMenuTrigger &&
          widget.semanticsLabel == '$provider options',
    ),
  );
  await tester.pumpAndSettle();
}

void main() {
  for (final status in [404, 405]) {
    testWidgets('older server retry falls back to status after $status', (
      tester,
    ) async {
      final repository = ConnectorRepository()
        ..deferNativeSelection = true
        ..retryFailure = ApiFailure('Route unavailable.', status: status);
      repository.pickerReplies.addAll([
        {
          'state': 'selecting',
          'items': <Json>[],
          'failures': <Json>[],
          'progress': {'processed': 1, 'total': 2},
          'error': {'action': 'retry', 'message': 'Please retry.'},
        },
        {'state': 'selected', 'items': <Json>[], 'failures': <Json>[]},
      ]);
      await mount(
        tester,
        repository,
        'google_drive',
        native: true,
        durablePicker: false,
      );
      await press(tester, 'Connect Google Drive');
      await tester.pump(const Duration(seconds: 3));
      await tester.pumpAndSettle();
      await press(tester, 'Retry');
      expect(
        repository.calls.where((call) => call.$2.endsWith('/retry')),
        hasLength(1),
      );
      expect(
        repository.calls.where(
          (call) =>
              call.$1 == 'GET' &&
              call.$2 == '/connections/new/picker/native-picker',
        ),
        hasLength(2),
      );
      await tester.pumpWidget(const SizedBox());
    });
  }

  testWidgets('native Picker selects all 500 returned photos once', (
    tester,
  ) async {
    final repository = ConnectorRepository()..deferNativeSelection = true;
    repository.pickerReplies.add({
      'state': 'selected',
      'items': [
        for (var index = 0; index < 500; index++)
          {
            'id': 'photo-$index',
            'filename': 'photo-$index.jpg',
            'supported': true,
            'source': {
              'provider': 'google_drive',
              'connection_id': 'new',
              'object_id': 'photo-$index',
              'version': '1',
            },
          },
      ],
      'failures': <Json>[],
    });
    await mount(tester, repository, 'google_drive', native: true);
    await press(tester, 'Connect Google Drive');
    await tester.pump(const Duration(seconds: 3));
    await tester.pumpAndSettle();
    expect(find.text('Add 500 photos'), findsOneWidget);
    expect(
      tester
          .widget<UiButton>(find.widgetWithText(UiButton, 'Add 500 photos'))
          .onPressed,
      isNotNull,
    );
    expect(find.byType(UiCheckbox).evaluate().length, lessThan(30));
    expect(repository.calls.any((call) => call.$2.contains('/draft')), isFalse);
    await tester.pumpWidget(const SizedBox());
  });

  for (final durablePicker in [true, false]) {
    testWidgets(
      'explicit retry retains Picker IDs with cached capability $durablePicker',
      (tester) async {
        final repository = ConnectorRepository()..deferNativeSelection = true;
        repository.pickerReplies.addAll([
          {
            'state': 'selecting',
            'items': <Json>[],
            'failures': <Json>[],
            'progress': {'processed': 100, 'total': 500},
            'error': {
              'code': 'selection_retry_exhausted',
              'action': 'retry',
              'message': 'Checking paused. Retry to continue.',
            },
          },
          {
            'state': 'selecting',
            'items': <Json>[],
            'failures': <Json>[],
            'progress': {'processed': 100, 'total': 500},
          },
        ]);
        await mount(
          tester,
          repository,
          'google_drive',
          native: true,
          durablePicker: durablePicker,
        );
        await press(tester, 'Connect Google Drive');
        await tester.pump(const Duration(seconds: 3));
        await tester.pumpAndSettle();
        await press(tester, 'Retry');
        expect(
          repository.calls.where(
            (call) =>
                call.$1 == 'POST' &&
                call.$2 == '/connections/new/picker/native-picker/retry',
          ),
          hasLength(1),
        );
        expect(repository.authorizations, 1);
        expect(find.text('Checking 100 of 500 photos…'), findsOneWidget);
        await tester.pumpWidget(const SizedBox());
      },
    );
  }

  for (final status in [401, 403, 409, 500, null]) {
    testWidgets('retry does not mask a $status failure with a status read', (
      tester,
    ) async {
      final repository = ConnectorRepository()
        ..deferNativeSelection = true
        ..retryFailure = ApiFailure('Retry unavailable.', status: status);
      repository.pickerReplies.add({
        'state': 'selecting',
        'items': <Json>[],
        'failures': <Json>[],
        'progress': {'processed': 1, 'total': 2},
        'error': {'action': 'retry', 'message': 'Please retry.'},
      });
      await mount(tester, repository, 'google_drive', native: true);
      await press(tester, 'Connect Google Drive');
      await tester.pump(const Duration(seconds: 3));
      await tester.pumpAndSettle();
      await press(tester, 'Retry');
      expect(
        repository.calls.where((call) => call.$2.endsWith('/retry')),
        hasLength(1),
      );
      expect(
        repository.calls.where(
          (call) =>
              call.$1 == 'GET' &&
              call.$2 == '/connections/new/picker/native-picker',
        ),
        hasLength(1),
      );
      expect(find.text('Retry unavailable.'), findsOneWidget);
      expect(repository.authorizations, 1);
      await tester.pumpWidget(const SizedBox());
    });
  }

  testWidgets(
    'pasted link reconnects the only expired account with its original identity',
    (tester) async {
      final repository = ConnectorRepository();
      repository.accounts.add({
        ...repository.account('expired', 'google_drive'),
        'state': 'needs_authorization',
        'error': {'message': 'Sign in again.', 'action': 'connect'},
      });
      await mount(tester, repository, 'url');
      await tester.enterText(
        find.byType(EditableText),
        'https://drive.google.com/file/d/photo/view',
      );
      await tester.pumpAndSettle();
      expect(find.text('expired@example.test'), findsOneWidget);
      await press(tester, 'Reconnect Google Drive');
      final create = repository.calls.firstWhere(
        (c) => c.$1 == 'POST' && c.$2 == '/connections',
      );
      expect(create.$3!['reconnect_id'], 'expired');
      expect(create.$3!['access'], 'folders');
      expect(find.text('Google Drive · expired@example.test'), findsOneWidget);
    },
  );

  testWidgets(
    'switching Google selection mode clears folder navigation and retains selections',
    (tester) async {
      final repository = ConnectorRepository()..nestedFolders = true;
      repository.accounts.add(repository.account('saved', 'google_drive'));
      final sessions = await mount(tester, repository, 'google_drive');
      await tester.tap(find.text('photo.jpg'));
      await tester.pumpAndSettle();
      await press(tester, 'Folder');
      expect(find.text('Back to All files'), findsOneWidget);
      expect(find.text('Load more files'), findsOneWidget);
      await openOptions(tester, 'Google Drive');
      await tester.tap(find.text('Choose photos'));
      await tester.pumpAndSettle();
      expect(sessions, isEmpty);
      expect(find.byType(ConnectorFrame), findsOneWidget);
      expect(find.text('Back to All files'), findsNothing);
      expect(find.text('Load more files'), findsNothing);
      expect(find.text('Folder options'), findsNothing);
      await press(tester, 'Back to selected photos');
      expect(find.text('Add 1 photo'), findsOneWidget);
      await openOptions(tester, 'Google Drive');
      await tester.tap(find.text('Browse folders'));
      await tester.pumpAndSettle();
      expect(repository.host.disposedFrames, 1);
      expect(
        repository.calls.any((c) => c.$1 == 'POST' && c.$2 == '/connections'),
        isFalse,
      );
      expect(find.text('Folder options'), findsOneWidget);
      expect(find.text('Add 1 photo'), findsOneWidget);
    },
  );

  testWidgets(
    'new connection has one action and no account-management controls',
    (tester) async {
      await mount(tester, ConnectorRepository(), 'google_drive', scale: 2);
      expect(find.byType(UiButton), findsOneWidget);
      expect(find.text('Connect Google Drive'), findsOneWidget);
      expect(find.byType(UiMenuTrigger), findsNothing);
      expect(find.textContaining('administrator'), findsNothing);
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets(
    'account tools and additional Google access are explicit menu actions',
    (tester) async {
      final repository = ConnectorRepository();
      repository.accounts.add(
        repository.account('saved', 'google_drive', access: 'files'),
      );
      await mount(tester, repository, 'google_drive');
      expect(find.text('Choose photos'), findsOneWidget);
      expect(find.text('Disconnect'), findsNothing);
      expect(find.text('Browse folders'), findsNothing);
      expect(repository.calls.any((c) => c.$1 == 'POST'), isFalse);
      await openOptions(tester, 'Google Drive');
      await tester.tap(find.text('Browse folders'));
      await tester.pumpAndSettle();
      final create = repository.calls.firstWhere(
        (c) => c.$1 == 'POST' && c.$2 == '/connections',
      );
      expect(create.$3!['access'], 'folders');
      expect(find.text('photo.jpg'), findsOneWidget);
      expect(find.text('Include subfolders'), findsNothing);
      await tester.tap(find.text('Folder options'));
      await tester.pumpAndSettle();
      expect(
        tester
            .widget<UiCheckbox>(
              find.widgetWithText(UiCheckbox, 'Include subfolders'),
            )
            .value,
        isFalse,
      );
      expect(find.text('Select folder photos'), findsOneWidget);
    },
  );

  testWidgets(
    'link import only offers the connector required by entered links',
    (tester) async {
      final repository = ConnectorRepository();
      await mount(tester, repository, 'url');
      expect(find.text('Connect Google Drive'), findsNothing);
      expect(find.text('Connect Dropbox'), findsNothing);
      await tester.enterText(
        find.byType(EditableText),
        'https://example.test/photo.jpg',
      );
      await tester.pumpAndSettle();
      expect(find.byType(UiMenuTrigger), findsNothing);
      expect(find.text('Connect Google Drive'), findsNothing);
      await tester.enterText(
        find.byType(EditableText),
        'https://drive.google.com/file/d/photo/view',
      );
      await tester.pumpAndSettle();
      expect(find.text('Connect Google Drive'), findsOneWidget);
      expect(find.text('Connect Dropbox'), findsNothing);
      expect(repository.calls.any((c) => c.$1 == 'POST'), isFalse);
      await tester.enterText(
        find.byType(EditableText),
        'https://www.dropbox.com/s/photo',
      );
      await tester.pumpAndSettle();
      expect(find.text('Connect Google Drive'), findsNothing);
      expect(find.text('Connect Dropbox'), findsOneWidget);
    },
  );

  testWidgets(
    'disconnecting a link account clears its selection without removing the link',
    (tester) async {
      final repository = ConnectorRepository();
      repository.accounts.add(repository.account('saved', 'dropbox'));
      await mount(tester, repository, 'url');
      const url = 'https://www.dropbox.com/s/photo';
      await tester.enterText(find.byType(EditableText), url);
      await tester.pumpAndSettle();
      await openOptions(tester, 'Dropbox');
      await tester.tap(find.text('Disconnect'));
      await tester.pumpAndSettle();
      expect(find.text('Connect Dropbox'), findsOneWidget);
      expect(
        tester.widget<EditableText>(find.byType(EditableText)).controller.text,
        url,
      );
      expect(find.byType(UiSelect<String>), findsNothing);
    },
  );

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
      expect(find.text('Reconnect expired@example.test'), findsNothing);
      await openOptions(tester, 'Google Drive');
      await tester.tap(find.text('Reconnect expired@example.test'));
      await tester.pumpAndSettle();
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
      // A reconnect with an uncertain acknowledgement requires reconciliation;
      // stable connected accounts no longer poll.
      repository.loseCompletionReply = true;
      await openOptions(tester, 'Dropbox');
      await tester.tap(find.text('Use another account'));
      await tester.pumpAndSettle();
      repository.delayedConnection = 'new';
      repository.delayedPoll = Completer<Json>();
      await tester.pump(const Duration(seconds: 3));
      expect(repository.calls.last.$2, '/connections/new');
      await tester.tap(find.text('Choose an account'));
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
      expect(find.text('Copy administrator details'), findsNothing);
      expect(find.text('Import photos from Google Drive.'), findsNothing);
      expect(find.text('Retry connection'), findsOneWidget);
      await tester.tap(find.text('Administrator help'));
      await tester.pumpAndSettle();
      expect(find.text('Copy administrator details'), findsOneWidget);
      expect(find.textContaining('pending'), findsNothing);
      expect(sessions.single.closed, isTrue);
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets('Google consent closes before selection continues inline', (
    tester,
  ) async {
    final repository = ConnectorRepository();
    final sessions = await mount(tester, repository, 'google_drive');
    await press(tester, 'Connect Google Drive');
    expect(find.text('Connected'), findsOneWidget);
    expect(find.text('new@example.test'), findsOneWidget);
    expect(sessions, hasLength(1));
    expect(sessions.single.keepOpen, isFalse);
    expect(sessions.single.pickerUrl, isNull);
    expect(sessions.single.closed, isTrue);
    expect(find.byType(ConnectorFrame), findsOneWidget);
    final create = repository.calls.firstWhere(
      (c) => c.$1 == 'POST' && c.$2 == '/connections',
    );
    expect(create.$3!['access'], 'files');
    expect(repository.calls.any((c) => c.$2.endsWith('/browse')), isFalse);
    await tester.pumpWidget(const SizedBox());
    expect(sessions.single.closed, isTrue);
  });

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
    'native selection keeps polling and displays durable progress until selected',
    (tester) async {
      final repository = ConnectorRepository()..deferNativeSelection = true;
      repository.pickerReplies.addAll([
        {
          'state': 'selecting',
          'items': <Json>[],
          'failures': <Json>[],
          'progress': {'processed': 5, 'total': 500},
        },
        {
          'state': 'selected',
          'items': [
            {
              'id': 'finished-photo',
              'filename': 'finished-photo.jpg',
              'supported': true,
              'source': {
                'provider': 'google_drive',
                'connection_id': 'new',
                'object_id': 'finished-photo',
                'version': '1',
              },
            },
          ],
          'failures': <Json>[],
        },
      ]);
      await mount(tester, repository, 'google_drive', native: true);
      await press(tester, 'Connect Google Drive');
      expect(find.text('Checking 0 of 500 photos…'), findsOneWidget);
      expect(find.text('finished-photo.jpg'), findsNothing);
      await tester.pump(const Duration(seconds: 3));
      await tester.pumpAndSettle();
      expect(find.text('Checking 5 of 500 photos…'), findsOneWidget);
      await tester.pump(const Duration(seconds: 3));
      await tester.pumpAndSettle();
      expect(find.text('finished-photo.jpg'), findsOneWidget);
      expect(find.textContaining('Checking '), findsNothing);
      expect(
        repository.calls.where(
          (call) => call.$2 == '/connections/new/picker/native-picker',
        ),
        hasLength(2),
      );
      expect(
        repository.calls.any(
          (call) => call.$2.contains('/draft') || call.$2.contains('/submit'),
        ),
        isFalse,
      );
      await tester.pumpWidget(const SizedBox());
    },
  );

  for (final (native, lostReply) in [
    (false, false),
    (true, false),
    (true, true),
  ]) {
    testWidgets(
      'same-account reconnect resumes retained selection: native=$native lostReply=$lostReply',
      (tester) async {
        final repository = ConnectorRepository()..deferNativeSelection = true;
        repository.pickerReplies.addAll([
          {
            'state': 'selecting',
            'items': <Json>[],
            'failures': <Json>[],
            'progress': {'processed': 5, 'total': 500},
            'error': {
              'message': 'Reconnect this account to finish checking photos.',
              'action': 'connect',
            },
          },
          {
            'state': 'selected',
            'items': [
              {
                'id': 'retained-photo',
                'filename': 'retained-photo.jpg',
                'supported': true,
              },
            ],
            'failures': <Json>[],
          },
        ]);
        await mount(tester, repository, 'google_drive', native: native);
        await press(tester, 'Connect Google Drive');
        await tester.pump(const Duration(seconds: 3));
        await tester.pumpAndSettle();
        expect(
          find.text('Reconnect this account to finish checking photos.'),
          findsOneWidget,
        );
        repository.deferNativeSelection = false;
        repository.loseCompletionReply = lostReply;
        repository.pickerRepliesById['native-picker-2'] = [
          {'state': 'selected', 'items': <Json>[], 'failures': <Json>[]},
        ];
        await press(tester, 'Retry connection');
        if (lostReply) {
          expect(find.text('retained-photo.jpg'), findsNothing);
          await tester.pump(const Duration(seconds: 3));
          await tester.pumpAndSettle();
        }
        expect(find.text('retained-photo.jpg'), findsOneWidget);
        expect(find.text('native-photo.jpg'), findsNothing);
        final starts = repository.calls
            .where((call) => call.$1 == 'POST' && call.$2 == '/connections')
            .toList();
        expect(starts, hasLength(2));
        expect(starts.last.$3!['reconnect_id'], 'new');
        final originalPicker = native ? 'native-picker' : 'picker';
        expect(
          repository.calls.where(
            (call) => call.$2 == '/connections/new/picker/$originalPicker',
          ),
          hasLength(2),
        );
        expect(
          repository.calls.where(
            (call) => call.$2.endsWith('/picker/native-picker-2'),
          ),
          hasLength(lostReply ? 1 : 0),
        );
        expect(
          repository.calls.where(
            (call) => call.$1 == 'POST' && call.$2.endsWith('/picker'),
          ),
          hasLength(native ? 0 : 1),
        );
        await tester.pumpWidget(const SizedBox());
      },
    );
  }

  testWidgets(
    'recovered OAuth rejection surfaces its reason and stops that picker poll',
    (tester) async {
      final repository = ConnectorRepository()
        ..loseCompletionReply = true
        ..deferNativeSelection = true;
      repository.pickerReplies.add({
        'state': 'failed',
        'items': <Json>[],
        'failures': <Json>[],
        'error': {
          'message': 'The provider did not grant the requested access.',
          'action': 'administrator',
        },
      });
      await mount(tester, repository, 'google_drive', native: true);
      await press(tester, 'Connect Google Drive');
      await tester.pump(const Duration(seconds: 3));
      await tester.pumpAndSettle();
      expect(
        find.text('The provider did not grant the requested access.'),
        findsOneWidget,
      );
      expect(find.text('Administrator help'), findsOneWidget);
      await tester.pump(const Duration(seconds: 6));
      await tester.pumpAndSettle();
      expect(
        repository.calls.where(
          (call) => call.$2 == '/connections/new/picker/native-picker',
        ),
        hasLength(1),
      );
      await tester.pumpWidget(const SizedBox());
    },
  );

  for (final returning in [false, true]) {
    testWidgets(
      'native Google Picker returns provider selection without hosted JS: returning=$returning',
      (tester) async {
        final repository = ConnectorRepository();
        if (returning) {
          repository.accounts.add(
            repository.account('saved', 'google_drive', access: 'files'),
          );
        }
        final sessions = await mount(
          tester,
          repository,
          'google_drive',
          native: true,
        );
        await press(
          tester,
          returning ? 'Choose photos' : 'Connect Google Drive',
        );
        expect(find.text('native-photo.jpg'), findsOneWidget);
        expect(sessions, hasLength(1));
        expect(sessions.single.keepOpen, isFalse);
        expect(sessions.single.pickerUrl, isNull);
        expect(sessions.single.closed, isTrue);
        final start = repository.calls.firstWhere(
          (call) => call.$1 == 'POST' && call.$2 == '/connections',
        );
        expect(start.$3!['return_origin'], isNull);
        expect(start.$3!['access'], 'files');
        expect(start.$3!['reconnect_id'], returning ? 'saved' : null);
        final completion = repository.calls.singleWhere(
          (call) => call.$2 == '/connections/complete',
        );
        expect(completion.$3!['picked_file_ids'], 'native-photo');
        expect(
          repository.calls.any((call) => call.$2.endsWith('/picker')),
          isFalse,
        );
        expect(
          repository.calls.any(
            (call) => call.$2.contains('/draft') || call.$2.contains('/submit'),
          ),
          isFalse,
        );
      },
    );
  }

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
      await tester.tap(find.text('Administrator help'));
      await tester.pumpAndSettle();
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
    'Picker failure keeps consent closed and Retry uses the connected account inline',
    (tester) async {
      final repository = ConnectorRepository()..failPicker = true;
      final sessions = await mount(tester, repository, 'google_drive');
      await press(tester, 'Connect Google Drive');
      expect(sessions.single.closed, isTrue);
      expect(find.text('Connected'), findsOneWidget);
      repository.failPicker = false;
      await press(tester, 'Retry');
      expect(sessions, hasLength(1));
      expect(find.byType(ConnectorFrame), findsOneWidget);
      expect(
        repository.calls.where((c) => c.$1 == 'POST' && c.$2 == '/connections'),
        hasLength(1),
      );
    },
  );
}
