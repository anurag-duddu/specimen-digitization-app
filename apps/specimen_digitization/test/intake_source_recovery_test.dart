// Controlled transport/OAuth regressions; these do not establish provider acceptance.
import 'dart:async';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/screens/intake/bulk_intake_controller.dart';
import 'package:specimen_digitization/src/screens/intake/bulk_intake_repository.dart';
import 'package:specimen_digitization/src/screens/intake/intake_source_picker.dart';
import 'package:specimen_digitization/src/theme/app_theme.dart';
import 'package:specimen_ui/specimen_ui.dart';

import 'intake_connector_test.dart'
    show ConnectorRepository, ConnectorSession, press;
import 'ui_finders.dart';

const _scope = CollectionScope(
  organizationId: 'org',
  collectionId: 'collection',
  name: 'Collection',
);
const _keep = 'https://images.example/keep.jpg';
const _omit = 'https://images.example/omit.jpg';
const _retry = 'https://images.example/retry.jpg';

class _RecoveryRepository extends ConnectorRepository {
  final locations = <Json>[
    {'id': 'archive', 'label': 'Archive photos'},
    {'id': 'working', 'label': 'Working photos'},
  ];
  final resolveCounts = <String, int>{};
  final versions = <String, String>{};

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
    if (path == '/sources') {
      calls.add((method, path, body));
      return {'items': locations.map(Map<String, dynamic>.of).toList()};
    }
    if (path.startsWith('/sources/') && path.endsWith('/browse')) {
      calls.add((method, path, body));
      final id = path.split('/')[2];
      if (!locations.any((row) => row['id'] == id)) {
        throw StateError('A removed storage location must not be browsed');
      }
      return {
        'items': [
          {
            'id': '$id/photo.jpg',
            'filename': '$id-photo.jpg',
            'kind': 'file',
            'media_type': 'image/jpeg',
            'supported': true,
            'source': {
              'provider': 'storage',
              'source_id': id,
              'object_id': '$id/photo.jpg',
              'version': versions[id] ?? '1',
            },
          },
        ],
      };
    }
    if (path == '/resolve') {
      calls.add((method, path, body));
      final url = body!['url'] as String;
      final count = resolveCounts.update(url, (n) => n + 1, ifAbsent: () => 1);
      if (url == _retry && count == 1) {
        throw const ApiFailure(
          'The source is temporarily unavailable.',
          code: 'provider_unavailable',
          details: {'action': 'retry', 'retryable': true},
        );
      }
      final drive = Uri.parse(url).host == 'drive.google.com';
      final account = body['connection_id'];
      return {
        'items': [
          {
            'id': drive ? 'shared-object' : url,
            'filename': drive
                ? 'shared-$account.jpg'
                : Uri.parse(url).pathSegments.last,
            'kind': 'file',
            'supported': true,
            'media_type': 'image/jpeg',
            'source': drive
                ? {
                    'provider': 'google_drive',
                    'connection_id': account,
                    'object_id': 'shared-object',
                    'version': '1',
                  }
                : {'provider': 'url', 'url': url},
          },
        ],
      };
    }
    return super.intakeRequest(
      scope,
      method,
      path,
      body: body,
      query: query,
      bytes: bytes,
      offset: offset,
    );
  }
}

class _PartialAdmissionController extends BulkIntakeController {
  _PartialAdmissionController(_RecoveryRepository repository)
    : super(repository: repository, scope: _scope, userId: 'owner');

  final attempts = <List<Json>>[];

  @override
  Future<void> addSource(List<Json> photos) async {
    attempts.add(photos.map(Map<String, dynamic>.of).toList());
    if (attempts.length == 1) {
      // One acknowledged row, followed by an uncertain remainder. The source
      // UI must preserve that row's immutable admission identity for a retry.
      items.add(
        IntakeDraftItem({
          ...photos.first,
          'id': 'acknowledged-photo',
          'state': 'ready',
          'included': true,
        }),
      );
    }
    error = 'Some photos are still waiting to be added.';
    changed();
  }
}

Future<void> _mount(
  WidgetTester tester,
  BulkIntakeController controller,
  String provider,
) async {
  await tester.pumpWidget(
    MaterialApp(
      theme: AppTheme.light(),
      home: Scaffold(
        body: IntakeSourcePicker(
          controller: controller,
          provider: provider,
          authSessionFactory: ConnectorSession.new,
        ),
      ),
    ),
  );
  await tester.pumpAndSettle();
  expect(tester.takeException(), isNull);
}

void _cleanup(WidgetTester tester, BulkIntakeController controller) {
  tester.view.physicalSize = const Size(1100, 1100);
  tester.view.devicePixelRatio = 1;
  addTearDown(() async {
    await tester.pumpWidget(const SizedBox.shrink());
    controller.dispose();
    tester.view.reset();
  });
}

Future<void> _links(WidgetTester tester, String values) async {
  await tester.enterText(
    find.descendant(
      of: uiField('Photo or folder links'),
      matching: find.byType(EditableText),
    ),
    values,
  );
  await tester.pumpAndSettle();
}

bool? _selected(WidgetTester tester, String name) =>
    tester.widget<UiCheckbox>(find.widgetWithText(UiCheckbox, name)).value;

void main() {
  testWidgets('registered storage can switch between two locations', (
    tester,
  ) async {
    final repository = _RecoveryRepository();
    final controller = BulkIntakeController(
      repository: repository,
      scope: _scope,
      userId: 'owner',
    );
    _cleanup(tester, controller);
    await _mount(tester, controller, 'storage');
    await pickUiSelect(tester, 'Storage location', 'Archive photos');
    expect(find.text('archive-photo.jpg'), findsOneWidget);
    await pickUiSelect(tester, 'Storage location', 'Working photos');
    expect(find.text('working-photo.jpg'), findsOneWidget);
    expect(find.text('archive-photo.jpg'), findsNothing);
    expect(
      repository.calls
          .where((row) => row.$2.endsWith('/browse'))
          .map((row) => row.$2),
      ['/sources/archive/browse', '/sources/working/browse'],
    );
  });

  testWidgets('a removed remembered storage location is cleared on reopen', (
    tester,
  ) async {
    final repository = _RecoveryRepository();
    final controller = BulkIntakeController(
      repository: repository,
      scope: _scope,
      userId: 'owner',
    );
    _cleanup(tester, controller);
    await _mount(tester, controller, 'storage');
    await pickUiSelect(tester, 'Storage location', 'Archive photos');
    await tester.pumpWidget(const SizedBox.shrink());
    repository.locations.removeWhere((row) => row['id'] == 'archive');
    final reads = repository.calls
        .where((row) => row.$2.endsWith('/browse'))
        .length;
    await _mount(tester, controller, 'storage');
    expect(
      tester.widget<UiSelect<String>>(uiSelect('Storage location')).value,
      isNull,
    );
    expect(find.text('archive-photo.jpg'), findsNothing);
    expect(
      repository.calls.where((row) => row.$2.endsWith('/browse')),
      hasLength(reads),
    );
    await pickUiSelect(tester, 'Storage location', 'Working photos');
    expect(find.text('working-photo.jpg'), findsOneWidget);
  });

  testWidgets(
    'retrying one link preserves successful identities and deselection',
    (tester) async {
      final repository = _RecoveryRepository();
      final controller = _PartialAdmissionController(repository);
      _cleanup(tester, controller);
      await _mount(tester, controller, 'url');
      await _links(tester, '$_keep\n$_omit\n$_retry');
      await press(tester, 'Review links');
      await tester.tap(find.widgetWithText(UiCheckbox, 'omit.jpg'));
      await tester.pumpAndSettle();
      expect(_selected(tester, 'omit.jpg'), isFalse);
      await press(tester, 'Add 1 photo');
      final clientId = controller.attempts.single.single['client_id'];
      expect(clientId, isA<String>());
      await press(tester, 'Retry');
      expect(repository.resolveCounts, {_keep: 1, _omit: 1, _retry: 2});
      expect(_selected(tester, 'keep.jpg'), isTrue);
      expect(_selected(tester, 'omit.jpg'), isFalse);
      expect(_selected(tester, 'retry.jpg'), isTrue);
      await press(tester, 'Add 2 photos');
      final retry = controller.attempts.last;
      expect(retry.map((row) => row['filename']), ['keep.jpg', 'retry.jpg']);
      expect(retry.first['client_id'], clientId);
      expect(retry.last['client_id'], isNot(clientId));
    },
  );

  testWidgets('reviewing changed link input removes prior selected URLs', (
    tester,
  ) async {
    final repository = _RecoveryRepository();
    final controller = _PartialAdmissionController(repository);
    _cleanup(tester, controller);
    await _mount(tester, controller, 'url');
    await _links(tester, _keep);
    await press(tester, 'Review links');
    await press(tester, 'Add 1 photo');
    await _links(tester, _omit);
    await press(tester, 'Review links');
    expect(find.text('keep.jpg'), findsNothing);
    expect(_selected(tester, 'omit.jpg'), isTrue);
    await press(tester, 'Add 1 photo');
    expect(controller.attempts.last.single['source'], {
      'provider': 'url',
      'url': _omit,
    });
    expect(
      controller.attempts.last.single['client_id'],
      isNot(controller.attempts.first.single['client_id']),
    );
  });

  testWidgets('changing link account replaces the prior account selection', (
    tester,
  ) async {
    final repository = _RecoveryRepository();
    repository.accounts.addAll([
      repository.account('first', 'google_drive'),
      repository.account('second', 'google_drive'),
    ]);
    final controller = _PartialAdmissionController(repository);
    _cleanup(tester, controller);
    await _mount(tester, controller, 'url');
    await _links(tester, 'https://drive.google.com/file/d/shared-object/view');
    await pickUiSelect(tester, 'Google Drive account', 'first@example.test');
    await press(tester, 'Review links');
    await press(tester, 'Add 1 photo');
    await pickUiSelect(tester, 'Google Drive account', 'second@example.test');
    await press(tester, 'Review links');
    expect(find.text('shared-first.jpg'), findsNothing);
    expect(_selected(tester, 'shared-second.jpg'), isTrue);
    await press(tester, 'Add 1 photo');
    final source = controller.attempts.last.single['source'] as Map;
    expect(source['connection_id'], 'second');
    expect(
      controller.attempts.last.single['client_id'],
      isNot(controller.attempts.first.single['client_id']),
    );
  });

  for (final changedVersion in [false, true]) {
    testWidgets(
      'reselected source identity follows its exact version: changed=$changedVersion',
      (tester) async {
        final repository = _RecoveryRepository();
        final controller = _PartialAdmissionController(repository);
        _cleanup(tester, controller);
        await _mount(tester, controller, 'storage');
        await pickUiSelect(tester, 'Storage location', 'Archive photos');
        await press(tester, 'Select visible photos');
        await press(tester, 'Add 1 photo');
        final firstId = controller.attempts.single.single['client_id'];
        await pickUiSelect(tester, 'Storage location', 'Working photos');
        if (changedVersion) repository.versions['archive'] = '2';
        await pickUiSelect(tester, 'Storage location', 'Archive photos');
        await press(tester, 'Select visible photos');
        await press(tester, 'Add 1 photo');
        final retry = controller.attempts.last.single;
        expect(retry['client_id'], changedVersion ? isNot(firstId) : firstId);
        expect((retry['source'] as Map)['version'], changedVersion ? '2' : '1');
      },
    );
  }

  testWidgets('a delayed same-ID poll cannot overwrite successful reconnect', (
    tester,
  ) async {
    final repository = _RecoveryRepository();
    final expired = {
      ...repository.account('first', 'dropbox'),
      'state': 'needs_authorization',
      'error': {'message': 'Old authorization state.', 'action': 'connect'},
    };
    repository.accounts.add(expired);
    final controller = BulkIntakeController(
      repository: repository,
      scope: _scope,
      userId: 'owner',
    );
    _cleanup(tester, controller);
    await _mount(tester, controller, 'dropbox');
    repository.delayedConnection = 'first';
    repository.delayedPoll = Completer<Json>();
    await tester.pump(const Duration(seconds: 3));
    await tester.pump();
    expect(
      repository.calls.where(
        (row) => row.$1 == 'GET' && row.$2 == '/connections/first',
      ),
      hasLength(1),
    );
    await press(tester, 'Retry connection');
    expect(find.text('Connected'), findsOneWidget);
    expect(repository.authorizations, 1);
    repository.delayedPoll!.complete(expired);
    await tester.pumpAndSettle();
    expect(find.text('Connected'), findsOneWidget);
    expect(find.text('Old authorization state.'), findsNothing);
    expect(find.text('Retry connection'), findsNothing);
    expect(repository.authorizations, 1);
  });
}
