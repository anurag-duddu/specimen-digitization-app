// Finders and actions shared by the intake tests.
//
// The intake screen decodes real image bytes when a file is chosen, which
// only happens under `tester.runAsync`. Every test needs the same "press the
// button, wait for the decode to finish" dance, so it lives here once.

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';

/// The file picker button.
final Finder chooseFilesButton = find.byKey(
  const ValueKey<String>('intake-choose-files'),
);

/// The camera button. Absent on web and desktop.
final Finder takePhotographButton = find.byKey(
  const ValueKey<String>('intake-take-photograph'),
);

/// The button that starts a batch.
final Finder uploadButton = find.byKey(const ValueKey<String>('intake-upload'));

/// The one per-batch confirmation.
final Finder confirmCheckbox = find.byKey(
  const ValueKey<String>('intake-confirm'),
);

/// The manifest header's Stop action. Present only while a batch is running.
final Finder stopButton = find.byKey(const ValueKey<String>('intake-stop'));

/// The sensitivity checkbox for new photographs.
final Finder sensitivityControl = find.byKey(
  const ValueKey<String>('intake-sensitivity'),
);

/// True when the button [finder] names is pressable.
bool buttonEnabled(WidgetTester tester, Finder finder) =>
    tester.widget<UiButton>(finder).onPressed != null;

/// True when the per-batch confirmation is ticked.
bool batchConfirmed(WidgetTester tester) =>
    tester.widget<UiCheckbox>(confirmCheckbox).value ?? false;

/// Selects the classification for new files using the actual checkbox.
/// Existing and retried uploads keep their original classification.
Future<void> selectSensitivity(WidgetTester tester, String label) async {
  final bool wanted = switch (label) {
    'Sensitive' => true,
    'Not sensitive' => false,
    _ => throw ArgumentError.value(label, 'label', 'Unknown classification'),
  };
  expect(sensitivityControl, findsOneWidget);
  await tester.ensureVisible(sensitivityControl);
  await tester.pumpAndSettle();
  final UiCheckbox checkbox = tester.widget<UiCheckbox>(sensitivityControl);
  expect(checkbox.onChanged, isNotNull);
  expect(checkbox.value, isNotNull);
  if (checkbox.value != wanted) {
    expect(sensitivityControl.hitTestable(), findsOneWidget);
    await tester.tap(sensitivityControl);
    await tester.pumpAndSettle();
  }
  expect(tester.widget<UiCheckbox>(sensitivityControl).value, wanted);
}

/// Presses the file picker and waits for every chosen file to be read,
/// hashed and measured.
Future<void> chooseFiles(WidgetTester tester) async {
  await tester.ensureVisible(chooseFilesButton);
  await tester.pumpAndSettle();
  await tester.runAsync(() async {
    await tester.tap(chooseFilesButton);
    var finished = false;
    for (var attempt = 0; attempt < 200; attempt++) {
      await Future<void>.delayed(const Duration(milliseconds: 25));
      await tester.pump();
      if (buttonEnabled(tester, chooseFilesButton)) {
        finished = true;
        break;
      }
    }
    expect(
      finished,
      isTrue,
      reason: 'source inspection must finish before an upload can start',
    );
  });
  await tester.pumpAndSettle();
}

/// Ticks the per-batch confirmation.
Future<void> confirmBatch(WidgetTester tester) async {
  await tester.ensureVisible(confirmCheckbox);
  await tester.pumpAndSettle();
  await tester.tap(confirmCheckbox);
  await tester.pumpAndSettle();
}

/// Presses the upload button.
Future<void> pressUpload(WidgetTester tester) async {
  await tester.ensureVisible(uploadButton);
  await tester.pumpAndSettle();
  await tester.tap(uploadButton);
  await tester.pumpAndSettle();
}

/// Starts the batch through its explicit current upload action.
/// Removed per-batch confirmation tests still use confirmBatch and fail visibly;
/// this action never invents a confirmation state.
Future<void> submitBatch(WidgetTester tester) => pressUpload(tester);
