// Batch behaviour on the intake screen: Stop, the per-batch confirmation
// reset, and the rows this client refuses.
//
// Heuristics audit H1.5, H1.6, H3.6, H3.7, H5.3 and H9.4; pass criteria 1.5,
// 1.6, 3.6, 3.7, 5.3 and 9.3.

import 'dart:async';
import 'dart:io';
import 'dart:typed_data';

import 'package:file_selector/file_selector.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:specimen_digitization/src/intake.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/screens/intake/manifest_panel.dart';
import 'package:specimen_digitization/src/theme/app_theme.dart';

import 'intake_harness.dart';
import 'widget_test.dart' show TestRepository;

const CollectionScope scope = CollectionScope(
  organizationId: 'org',
  collectionId: 'insects',
  name: 'Synthetic insects',
);

/// Holds the first transfer open so a test can press Stop while a file is
/// genuinely in flight. Nothing here uses a timer, so the whole batch runs on
/// microtasks and a plain `pump` moves it along.
class HeldUploadRepository extends TestRepository {
  final Completer<void> release = Completer<void>();
  final List<String> created = <String>[];
  bool firstUploadStarted = false;

  @override
  Future<Json> createIntake(
    CollectionScope scope,
    IntakeFile file,
    String key,
  ) async {
    created.add(file.name);
    return <String, dynamic>{
      'upload_id': 'upload-${created.length}',
      'state': 'uploading',
      'offset': 0,
    };
  }

  @override
  Future<Json> resumeIntake(CollectionScope scope, String id) async =>
      <String, dynamic>{'upload_id': id, 'state': 'uploading', 'offset': 1};

  @override
  Future<void> upload(
    CollectionScope scope,
    Json session,
    IntakeFile file,
    void Function(double) progress,
  ) async {
    if (!firstUploadStarted) {
      firstUploadStarted = true;
      progress(0.5);
      await release.future;
    }
    progress(1);
  }
}

Future<void> pumpIntake(
  WidgetTester tester, {
  required SpecimenRepository repository,
  required Future<List<XFile>> Function(bool camera) pickImages,
  Size size = const Size(1100, 2400),
}) async {
  SharedPreferences.setMockInitialValues(<String, Object>{});
  tester.view.devicePixelRatio = 1;
  tester.view.physicalSize = size;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(
    MaterialApp(
      theme: AppTheme.light(),
      home: Scaffold(
        body: IntakeScreen(
          repository: repository,
          scope: scope,
          userId: 'owner',
          onComplete: () {},
          pickImages: pickImages,
        ),
      ),
    ),
  );
  await tester.pumpAndSettle();
}

/// Three fixtures with three different checksums, because the manifest
/// deduplicates by checksum and two copies of one file are one row.
const List<String> distinctFixtures = <String>[
  'synthetic-label.png',
  'synthetic-wide-label.png',
  'synthetic-heic-derived.png',
];

XFile fixture(String name, {int source = 0}) => XFile.fromData(
  File('test/fixtures/${distinctFixtures[source]}').readAsBytesSync(),
  path: name,
  name: name,
);

void main() {
  testWidgets('Stop cancels files that have not started, in flight finishes', (
    WidgetTester tester,
  ) async {
    final HeldUploadRepository repository = HeldUploadRepository();
    await pumpIntake(
      tester,
      repository: repository,
      pickImages: (bool _) async => <XFile>[
        fixture('one.png'),
        fixture('two.png', source: 1),
        fixture('three.png', source: 2),
      ],
    );
    await chooseFiles(tester);
    expect(find.text('0 of 3 accepted'), findsOneWidget);
    await confirmBatch(tester);

    await tester.ensureVisible(uploadButton);
    await tester.pumpAndSettle();
    await tester.tap(uploadButton);
    for (
      var attempt = 0;
      attempt < 20 && !repository.firstUploadStarted;
      attempt++
    ) {
      await tester.pump();
    }
    expect(repository.firstUploadStarted, isTrue);
    // One more frame, so the state the transfer just reached is drawn.
    await tester.pump();
    expect(find.text('Uploading'), findsWidgets);

    await tester.ensureVisible(stopButton);
    await tester.pump();
    await tester.tap(stopButton);
    await tester.pump();
    expect(find.text('Stopping'), findsOneWidget);

    repository.release.complete();
    await tester.pumpAndSettle();

    // The file already sending finished. The two that had not started are
    // named, not left in an unlabelled state (pass criterion 3.6).
    expect(repository.created, <String>['one.png']);
    expect(find.text('1 of 3 accepted'), findsOneWidget);
    expect(
      find.text('Stopped before this file started. Upload again to continue.'),
      findsNWidgets(2),
    );
  });

  testWidgets('a refused file becomes a skipped row with its own reason', (
    WidgetTester tester,
  ) async {
    await pumpIntake(
      tester,
      repository: TestRepository(),
      pickImages: (bool _) async => <XFile>[
        XFile.fromData(Uint8List(0), path: 'empty.png', name: 'empty.png'),
        XFile.fromData(
          File('test/fixtures/synthetic-label.png').readAsBytesSync(),
          path: 'notes.txt',
          name: 'notes.txt',
        ),
        fixture('good.png', source: 1),
      ],
    );
    await chooseFiles(tester);

    expect(find.text('0 of 3 accepted, 2 skipped'), findsOneWidget);
    expect(find.text('Skipped'), findsNWidgets(2));
    expect(find.text('empty.png'), findsOneWidget);
    expect(find.text('notes.txt'), findsOneWidget);
    expect(
      find.text('This file is empty, so there is nothing to upload.'),
      findsOneWidget,
    );
    expect(
      find.textContaining('This client uploads JPEG, PNG, HEIC, TIFF and DNG.'),
      findsOneWidget,
    );
    // Every reason sits in the row it belongs to (H9.4).
    expect(find.byType(IntakeManifestRow), findsNWidgets(3));
  });

  testWidgets('the per-batch confirmation clears whenever a file is added', (
    WidgetTester tester,
  ) async {
    var call = 0;
    await pumpIntake(
      tester,
      repository: TestRepository(),
      pickImages: (bool _) async => <XFile>[
        fixture('take-$call.png', source: call++),
      ],
    );
    await chooseFiles(tester);
    await confirmBatch(tester);
    expect(batchConfirmed(tester), isTrue);
    expect(buttonEnabled(tester, uploadButton), isTrue);

    await chooseFiles(tester);
    expect(
      batchConfirmed(tester),
      isFalse,
      reason: 'one tick must never authorise a file chosen after it',
    );
    expect(buttonEnabled(tester, uploadButton), isFalse);
  });

  testWidgets('the upload button names the count it authorises', (
    WidgetTester tester,
  ) async {
    var call = 0;
    await pumpIntake(
      tester,
      repository: TestRepository(),
      pickImages: (bool _) async => <XFile>[
        fixture('file-$call.png', source: call++),
      ],
    );
    await tester.ensureVisible(uploadButton);
    expect(find.text('Upload 0 photographs'), findsOneWidget);
    await chooseFiles(tester);
    expect(find.text('Upload 1 photograph'), findsOneWidget);
    await chooseFiles(tester);
    expect(find.text('Upload 2 photographs'), findsOneWidget);
  });

  testWidgets('removing a row takes it out of the batch', (
    WidgetTester tester,
  ) async {
    await pumpIntake(
      tester,
      repository: TestRepository(),
      pickImages: (bool _) async => <XFile>[fixture('unwanted.png')],
    );
    await chooseFiles(tester);
    expect(find.byType(IntakeManifestRow), findsOneWidget);
    final Finder remove = find.descendant(
      of: find.byType(IntakeManifestRow),
      matching: find.byType(IconButton),
    );
    await tester.ensureVisible(remove);
    await tester.pumpAndSettle();
    await tester.tap(remove);
    await tester.pumpAndSettle();
    expect(find.byType(IntakeManifestRow), findsNothing);
    expect(find.text('No files selected yet'), findsOneWidget);
  });
}
