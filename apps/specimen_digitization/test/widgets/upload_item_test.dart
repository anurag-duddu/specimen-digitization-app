// The intake item: measurements, a state chip, a reason, a way out.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/widgets/status_chip.dart';
import 'package:specimen_digitization/src/widgets/upload_item.dart';

import 'harness.dart';

Widget _item({
  UploadState state = UploadState.ready,
  double? progress,
  String? reason,
  VoidCallback? onRemove,
  String? removeBlockedReason,
  Widget? details,
}) => SizedBox(
  width: 600,
  child: UploadItem(
    name: 'IMG_4821.jpg',
    state: state,
    sizeBytes: 4200000,
    pixelWidth: 6000,
    pixelHeight: 4000,
    progress: progress,
    reason: reason,
    onRemove: onRemove,
    removeBlockedReason: removeBlockedReason,
    details: details,
  ),
);

void main() {
  test('measurements name what was not measured', () {
    expect(
      UploadItem.measurements(sizeBytes: 4200000, width: 6000, height: 4000),
      '4.2 MB, 6000 by 4000 pixels',
    );
    expect(
      UploadItem.measurements(),
      'Size not measured, Dimensions not measured',
    );
    expect(
      UploadItem.measurements(sizeBytes: 4200000),
      '4.2 MB, Dimensions not measured',
    );
  });

  testWidgets('renders the name, the measurements and the state chip', (
    WidgetTester tester,
  ) async {
    await pumpComponent(tester, _item(onRemove: () {}));
    expect(find.text('IMG_4821.jpg'), findsOneWidget);
    expect(find.text('4.2 MB, 6000 by 4000 pixels'), findsOneWidget);
    expect(find.byType(StatusChip), findsOneWidget);
    expect(find.text('Ready'), findsOneWidget);
  });

  testWidgets('every state renders its own word', (WidgetTester tester) async {
    for (final UploadState state in UploadState.values) {
      await pumpComponent(tester, _item(state: state, progress: 0.4));
      expect(find.text(state.label), findsOneWidget, reason: state.name);
    }
  });

  testWidgets('uploading carries a determinate ring, other states do not', (
    WidgetTester tester,
  ) async {
    await pumpComponent(
      tester,
      _item(state: UploadState.uploading, progress: 0.42),
    );
    final CircularProgressIndicator ring = tester
        .widget<CircularProgressIndicator>(
          find.byType(CircularProgressIndicator),
        );
    expect(ring.value, 0.42);

    await pumpComponent(
      tester,
      _item(state: UploadState.checking, progress: 0.42),
    );
    expect(find.byType(CircularProgressIndicator), findsNothing);
  });

  testWidgets('a failed item keeps its reason and stays in the list', (
    WidgetTester tester,
  ) async {
    await pumpComponent(
      tester,
      _item(
        state: UploadState.failed,
        reason: 'The server could not read the file. Try the original.',
        onRemove: () {},
      ),
    );
    expect(find.text('Failed'), findsOneWidget);
    expect(
      find.text('The server could not read the file. Try the original.'),
      findsOneWidget,
    );
  });

  testWidgets('the remove action fires, and a row that cannot be removed '
      'says why instead of spending a target on a dead control', (
    WidgetTester tester,
  ) async {
    int removed = 0;
    await pumpComponent(tester, _item(onRemove: () => removed++));
    await tester.tap(find.byTooltip(UploadItem.removeLabel));
    await tester.pumpAndSettle();
    expect(removed, 1);

    // No callback and no reason: no control at all.
    await pumpComponent(tester, _item());
    expect(find.byType(IconButton), findsNothing);

    // A reason: the control is there, disabled, and names the reason.
    await pumpComponent(
      tester,
      _item(removeBlockedReason: 'The server has taken this file.'),
    );
    final IconButton button = tester.widget<IconButton>(
      find.byType(IconButton),
    );
    expect(button.onPressed, isNull);
    expect(button.tooltip, contains('The server has taken this file.'));
  });

  testWidgets('the duplicate state uses the agreed words', (
    WidgetTester tester,
  ) async {
    await pumpComponent(tester, _item(state: UploadState.duplicate));
    expect(find.text('Already in collection'), findsOneWidget);
  });

  testWidgets('the state chip speaks its own vocabulary', (
    WidgetTester tester,
  ) async {
    final SemanticsHandle handle = tester.ensureSemantics();
    await pumpComponent(tester, _item(state: UploadState.accepted));
    expect(find.bySemanticsLabel('Upload: accepted'), findsOneWidget);
    handle.dispose();
  });

  testWidgets('renders in both themes and meets the guidelines', (
    WidgetTester tester,
  ) async {
    for (final ThemeData theme in productThemes.values) {
      await pumpComponent(tester, _item(onRemove: () {}), theme: theme);
      await expectAccessible(tester);
    }
  });
}
