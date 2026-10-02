// Runs the real application against the explicitly synthetic capture service.
// These gestures enter Flutter's pointer pipeline; OS gesture qualification
// (system Back, iOS edge swipe, keyboard and pickers) is a separate device pass.
import 'package:flutter/cupertino.dart' as cupertino;
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart' as material;
import 'package:flutter/semantics.dart';
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:specimen_digitization/src/app/shell.dart';
import 'package:specimen_digitization/src/audit_history.dart';
import 'package:specimen_digitization/src/intake.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/screens/workbench/source_pane.dart';
import 'package:specimen_digitization/src/widgets/diff_text.dart';
import 'package:specimen_digitization/src/widgets/evidence_drawer.dart';
import 'package:specimen_digitization/src/widgets/queue_row.dart';
import 'package:specimen_digitization/src/widgets/region_overlay.dart';
import 'package:specimen_digitization/src/widgets/repository_url_import_gate.dart';
import 'package:specimen_digitization/src/workbench.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../test/ui_finders.dart';
import '../test/verification/capture_app.dart' as capture;

final List<Map<String, Object>> _nativeImeTapChecks = [];

Finder get _record => find.byType(ReviewWorkbench);
Finder get _canvas => find.byKey(const ValueKey('source-photo-viewport'));
Finder get _nativeNav => find.byKey(const ValueKey('mobile-navigation'));
Finder get _labelPicker => find.byWidgetPredicate(
  (widget) => widget is UiSelect<String> && widget.label == 'Label',
  skipOffstage: false,
);

Finder _row(String id) =>
    find.byWidgetPredicate((widget) => widget is QueueRow && widget.id == id);

Future<void> _settle(WidgetTester tester) async {
  await tester.pumpAndSettle(
    const Duration(milliseconds: 100),
    EnginePhase.sendSemanticsUpdate,
    const Duration(seconds: 15),
  );
}

EdgeInsets _liveInsets(WidgetTester tester) => EdgeInsets.fromViewPadding(
  tester.view.viewInsets,
  tester.view.devicePixelRatio,
);

Future<void> _settleNativeInsets(WidgetTester tester) async {
  var previous = _liveInsets(tester);
  var stable = 0;
  for (var sample = 0; sample < 10 && stable < 2; sample++) {
    // Native IME metrics can arrive after Flutter's first settled frame.
    await tester.pump(const Duration(milliseconds: 100));
    final current = _liveInsets(tester);
    stable = current == previous ? stable + 1 : 0;
    previous = current;
  }
  expect(stable, 2, reason: 'native view insets did not settle');
}

Future<Size> _awaitOrientation(
  WidgetTester tester, {
  required bool portrait,
}) async {
  for (var sample = 0; sample < 60; sample++) {
    await tester.pump(const Duration(milliseconds: 100));
    final size = tester.view.physicalSize / tester.view.devicePixelRatio;
    if ((size.height > size.width) == portrait) break;
  }
  await _settle(tester);
  final size = tester.view.physicalSize / tester.view.devicePixelRatio;
  expect(size.height > size.width, portrait);
  return size;
}

void _expectLandscapeReading(WidgetTester tester) {
  final size = tester.view.physicalSize / tester.view.devicePixelRatio;
  if (size.height >= size.width || size.shortestSide >= 600) return;
  expect(find.byKey(const ValueKey('review-inspector')), findsOneWidget);
  final viewport = tester.getRect(find.byKey(evidenceScrollKey));
  final literal = tester.getRect(find.byType(DiffText).first);
  expect(literal.top, greaterThanOrEqualTo(viewport.top));
  expect(
    literal.bottom,
    lessThanOrEqualTo(viewport.bottom),
    reason: 'the actual VLM reading must be visible, not just its heading',
  );
}

Future<void> _tap(
  WidgetTester tester,
  Finder target, {
  bool throughSemantics = false,
}) async {
  await _settle(tester);
  await _settleNativeInsets(tester);
  expect(target, findsOneWidget);
  await tester.ensureVisible(target);
  await _settle(tester);
  expect(target.hitTestable(), findsOneWidget);
  final size = tester.view.physicalSize / tester.view.devicePixelRatio;
  final insets = _liveInsets(tester);
  final visible = Rect.fromLTRB(
    insets.left,
    insets.top,
    size.width - insets.right,
    size.height - insets.bottom,
  );
  final rect = tester.getRect(target);
  final reason = '$target: $rect outside $visible; insets=$insets';
  expect(visible.contains(rect.center), isTrue, reason: reason);
  expect(rect.left, greaterThanOrEqualTo(visible.left - 0.5), reason: reason);
  expect(rect.top, greaterThanOrEqualTo(visible.top - 0.5), reason: reason);
  expect(rect.right, lessThanOrEqualTo(visible.right + 0.5), reason: reason);
  expect(rect.bottom, lessThanOrEqualTo(visible.bottom + 0.5), reason: reason);
  if (insets != EdgeInsets.zero) {
    _nativeImeTapChecks.add({
      'target': target.toString(),
      'insets': [insets.left, insets.top, insets.right, insets.bottom],
      'targetRect': [rect.left, rect.top, rect.right, rect.bottom],
      'visibleRect': [visible.left, visible.top, visible.right, visible.bottom],
    });
  }
  if (throughSemantics) {
    final node = tester.getSemantics(target);
    expect(node.getSemanticsData().hasAction(SemanticsAction.tap), isTrue);
    node.owner!.performAction(node.id, SemanticsAction.tap);
  } else {
    await tester.tap(target);
  }
  await _settle(tester);
}

Future<void> _awaitNavigationReturn(
  WidgetTester tester,
  Finder navigation,
) async {
  for (var sample = 0; sample < 30; sample++) {
    if (_liveInsets(tester).bottom == 0 && navigation.evaluate().length == 1) {
      return;
    }
    await tester.pump(const Duration(milliseconds: 100));
  }
  expect(
    _liveInsets(tester).bottom,
    0,
    reason: 'the native keyboard must dismiss after closing the link dialog',
  );
  expect(navigation, findsOneWidget);
}

Future<void> _launch(WidgetTester tester) async {
  // Each case has a new in-memory repository and router. Do not clear device
  // preferences or replace native plugins with mocks in this suite.
  await tester.pumpWidget(const SizedBox.shrink());
  await capture.main();
  await _settle(tester);
  expect(_row('fixture-001'), findsOneWidget);
  addTearDown(() async {
    await tester.pumpWidget(const SizedBox.shrink());
    await _settle(tester);
  });
}

Future<void> _openRecord(WidgetTester tester) async {
  await _tap(tester, _row('fixture-001'));
  expect(_record, findsOneWidget);
  expect(_specimen(tester).id, 'fixture-001');
  expect(uiSelect('Label'), findsOneWidget);
}

Specimen _specimen(WidgetTester tester) =>
    tester.widget<ReviewWorkbench>(_record).specimen;

Finder _destination(String label) {
  if (_nativeNav.evaluate().isNotEmpty) {
    return find.descendant(of: _nativeNav, matching: find.text(label));
  }
  return find.descendant(
    of: find.byKey(const ValueKey('global-rail')),
    matching: find.byWidgetPredicate(
      (widget) => widget is Pressable && widget.semanticsLabel == label,
    ),
  );
}

void _expectNavigation(WidgetTester tester, int selected) {
  final size = tester.view.physicalSize / tester.view.devicePixelRatio;
  final textScaler = MediaQuery.textScalerOf(
    tester.element(find.byType(AppShell)),
  );
  final scale = (textScaler.scale(16) / 16).clamp(1.0, 2.0);
  final mobile = size.width < 768 * scale || size.height < 600;
  // Assert the layout contract before inspecting its implementation. A full
  // tablet must not silently pass with phone tabs, and a landscape phone
  // remains a phone-sized window even when its width exceeds 768.
  expect(_nativeNav, mobile ? findsOneWidget : findsNothing);
  expect(
    find.byKey(const ValueKey('global-rail')),
    mobile ? findsNothing : findsOneWidget,
  );
  if (mobile) {
    if (defaultTargetPlatform == TargetPlatform.iOS) {
      expect(find.byType(cupertino.CupertinoTabBar), findsOneWidget);
      expect(find.byType(material.NavigationBar), findsNothing);
      expect(
        tester.widget<cupertino.CupertinoTabBar>(_nativeNav).currentIndex,
        selected,
      );
    } else {
      expect(find.byType(material.NavigationBar), findsOneWidget);
      expect(find.byType(cupertino.CupertinoTabBar), findsNothing);
      expect(
        tester.widget<material.NavigationBar>(_nativeNav).selectedIndex,
        selected,
      );
    }
    expect(find.byKey(const ValueKey('global-rail')), findsNothing);
    expect(find.byKey(const ValueKey('global-sidebar')), findsNothing);
  } else {
    expect(find.byKey(const ValueKey('global-rail')), findsOneWidget);
    expect(
      tester
          .widget<Pressable>(
            _destination(selected == 0 ? 'Specimens' : 'Intake'),
          )
          .selected,
      isTrue,
    );
  }
}

Future<void> _pickLabel(WidgetTester tester, int number) async {
  await _tap(tester, _labelPicker);
  // The menu scrolls in a short landscape window. Find its row before _tap
  // reveals it and validates that the complete target is visible and hittable.
  final option = find.byWidgetPredicate(
    (widget) => widget is UiListRow && widget.title == 'Label $number',
  );
  await _tap(tester, option);
  expect(tester.widget<UiSelect<String>>(_labelPicker).value, 'r$number');
}

Future<void> _revealSource(WidgetTester tester) async {
  await _settle(tester);
  // The photograph shares the phone's ordinary page scroll. Finding the
  // laid-out offscreen block lets ensureVisible reveal it after the picker.
  final source = find.byKey(
    const ValueKey('source-photo-viewport'),
    skipOffstage: false,
  );
  expect(source, findsOneWidget);
  await tester.ensureVisible(source);
  await _settle(tester);
  expect(_canvas, findsOneWidget);
  final window =
      Offset.zero & (tester.view.physicalSize / tester.view.devicePixelRatio);
  expect(tester.getRect(_canvas).overlaps(window), isTrue);
}

Future<void> _expectLabel(WidgetTester tester, int number) async {
  expect(tester.widget<UiSelect<String>>(_labelPicker).value, 'r$number');
  await _revealSource(tester);
  final panes = tester.widgetList<WorkbenchSourcePane>(
    find.byType(WorkbenchSourcePane),
  );
  // Pane wrappers may be offstage in the phone sliver layout; the visible
  // photograph and its selected region below are required on every device.
  expect(panes.every((pane) => pane.selectedRegionId == 'r$number'), isTrue);
  final selected = tester.widgetList<RegionOverlay>(
    find.descendant(
      of: _canvas,
      matching: find.byWidgetPredicate(
        (widget) => widget is RegionOverlay && widget.selected,
      ),
    ),
  );
  expect(selected.map((overlay) => overlay.index), [number]);
}

Future<void> _tapImageLabel(WidgetTester tester, int number) async {
  await _revealSource(tester);
  if (uiButton('Reset view').evaluate().isNotEmpty) {
    await _tap(tester, uiButton('Reset view'));
  }
  final overlay = find.descendant(
    of: _canvas,
    matching: find.byWidgetPredicate(
      (widget) => widget is RegionOverlay && widget.index == number,
    ),
  );
  final badge = find.descendant(of: overlay, matching: find.text('$number'));
  expect(badge, findsOneWidget);
  // The painted number ignores pointers; the shared label hit target behind
  // it must receive this real pointer tap, including after record navigation.
  final point = tester.getCenter(badge);
  expect(tester.getRect(_canvas).contains(point), isTrue);
  await tester.tapAt(point);
  await _settle(tester);
  await _expectLabel(tester, number);
}

Future<void> _stepSpecimen(WidgetTester tester, String label) async {
  final arrow = uiIconButton(label);
  if (arrow.evaluate().isNotEmpty) {
    await _tap(tester, arrow);
  } else {
    final menu = find.byWidgetPredicate(
      (widget) =>
          widget is UiMenuTrigger &&
          widget.items.any((item) => item.label == label),
    );
    expect(menu, findsWidgets);
    await _tap(tester, menu.first);
    await _tap(tester, find.text(label));
  }
}

InteractiveViewer _viewer(WidgetTester tester) => tester.widget(
  find.descendant(of: _canvas, matching: find.byType(InteractiveViewer)),
);

List<double> _matrix(WidgetTester tester) =>
    _viewer(tester).transformationController!.value.storage.toList();

void _expectFitted(WidgetTester tester) {
  final matrix = _matrix(tester);
  for (var i = 0; i < 16; i++) {
    expect(matrix[i], closeTo(i % 5 == 0 ? 1 : 0, .001));
  }
  expect(uiButton('Reset view'), findsNothing);
}

void main() {
  final binding = IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets(
    'workspace navigation protects and discards a label draft',
    (tester) async {
      await _launch(tester);
      final size = tester.view.physicalSize / tester.view.devicePixelRatio;
      binding.reportData = <String, dynamic>{
        'fixture': 'capture_app synthetic in-memory repository',
        'logicalWidth': size.width,
        'logicalHeight': size.height,
        'platform': defaultTargetPlatform.name,
        'nativeImeTapChecks': _nativeImeTapChecks,
      };
      _expectNavigation(tester, 0);
      await _openRecord(tester);
      await _pickLabel(tester, 1);
      final state = tester.state(_record);
      final field = uiField('Accepted label text');
      await tester.ensureVisible(field);
      await tester.enterText(field, 'Synthetic retained draft');
      FocusManager.instance.primaryFocus?.unfocus();
      await _settle(tester);
      await _tap(tester, _destination('Intake'));
      expect(find.text('Discard unsaved corrections?'), findsOneWidget);
      await _tap(tester, uiButton('Keep editing'));
      expect(tester.state(_record), same(state));
      expect(
        tester.widget<UiField>(field).controller!.text,
        'Synthetic retained draft',
      );
      _expectNavigation(tester, 0);
      await _tap(tester, _destination('Intake'));
      await _tap(tester, uiButton('Discard changes').hitTestable());
      expect(find.byType(IntakeScreen), findsOneWidget);
      expect(_record, findsNothing);
      _expectNavigation(tester, 1);
      await _tap(tester, _destination('Specimens'));
      _expectNavigation(tester, 0);
      expect(_record, findsOneWidget);
      expect(tester.state(_record), same(state));
      await _pickLabel(tester, 1);
      expect(tester.widget<UiField>(field).controller!.text, isEmpty);
      // Reselecting the active destination returns to its list root.
      await _tap(tester, _destination('Specimens'));
      expect(_record, findsNothing);
      expect(_row('fixture-001'), findsOneWidget);
      await _openRecord(tester);
      expect(tester.takeException(), isNull);
    },
    timeout: const Timeout(Duration(minutes: 2)),
  );

  testWidgets(
    'label overlays and specimen arrows retain working selection',
    (tester) async {
      await _launch(tester);
      await _openRecord(tester);
      await _pickLabel(tester, 2);
      await _expectLabel(tester, 2);
      await _tap(tester, uiRecordView('Structured specimen data'));
      await _revealSource(tester);
      await _tap(tester, uiButton('Reset view'));
      // Select the on-image hit target from the data context, not the picker.
      final overlay = find.descendant(
        of: _canvas,
        matching: find.byWidgetPredicate(
          (widget) => widget is Pressable && widget.semanticsLabel == 'Label 2',
        ),
      );
      await _tap(tester, overlay);
      await _expectLabel(tester, 2);
      await _stepSpecimen(tester, 'Next specimen');
      expect(_specimen(tester).id, 'fixture-002');
      await _tapImageLabel(tester, 2);
      await _pickLabel(tester, 3);
      await _expectLabel(tester, 3);
      await _stepSpecimen(tester, 'Previous specimen');
      expect(_specimen(tester).id, 'fixture-001');
      await _tapImageLabel(tester, 1);
      expect(tester.takeException(), isNull);
    },
    timeout: const Timeout(Duration(minutes: 2)),
  );

  testWidgets(
    'continuous image pinch and pan reset inside the photograph',
    (tester) async {
      await _launch(tester);
      await _openRecord(tester);
      await _tap(tester, uiIconButton('Open photograph'));
      if (uiButton('Reset view').evaluate().isNotEmpty) {
        await _tap(tester, uiButton('Reset view'));
      }
      _expectFitted(tester);
      final originalViewer = tester.state(
        find.descendant(of: _canvas, matching: find.byType(InteractiveViewer)),
      );
      final center = tester.getCenter(_canvas);
      final left = await tester.startGesture(
        center - const Offset(24, 0),
        pointer: 11,
      );
      final right = await tester.startGesture(
        center + const Offset(24, 0),
        pointer: 12,
      );
      try {
        await tester.pump();
        var lastScale = 1.0;
        // Keep BOTH pointers down as fitted scale crosses the pan threshold.
        for (final spread in [32.0, 44.0, 60.0, 80.0]) {
          await left.moveTo(center - Offset(spread, 0));
          await right.moveTo(center + Offset(spread, 0));
          await tester.pump(const Duration(milliseconds: 40));
          final scale = _viewer(
            tester,
          ).transformationController!.value.getMaxScaleOnAxis();
          expect(scale, greaterThanOrEqualTo(lastScale));
          lastScale = scale;
          expect(
            tester.state(
              find.descendant(
                of: _canvas,
                matching: find.byType(InteractiveViewer),
              ),
            ),
            same(originalViewer),
          );
        }
        expect(lastScale, greaterThan(1.5));
      } finally {
        await left.up();
        await right.up();
      }
      await _settle(tester);
      final beforePan = _matrix(tester);
      await tester.dragFrom(center, const Offset(48, 36));
      await _settle(tester);
      final afterPan = _matrix(tester);
      expect(
        (afterPan[12] - beforePan[12]).abs() +
            (afterPan[13] - beforePan[13]).abs(),
        greaterThan(8),
      );
      final canvas = tester.getRect(_canvas);
      final reset = tester.getRect(uiButton('Reset view'));
      expect(canvas.contains(reset.topLeft), isTrue);
      expect(canvas.contains(reset.bottomRight), isTrue);
      expect(canvas.right - reset.right, inInclusiveRange(0, 24));
      expect(canvas.bottom - reset.bottom, inInclusiveRange(0, 24));
      await _tap(tester, uiButton('Reset view'));
      _expectFitted(tester);
      await _tap(tester, uiIconButton('Close the full screen photograph'));
      expect(_record, findsOneWidget);
      // Inline label inspection also needs deliberate pan without navigating
      // away or losing which label is selected.
      await _pickLabel(tester, 1);
      await _revealSource(tester);
      final inlineBefore = _matrix(tester);
      await tester.dragFrom(tester.getCenter(_canvas), const Offset(40, 24));
      await _settle(tester);
      final inlineAfter = _matrix(tester);
      expect(
        (inlineAfter[12] - inlineBefore[12]).abs() +
            (inlineAfter[13] - inlineBefore[13]).abs(),
        greaterThan(8),
      );
      await _expectLabel(tester, 1);
      final inlineCanvas = tester.getRect(_canvas);
      final inlineReset = tester.getRect(uiButton('Reset view'));
      expect(inlineCanvas.contains(inlineReset.topLeft), isTrue);
      expect(inlineCanvas.contains(inlineReset.bottomRight), isTrue);
      expect(inlineCanvas.right - inlineReset.right, inInclusiveRange(0, 24));
      expect(inlineCanvas.bottom - inlineReset.bottom, inInclusiveRange(0, 24));
      await _tap(tester, uiButton('Reset view'));
      expect(uiButton('Reset view'), findsNothing);
      expect(tester.widget<UiSelect<String>>(_labelPicker).value, '');
      expect(tester.takeException(), isNull);
    },
    timeout: const Timeout(Duration(minutes: 2)),
  );

  testWidgets(
    'history reset and restore create retained audit versions',
    (tester) async {
      await _launch(tester);
      await _openRecord(tester);
      final original = _specimen(tester);
      await _pickLabel(tester, 1);
      final accepted = uiField('Accepted label text');
      await tester.ensureVisible(accepted);
      final baselineText = tester.widget<UiField>(accepted).controller!.text;
      const editedText = 'Synthetic history correction: Chicago 1919';
      expect(baselineText, isNot(editedText));
      await tester.enterText(accepted, editedText);
      await _settle(tester);
      final correctionReason = uiField('Reason for correction');
      await tester.ensureVisible(correctionReason);
      await tester.enterText(
        correctionReason,
        'Synthetic changed-label history check',
      );
      await _tap(tester, uiButton('Save label text'));
      final edited = _specimen(tester);
      expect(edited.revision, original.revision + 1);
      expect(edited.audit.length, original.audit.length + 1);
      expect(edited.audit.last['action'], 'transcription_adjudication');
      expect(tester.widget<UiField>(accepted).controller!.text, editedText);
      expect(find.text('Unsaved changes'), findsNothing);
      // Phone context tabs can be outside the lazy page viewport after editing.
      // Reveal the photograph/top context before finding a record-view control.
      await _revealSource(tester);
      await _tap(tester, uiRecordView('Review history'));
      expect(find.byType(AuditHistoryPanel), findsOneWidget);
      await _tap(tester, uiButton('Start over'));
      expect(find.text('Initial version · 1'), findsOneWidget);
      await _tap(tester, uiButton('Reset to initial version'));
      await tester.enterText(uiField('Reason'), 'Synthetic reset smoke check');
      await _tap(tester, uiButton('Reset specimen'));
      final reset = _specimen(tester);
      expect(reset.revision, edited.revision + 1);
      expect(reset.assets, original.assets);
      expect(reset.audit.length, edited.audit.length + 1);
      expect(reset.audit.sublist(0, edited.audit.length), edited.audit);
      expect(reset.audit.last['action'], 'review_reset_initial');
      expect(reset.audit.last['source_revision'], 1);
      expect(reset.audit.last['reason'], 'Synthetic reset smoke check');
      expect(find.text('Current version ${reset.revision}'), findsOneWidget);
      await _revealSource(tester);
      await _tap(tester, uiRecordView('Label review'));
      await _pickLabel(tester, 1);
      await tester.ensureVisible(accepted);
      await _settle(tester);
      expect(accepted.hitTestable(), findsOneWidget);
      expect(tester.widget<UiField>(accepted).controller!.text, baselineText);
      await _revealSource(tester);
      await _tap(tester, uiRecordView('Review history'));
      await _tap(
        tester,
        find.byWidgetPredicate(
          (widget) =>
              widget is UiListRow &&
              widget.title == 'Version ${edited.revision}',
        ),
      );
      await _tap(tester, uiButton('Restore this version'));
      await tester.enterText(
        uiField('Reason'),
        'Synthetic restore smoke check',
      );
      await _tap(tester, uiButton('Restore version'));
      final restored = _specimen(tester);
      expect(restored.revision, reset.revision + 1);
      expect(restored.audit.length, reset.audit.length + 1);
      expect(restored.audit.sublist(0, reset.audit.length), reset.audit);
      expect(restored.audit.last['action'], 'review_restore_version');
      expect(restored.audit.last['source_revision'], edited.revision);
      expect(restored.audit.last['reason'], 'Synthetic restore smoke check');
      expect(restored.assets, original.assets);
      expect(find.text('Current version ${restored.revision}'), findsOneWidget);
      await _revealSource(tester);
      await _tap(tester, uiRecordView('Label review'));
      await _pickLabel(tester, 1);
      await tester.ensureVisible(accepted);
      await _settle(tester);
      expect(accepted.hitTestable(), findsOneWidget);
      expect(tester.widget<UiField>(accepted).controller!.text, editedText);
      expect(tester.takeException(), isNull);
    },
    timeout: const Timeout(Duration(minutes: 2)),
  );

  testWidgets(
    'intake checks registered storage in a dismissible link dialog',
    (tester) async {
      await _launch(tester);
      await _tap(tester, _destination('Intake'));
      expect(find.byType(IntakeScreen), findsOneWidget);
      final navigation = _nativeNav.evaluate().isNotEmpty
          ? _nativeNav
          : find.byKey(const ValueKey('global-rail'));
      expect(find.byType(RepositoryUrlIntake), findsNothing);
      await _tap(tester, uiIconButton('Import from link'));
      expect(find.byType(RepositoryUrlIntake), findsOneWidget);
      expect(uiButton('Review source'), findsNothing);
      await tester.enterText(
        uiField('Folder location'),
        'gs://specimen-digitization.firebasestorage.app/microscopic-slides/',
      );
      await _tap(tester, uiButton('Check location'));
      expect(
        find.text('Registered source found. Latest inventory: 1000 items.'),
        findsOneWidget,
      );
      expect(uiButton('Review source'), findsOneWidget);
      await tester.enterText(
        uiField('Folder location'),
        'gs://unregistered-synthetic-bucket/specimens/',
      );
      await _settle(tester);
      expect(uiButton('Review source'), findsNothing);
      await _tap(tester, uiButton('Check location'));
      expect(
        find.textContaining('This folder is not registered'),
        findsOneWidget,
      );
      await _tap(tester, uiButton('Close'));
      expect(find.byType(RepositoryUrlIntake), findsNothing);
      expect(find.byType(IntakeScreen), findsOneWidget);
      await _awaitNavigationReturn(tester, navigation);
      _expectNavigation(tester, 1);
      expect(tester.takeException(), isNull);
    },
    timeout: const Timeout(Duration(minutes: 2)),
  );

  testWidgets(
    'raw reading provenance closes independently by touch and semantics',
    (tester) async {
      final semantics = tester.ensureSemantics();
      try {
        await _launch(tester);
        await _openRecord(tester);
        await _pickLabel(tester, 1);
        final readingSource = uiIconButton(
          RegExp('^How this reading was produced,'),
        ).first;
        await _tap(tester, readingSource);

        const title = 'Reading provenance and raw response';
        final rawTrigger = uiButton(title);
        expect(rawTrigger, findsOneWidget);
        final parentRoute = ModalRoute.of(tester.element(rawTrigger))!;
        final drawer = tester.widget<EvidenceDrawer>(
          find.byWidgetPredicate(
            (widget) => widget is EvidenceDrawer && widget.title == title,
          ),
        );
        final payload = EvidenceDrawer.pretty(drawer.payload);
        expect(payload, isNotEmpty);
        final inner = find.byWidgetPredicate(
          (widget) =>
              (widget is UiDialog && widget.title == title) ||
              (widget is UiSheet && widget.title == title),
        );

        for (final accessible in [false, true]) {
          await _tap(tester, rawTrigger);
          expect(inner, findsOneWidget);
          expect(ModalRoute.of(tester.element(inner))!.isCurrent, isTrue);
          expect(find.text(payload), findsOneWidget);
          final close = find.descendant(
            of: inner,
            matching: find.byWidgetPredicate(
              (widget) =>
                  widget is Pressable &&
                  widget.semanticsLabel == 'Close' &&
                  widget.role == PressableRole.button,
            ),
          );
          expect(close, findsOneWidget);
          final node = tester.getSemantics(close);
          final data = node.getSemanticsData();
          expect(data.label, 'Close');
          expect(data.flagsCollection.isButton, isTrue);
          expect(data.hasAction(SemanticsAction.tap), isTrue);
          final bounds = tester.getRect(close);
          expect(bounds.width, greaterThanOrEqualTo(48));
          expect(bounds.height, greaterThanOrEqualTo(48));
          expect(node.rect.width, lessThanOrEqualTo(bounds.width + 1));
          expect(node.rect.height, lessThanOrEqualTo(bounds.height + 1));
          await _tap(tester, close, throughSemantics: accessible);

          expect(inner, findsNothing);
          expect(find.text(payload), findsNothing);
          expect(parentRoute.isCurrent, isTrue);
          expect(rawTrigger.hitTestable(), findsOneWidget);
        }

        await _tap(tester, uiButton('Close').hitTestable());
        expect(rawTrigger, findsNothing);
        expect(_record, findsOneWidget);
        expect(_specimen(tester).id, 'fixture-001');
        _expectNavigation(tester, 0);
        expect(tester.takeException(), isNull);
      } finally {
        semantics.dispose();
      }
    },
    timeout: const Timeout(Duration(minutes: 2)),
  );

  testWidgets(
    'native review renders and retains selection through phone rotation',
    (tester) async {
      await _launch(tester);
      await _openRecord(tester);
      await _pickLabel(tester, 1);
      await _revealSource(tester);
      final state = tester.state(_record);
      final initial = tester.view.physicalSize / tester.view.devicePixelRatio;
      await binding.convertFlutterSurfaceToImage();
      await tester.pump();
      _expectLandscapeReading(tester);
      await binding.takeScreenshot('review-initial');

      // Native orientation requests exercise real window metrics. Large Android
      // windows can deliberately ignore these requests, so tablets keep their
      // actual device orientation rather than faking a phone-sized window.
      if (initial.shortestSide < 600) {
        final initiallyPortrait = initial.height > initial.width;
        try {
          await SystemChrome.setPreferredOrientations([
            initiallyPortrait
                ? DeviceOrientation.landscapeLeft
                : DeviceOrientation.portraitUp,
          ]);
          final rotated = await _awaitOrientation(
            tester,
            portrait: !initiallyPortrait,
          );
          expect(tester.state(_record), same(state));
          expect(tester.widget<UiSelect<String>>(_labelPicker).value, 'r1');
          _expectNavigation(tester, 0);
          _expectLandscapeReading(tester);
          expect(tester.takeException(), isNull);
          await binding.takeScreenshot('review-rotated');
          binding.reportData!['nativeRotation'] = {
            'before': [initial.width, initial.height],
            'after': [rotated.width, rotated.height],
            'selectionRetained': true,
            'landscapeLiteralVisible': true,
          };
        } finally {
          try {
            await SystemChrome.setPreferredOrientations([
              initiallyPortrait
                  ? DeviceOrientation.portraitUp
                  : DeviceOrientation.landscapeLeft,
            ]);
            await _awaitOrientation(tester, portrait: initiallyPortrait);
          } finally {
            await SystemChrome.setPreferredOrientations([]);
          }
        }
      }
      expect(tester.takeException(), isNull);
    },
    timeout: const Timeout(Duration(minutes: 2)),
  );
}
