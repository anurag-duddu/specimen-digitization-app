import 'dart:io';

import 'package:flutter/widgets.dart';
import 'package:specimen_digitization/src/widgets/intake_photo.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/screens/intake/manifest_panel.dart';
import 'package:specimen_digitization/src/widgets/upload_item.dart';
import 'package:specimen_ui/specimen_ui.dart';

import 'intake_manifest_test.dart' show entryIn, pumpManifest;
import 'ui_finders.dart';
import 'widgets/harness.dart';

void main() {
  testWidgets('compact handoff row has one action and opens its diagnostics', (
    tester,
  ) async {
    final entry = entryIn(UploadState.failed);
    entry.transferError = const ApiFailure(
      'raw server refusal',
      code: 'rejected',
    );
    await pumpManifest(tester, [entry], size: const Size(390, 844));
    expect(find.byType(UiDisclosure), findsNothing);
    expect(find.text('Not sent'), findsOneWidget);
    expect(find.text('Sensitive'), findsOneWidget);
    expect(find.text('raw server refusal'), findsNothing);
    expect(find.textContaining('Checksum'), findsNothing);
    expect(
      tester.getSize(find.byType(IntakeManifestRow)).height,
      lessThanOrEqualTo(88),
    );
    final semantics = tester.ensureSemantics();
    expect(
      find.bySemanticsLabel(RegExp('specimen.png, Not sent, sensitive')),
      findsOneWidget,
    );
    await tester.tap(find.text('specimen.png'));
    await tester.pumpAndSettle();
    expect(find.byType(UiSheet), findsOneWidget);
    expect(find.textContaining('Checksum (SHA-256)'), findsOneWidget);
    expect(find.text('raw server refusal'), findsOneWidget);
    semantics.dispose();
  });

  for (final serverSensitive in <bool?>[true, false, null]) {
    testWidgets(
      'restored row and details use server sensitivity $serverSensitive',
      (tester) async {
        final semantics = tester.ensureSemantics();
        final entry = entryIn(UploadState.ready);
        final file = entry.file!;
        // Reselection can use the opposite local default, but resumes the
        // existing handle without changing its server classification.
        entry.file = IntakeFile(
          name: file.name,
          bytes: file.bytes,
          mimeType: file.mimeType,
          sha256: file.sha256,
          method: file.method,
          sensitive: serverSensitive == false,
        );
        entry.session = {
          'upload_id': 'restored',
          if (serverSensitive != null) 'sensitive': serverSensitive,
        };
        await pumpManifest(tester, [entry], size: const Size(390, 844));
        final spoken = serverSensitive == null
            ? 'sensitivity not available'
            : serverSensitive
            ? 'sensitive'
            : 'not sensitive';
        expect(
          find.bySemanticsLabel('specimen.png, Ready, $spoken'),
          findsOneWidget,
        );
        expect(
          find.descendant(
            of: find.byType(IntakeManifestRow),
            matching: find.text('Sensitive'),
          ),
          serverSensitive == true ? findsOneWidget : findsNothing,
        );
        await tester.tap(find.text('specimen.png'));
        await tester.pumpAndSettle();
        final detail = serverSensitive == null
            ? 'Existing upload, classification unchanged'
            : serverSensitive
            ? 'Sensitive'
            : 'Not sensitive';
        expect(
          find.descendant(
            of: find.byType(UiSheet),
            matching: find.text(detail),
          ),
          findsOneWidget,
        );
        semantics.dispose();
      },
    );
  }

  testWidgets('an open sensitivity menu tolerates its photo finishing', (
    tester,
  ) async {
    final entry = entryIn(UploadState.ready);
    var changes = 0;
    await pumpComponent(
      tester,
      IntakeManifest(
        entries: [entry],
        busy: false,
        stopping: false,
        onStop: () {},
        onRemove: (_) {},
        onServerCheck: (_) {},
        onSensitivityChanged: (entry, value) {
          if (entry.state == UploadState.ready && entry.file != null) changes++;
        },
      ),
    );
    await tester.tap(find.byType(UiMenuTrigger));
    await tester.pumpAndSettle();
    // The open menu retains its callback until the next UI frame.
    entry.state = UploadState.inMainQueue;
    entry.file = null;
    await tester.tap(find.text('Mark not sensitive'));
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
    expect(changes, 0);
  });

  testWidgets(
    'row and details resized previews release their cache keys on close',
    (tester) async {
      final entry = entryIn(UploadState.ready);
      entry.file = IntakeFile(
        name: entry.label,
        bytes: File('test/fixtures/synthetic-label.png').readAsBytesSync(),
        mimeType: 'image/png',
        sha256: entry.digest,
        method: 'files',
        sensitive: false,
      );
      await pumpManifest(tester, [entry]);
      final rowImage = find.descendant(
        of: find.byType(UploadItem),
        matching: find.byType(Image),
      );
      final provider = tester.widget<Image>(rowImage).image;
      await tester.runAsync(
        () => precacheImage(provider, tester.element(rowImage)),
      );
      await tester.tap(find.text(entry.label));
      await tester.pumpAndSettle();
      final detailImage = find.descendant(
        of: find.byType(IntakePhoto),
        matching: find.byType(Image),
      );
      final detailProvider = tester.widget<Image>(detailImage).image;
      await tester.runAsync(
        () => precacheImage(detailProvider, tester.element(detailImage)),
      );
      final keys = await Future.wait([
        provider.obtainKey(ImageConfiguration.empty),
        detailProvider.obtainKey(ImageConfiguration.empty),
      ]);
      expect(
        keys.every(PaintingBinding.instance.imageCache.containsKey),
        isTrue,
      );
      await tester.pumpWidget(const SizedBox.shrink());
      await tester.pumpAndSettle();
      for (final key in keys) {
        expect(PaintingBinding.instance.imageCache.containsKey(key), isFalse);
        expect(
          PaintingBinding.instance.imageCache.statusForKey(key).live,
          isFalse,
        );
      }
    },
  );

  testWidgets(
    'Ready menu edits only the selected photo and locks after creation',
    (tester) async {
      final first = entryIn(UploadState.ready, name: 'first.png');
      final second = entryIn(
        UploadState.ready,
        name: 'second.png',
        digest: 'second',
      );
      final changes = <String>[];
      await pumpComponent(
        tester,
        IntakeManifest(
          entries: [first, second],
          busy: false,
          stopping: false,
          onStop: () {},
          onRemove: (_) {},
          onServerCheck: (_) {},
          onSensitivityChanged: (entry, value) =>
              changes.add('${entry.label}:$value'),
        ),
      );
      await tester.tap(find.byType(UiMenuTrigger).first);
      await tester.pumpAndSettle();
      await tester.tap(find.text('Mark not sensitive'));
      await tester.pumpAndSettle();
      expect(changes, ['first.png:false']);
      first.session = {'upload_id': 'existing'};
      await pumpComponent(
        tester,
        IntakeManifest(
          entries: [first],
          busy: false,
          stopping: false,
          onStop: () {},
          onRemove: (_) {},
          onServerCheck: (_) {},
          onSensitivityChanged: (entry, value) => changes.add('unexpected'),
        ),
      );
      await tester.tap(find.byType(UiMenuTrigger));
      await tester.pumpAndSettle();
      expect(find.text('Mark not sensitive'), findsNothing);
      expect(find.text('Remove'), findsOneWidget);
    },
  );

  testWidgets('completion remains visible and opens Specimens', (tester) async {
    var opens = 0;
    await pumpComponent(
      tester,
      IntakeManifest(
        entries: [],
        sent: 12,
        busy: false,
        stopping: false,
        onStop: () {},
        onRemove: (_) {},
        onServerCheck: (_) {},
        onViewSpecimens: () => opens++,
      ),
    );
    expect(find.text('All 12 sent'), findsOneWidget);
    expect(find.text('No photos yet'), findsNothing);
    await tester.tap(uiButton('View in Specimens'));
    expect(opens, 1);
  });

  testWidgets(
    'batch bar names its measured progress and stopping consequence',
    (tester) async {
      await pumpComponent(
        tester,
        IntakeManifest(
          entries: [
            entryIn(UploadState.uploading, progress: 0.5),
            ...List.generate(
              9,
              (i) => entryIn(UploadState.ready, digest: '$i'),
            ),
          ],
          sent: 2,
          busy: true,
          stopping: false,
          onStop: () {},
          onRemove: (_) {},
          onServerCheck: (_) {},
        ),
      );
      expect(find.text('Sending 3 of 12'), findsOneWidget);
      final bar = tester.widgetList<UiProgress>(find.byType(UiProgress)).first;
      expect(bar.value, closeTo(2.5 / 12, 0.0001));
      expect(bar.semanticsLabel, 'Sending 3 of 12');
      expect(find.text('Stop sending'), findsOneWidget);
      expect(find.textContaining('Stop cancels'), findsNothing);
    },
  );

  for (final scale in [1.0, 2.0]) {
    testWidgets('all handoff row states fit 390dp at text $scale', (
      tester,
    ) async {
      for (final state in UploadState.values) {
        final entry = entryIn(state);
        await pumpComponent(
          tester,
          Builder(
            builder: (context) => MediaQuery(
              data: MediaQuery.of(
                context,
              ).copyWith(textScaler: TextScaler.linear(scale)),
              child: IntakeManifest(
                entries: [entry],
                busy: false,
                stopping: false,
                onStop: () {},
                onRemove: (_) {},
                onServerCheck: (_) {},
                onRetry: (_) {},
              ),
            ),
          ),
          size: const Size(390, 844),
        );
        expect(tester.takeException(), isNull, reason: '$state at $scale');
        if (scale == 1.0) {
          expect(
            tester.getSize(find.byType(IntakeManifestRow)).height,
            lessThanOrEqualTo(88),
            reason: '$state at $scale',
          );
        }
        expect(find.byType(UiDisclosure), findsNothing);
      }
    });
  }
}
