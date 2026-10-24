import 'dart:async';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/models.dart';
import 'intake_connector_test.dart'
    show ConnectorRepository, ConnectorSession, mount, press;

class DelayedConsent extends ConnectorSession {
  DelayedConsent() : super(native: true);
  final result = Completer<Json>();
  @override
  Future<Json> authenticate(String url, {bool keepOpen = false}) =>
      result.future;
}

class CancelledConsent extends ConnectorSession {
  CancelledConsent() : super(native: true);
  @override
  Future<Json> authenticate(String url, {bool keepOpen = false}) async =>
      throw const ApiFailure('Cancelled', code: 'authorization_cancelled');
}

void main() {
  testWidgets('source switch closes consent and rejects its late completion', (
    tester,
  ) async {
    final repository = ConnectorRepository();
    final active = ValueNotifier(true);
    addTearDown(active.dispose);
    final consent = DelayedConsent();
    await mount(
      tester,
      repository,
      'google_drive',
      native: true,
      active: active,
      sessionFactory: () => consent,
    );
    await tester.tap(find.text('Connect Google Drive'));
    await tester.pump();
    expect(repository.authorizations, 1);
    active.value = false;
    await tester.pump();
    expect(consent.closed, isTrue);
    consent.result.complete({'state': 'late', 'code': 'late'});
    await tester.pumpAndSettle();
    expect(
      repository.calls.where((call) => call.$2 == '/connections/complete'),
      isEmpty,
    );
    expect(tester.takeException(), isNull);
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets(
    'native dismissal keeps photos and reconciles account permission',
    (tester) async {
      final repository = ConnectorRepository()
        ..persistAuthorizationState = true;
      var attempt = 0;
      await mount(
        tester,
        repository,
        'google_drive',
        native: true,
        sessionFactory: () => ++attempt == 1
            ? ConnectorSession(native: true)
            : CancelledConsent(),
      );
      await press(tester, 'Connect Google Drive');
      expect(find.text('native-photo.jpg'), findsOneWidget);
      await press(tester, 'Choose photos');
      expect(find.text('native-photo.jpg'), findsOneWidget);
      expect(find.text('Add 1 photo'), findsOneWidget);
      expect(find.text('Connected'), findsNothing);
      expect(find.text('Retry connection'), findsOneWidget);
      expect(find.text('Cancelled'), findsNothing);
      expect(
        repository.calls.where((call) => call.$2 == '/connections/complete'),
        hasLength(1),
      );
      expect(
        repository.calls.where((call) => call.$2 == '/connections/new'),
        isNotEmpty,
      );
      await tester.pumpWidget(const SizedBox());
    },
  );

  testWidgets(
    'visible inactive selection reconciles; hidden waits for resume',
    (tester) async {
      final repository = ConnectorRepository()..deferNativeSelection = true;
      await mount(tester, repository, 'google_drive', native: true);
      await press(tester, 'Connect Google Drive');
      expect(find.text('Checking 0 of 500 photos…'), findsOneWidget);
      int reads() => repository.calls
          .where((call) => call.$1 == 'GET' && call.$2.contains('/picker/'))
          .length;
      final before = reads();
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.inactive);
      await tester.pump(const Duration(seconds: 3));
      expect(reads(), greaterThan(before));
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.hidden);
      await tester.pump();
      final hiddenReads = reads();
      await tester.pump(const Duration(seconds: 9));
      expect(reads(), hiddenReads);
      repository.pickerReplies.add({
        'state': 'selected',
        'items': [
          {
            'id': 'finished',
            'filename': 'finished.jpg',
            'supported': true,
            'source': {
              'provider': 'google_drive',
              'connection_id': 'new',
              'object_id': 'finished',
            },
          },
        ],
        'failures': <Json>[],
      });
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
      await tester.pumpAndSettle();
      expect(find.text('finished.jpg'), findsOneWidget);
      expect(find.text('Checking 0 of 500 photos…'), findsNothing);
      await tester.pumpWidget(const SizedBox());
    },
  );
}
