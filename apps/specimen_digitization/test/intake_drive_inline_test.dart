import 'dart:async';
import 'dart:typed_data';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/screens/intake/bulk_intake_controller.dart';
import 'package:specimen_digitization/src/screens/intake/intake_source_picker.dart';
import 'package:specimen_digitization/src/theme/app_theme.dart';
import 'package:specimen_ui/specimen_ui.dart';
import 'intake_connector_test.dart'
    show ConnectorRepository, ConnectorPickerHost, ConnectorFrame, mount, press;

class InlineRepository extends ConnectorRepository {
  String? returnedUrl;
  Completer<Json>? cancelGate;
  bool failCancel = false, failStatus = false;
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
    if (path.endsWith('/cancel') && (cancelGate != null || failCancel)) {
      calls.add((method, path, body));
      if (failCancel) throw const ApiFailure('Offline', status: 503);
      return cancelGate!.future;
    }
    if (method == 'GET' && path.contains('/picker/') && failStatus) {
      calls.add((method, path, body));
      throw const ApiFailure('Offline', status: 503);
    }
    final reply = await super.intakeRequest(
      scope,
      method,
      path,
      body: body,
      query: query,
      bytes: bytes,
      offset: offset,
    );
    return path.endsWith('/picker') && method == 'POST' && returnedUrl != null
        ? {...reply, 'url': returnedUrl}
        : reply;
  }
}

Json selectedPhoto(String id) => {
  'id': id,
  'filename': '$id.jpg',
  'supported': true,
  'source': {
    'provider': 'google_drive',
    'connection_id': 'saved',
    'object_id': id,
    'version': '1',
  },
};
Json selectedReply(String id) => {
  'state': 'selected',
  'items': [selectedPhoto(id)],
  'failures': <Json>[],
};
int starts(ConnectorRepository repository) => repository.calls
    .where((call) => call.$1 == 'POST' && call.$2.endsWith('/picker'))
    .length;

void main() {
  InlineRepository connected() => InlineRepository()
    ..accounts.add({
      'id': 'saved',
      'provider': 'google_drive',
      'access': 'files',
      'state': 'connected',
      'account_id': 'drive-owner',
      'account_label': 'owner@example.test',
    });
  testWidgets(
    'connected web selection constructs no OAuth popup and uses only the API wrapper',
    (tester) async {
      final repository = connected();
      final sessions = await mount(tester, repository, 'google_drive');
      await press(tester, 'Choose photos');
      expect(sessions, isEmpty);
      expect(find.byType(ConnectorFrame), findsOneWidget);
      final start = repository.calls.singleWhere(
        (call) => call.$2.endsWith('/picker'),
      );
      expect(start.$3, {'return_origin': 'https://app.example'});
      final wrapper = Uri.parse(repository.host.frames.single.url);
      expect(wrapper.origin, 'https://api.example');
      expect(wrapper.path, '/v1/intake/picker');
      expect(wrapper.queryParameters, {
        'embed_origin': 'https://app.example',
        'picker_id': 'picker',
      });
      expect(
        repository.calls.any(
          (call) => call.$2.contains('/draft') || call.$2.contains('/submit'),
        ),
        isFalse,
      );
      await tester.pumpWidget(const SizedBox());
      expect(repository.host.disposedFrames, 1);
    },
  );
  testWidgets('authoritative selection is retained through cancel and reopen', (
    tester,
  ) async {
    final repository = connected();
    final sessions = await mount(tester, repository, 'google_drive');
    await press(tester, 'Choose photos');
    repository.pickerReplies.add(selectedReply('earlier'));
    repository.host.frames.last.onEvent('selected');
    await tester.pumpAndSettle();
    expect(find.text('Add 1 photo'), findsOneWidget);
    await press(tester, 'Choose photos');
    expect(find.byType(ConnectorFrame), findsOneWidget);
    await press(tester, 'Back to selected photos');
    expect(find.text('earlier.jpg'), findsOneWidget);
    expect(find.text('Add 1 photo'), findsOneWidget);
    expect(sessions, isEmpty);
    expect(repository.host.disposedFrames, 2);
    await press(tester, 'Choose photos');
    expect(repository.host.frames, hasLength(3));
    await tester.pumpWidget(const SizedBox());
  });
  testWidgets(
    'delayed cancel restores focus after Choose photos becomes enabled at200percent',
    (tester) async {
      final repository = connected()..cancelGate = Completer<Json>();
      await mount(tester, repository, 'google_drive', scale: 2);
      await press(tester, 'Choose photos');
      final cancel = find.widgetWithText(UiButton, 'Cancel choosing photos');
      expect(cancel, findsOneWidget);
      await tester.ensureVisible(cancel);
      await tester.tap(cancel);
      await tester.pump();
      var choose = tester.widget<UiButton>(
        find.widgetWithText(UiButton, 'Choose photos'),
      );
      expect(choose.onPressed, isNull);
      expect(choose.focusNode!.hasFocus, isFalse);
      repository.cancelGate!.complete({'state': 'cancelled'});
      await tester.pumpAndSettle();
      choose = tester.widget<UiButton>(
        find.widgetWithText(UiButton, 'Choose photos'),
      );
      expect(choose.onPressed, isNotNull);
      expect(choose.focusNode!.hasFocus, isTrue);
      expect(find.byType(ConnectorFrame), findsNothing);
      expect(tester.takeException(), isNull);
      await tester.pumpWidget(const SizedBox());
    },
  );
  for (final state in ['selected', 'cancelled', 'expired', 'failed']) {
    testWidgets(
      '$state status before its iframe message detaches and restores focus',
      (tester) async {
        final repository = connected();
        await mount(tester, repository, 'google_drive');
        await press(tester, 'Choose photos');
        final oldFrame = repository.host.frames.last;
        repository.pickerReplies.add(
          state == 'selected'
              ? selectedReply('polled')
              : {
                  'state': state,
                  if (state == 'failed')
                    'error': {
                      'code': 'picker_failed',
                      'action': 'choose_source',
                      'retryable': true,
                      'message':
                          'Drive file selection could not finish. Choose photos again.',
                    },
                },
        );
        await tester.pump(const Duration(seconds: 3));
        await tester.pumpAndSettle();
        final choose = tester.widget<UiButton>(
          find.widgetWithText(UiButton, 'Choose photos'),
        );
        expect(choose.onPressed, isNotNull);
        expect(choose.focusNode!.hasFocus, isTrue);
        expect(
          find.text('polled.jpg'),
          state == 'selected' ? findsOneWidget : findsNothing,
        );
        expect(repository.host.disposedFrames, 1);
        final reads = repository.calls.length;
        oldFrame.onEvent(
          state == 'failed' || state == 'expired' ? 'error' : state,
        );
        await tester.pump(const Duration(seconds: 6));
        expect(repository.calls.length, reads);
        await tester.pumpWidget(const SizedBox());
      },
    );
  }
  for (final state in ['pending', 'selecting']) {
    testWidgets(
      '$state status keeps the chooser or durable progress until authoritative selection',
      (tester) async {
        final repository = connected();
        await mount(tester, repository, 'google_drive');
        await press(tester, 'Choose photos');
        repository.pickerReplies.add({
          'state': state,
          if (state == 'selecting') 'progress': {'processed': 1, 'total': 2},
        });
        await tester.pump(const Duration(seconds: 3));
        await tester.pumpAndSettle();
        expect(
          find.byType(ConnectorFrame),
          state == 'pending' ? findsOneWidget : findsNothing,
        );
        expect(repository.host.disposedFrames, state == 'pending' ? 0 : 1);
        if (state == 'selecting') {
          final choose = tester.widget<UiButton>(
            find.widgetWithText(UiButton, 'Choose photos'),
          );
          expect(choose.focusNode!.hasFocus, isTrue);
        }
        expect(
          find.text('Checking 1 of 2 photos…'),
          state == 'selecting' ? findsOneWidget : findsNothing,
        );
        repository.pickerReplies.add(selectedReply('completed'));
        await tester.pump(const Duration(seconds: 3));
        await tester.pumpAndSettle();
        expect(find.text('completed.jpg'), findsOneWidget);
        expect(repository.host.disposedFrames, 1);
        expect(starts(repository), 1);
        await tester.pumpWidget(const SizedBox());
      },
    );
  }
  for (final event in ['cancelled', 'error', 'timeout']) {
    testWidgets(
      '$event reconciles a committed selection instead of discarding its IDs',
      (tester) async {
        final repository = connected();
        await mount(tester, repository, 'google_drive');
        await press(tester, 'Choose photos');
        repository.cancelReplies.add({
          'state': 'selecting',
          'progress': {'processed': 1, 'total': 2},
        });
        final frame = repository.host.frames.last;
        event == 'timeout'
            ? frame.onFailure('Drive selection expired. Choose photos again.')
            : frame.onEvent(event);
        await tester.pumpAndSettle();
        expect(find.byType(ConnectorFrame), findsNothing);
        expect(find.text('Checking 1 of 2 photos…'), findsOneWidget);
        repository.pickerReplies.add(selectedReply('recovered'));
        await tester.pump(const Duration(seconds: 3));
        await tester.pumpAndSettle();
        expect(find.text('recovered.jpg'), findsOneWidget);
        expect(find.text('Add 1 photo'), findsOneWidget);
        expect(starts(repository), 1);
        await tester.pumpWidget(const SizedBox());
      },
    );
  }
  testWidgets(
    'uncertain cancel keeps its handle and prevents speculative new Picker',
    (tester) async {
      final repository = connected();
      final sessions = await mount(tester, repository, 'google_drive');
      await press(tester, 'Choose photos');
      repository.failCancel = true;
      repository.failStatus = true;
      repository.host.frames.last.onEvent('error');
      await tester.pumpAndSettle();
      expect(find.byType(ConnectorFrame), findsNothing);
      expect(starts(repository), 1);
      await press(tester, 'Choose photos');
      expect(starts(repository), 1);
      repository.failCancel = false;
      repository.failStatus = false;
      repository.cancelReplies.add(selectedReply('saved-before-error'));
      await press(tester, 'Retry');
      expect(find.text('saved-before-error.jpg'), findsOneWidget);
      expect(starts(repository), 1);
      expect(sessions, isEmpty);
      await tester.pumpWidget(const SizedBox());
    },
  );
  testWidgets(
    'selected notification alone never supplies accepted photo rows',
    (tester) async {
      final repository = connected();
      await mount(tester, repository, 'google_drive');
      await press(tester, 'Choose photos');
      repository.host.frames.last.onEvent('selected');
      await tester.pumpAndSettle();
      expect(find.textContaining('Add 1 photo'), findsNothing);
      expect(find.textContaining('Could not confirm'), findsOneWidget);
      repository.pickerReplies.add(selectedReply('verified'));
      await press(tester, 'Retry');
      expect(find.text('verified.jpg'), findsOneWidget);
      expect(find.text('Add 1 photo'), findsOneWidget);
      await tester.pumpWidget(const SizedBox());
    },
  );
  for (final disposeSource in [false, true]) {
    testWidgets(
      '${disposeSource ? 'disposed' : 'inactive retained'} source detaches without stealing focus and rejects queued events',
      (tester) async {
        final repository = connected();
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
        repository.host = ConnectorPickerHost();
        final active = ValueNotifier(true), outsideFocus = FocusNode();
        addTearDown(active.dispose);
        addTearDown(outsideFocus.dispose);
        await tester.pumpWidget(
          MaterialApp(
            theme: AppTheme.light(),
            home: Scaffold(
              body: Column(
                children: [
                  UiButton(
                    label: 'Outside source',
                    focusNode: outsideFocus,
                    onPressed: () {},
                  ),
                  Expanded(
                    child: ValueListenableBuilder<bool>(
                      valueListenable: active,
                      builder: (_, visible, _) => !visible && disposeSource
                          ? const SizedBox.shrink()
                          : IntakeSourcePicker(
                              controller: controller,
                              provider: 'google_drive',
                              active: visible,
                              pickerHost: repository.host,
                              authSessionFactory: () => throw StateError(
                                'Connected selection must not open OAuth',
                              ),
                            ),
                    ),
                  ),
                ],
              ),
            ),
          ),
        );
        await tester.pumpAndSettle();
        await press(tester, 'Choose photos');
        final oldFrame = repository.host.frames.last;
        outsideFocus.requestFocus();
        await tester.pump();
        active.value = false;
        await tester.pumpAndSettle();
        expect(repository.host.disposedFrames, 1);
        expect(outsideFocus.hasFocus, isTrue);
        final before = repository.calls.length;
        oldFrame.onEvent('selected');
        oldFrame.onFailure('Stale load error');
        await tester.pump(const Duration(seconds: 6));
        expect(repository.calls.length, before);
        expect(outsideFocus.hasFocus, isTrue);
        repository.pickerReplies.add({'state': 'cancelled'});
        active.value = true;
        await tester.pumpAndSettle();
        await press(tester, 'Choose photos');
        expect(repository.host.frames, hasLength(2));
        oldFrame.onEvent('cancelled');
        await tester.pumpAndSettle();
        expect(find.byType(ConnectorFrame), findsOneWidget);
        await tester.pumpWidget(const SizedBox());
      },
    );
  }
  for (final url in [
    'https://api.example/v1/intake/picker#state=legacy',
    'https://api.example/v1/intake/picker?embed_origin=https%3A%2F%2Fwrong.example&picker_id=picker',
    'https://api.example/v1/intake/picker?embed_origin=https%3A%2F%2Fapp.example&picker_id=old',
    'https://api.example/wrong?embed_origin=https%3A%2F%2Fapp.example&picker_id=picker',
    'http://api.example/v1/intake/picker?embed_origin=https%3A%2F%2Fapp.example&picker_id=picker',
    'javascript:alert(1)',
  ]) {
    testWidgets('old or invalid embed URL fails in workspace: $url', (
      tester,
    ) async {
      final repository = connected()..returnedUrl = url;
      final sessions = await mount(tester, repository, 'google_drive');
      await press(tester, 'Choose photos');
      expect(find.byType(ConnectorFrame), findsNothing);
      expect(
        find.text('Drive selection is being updated. Try again shortly.'),
        findsOneWidget,
      );
      expect(find.text('Retry'), findsOneWidget);
      expect(sessions, isEmpty);
      expect(repository.host.frames, isEmpty);
      await tester.pumpWidget(const SizedBox());
    });
  }
}
