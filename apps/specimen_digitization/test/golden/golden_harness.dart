// Scaffolding for the size-class goldens (north star, "Adaptation"; responsive
// and platform adaptation, section 8).
//
// One repository, one record, four widths, two themes and two text scales. The
// record is built from the checked-in wire fixtures in `test/fixtures/` rather
// than invented here, so a golden that changes because the wire changed is a
// real signal rather than a fixture drifting away from the server.
//
// Everything is pumped through `SpecimenDigitizationApp`, not through a bare
// widget, because a golden of a screen without its shell proves nothing about
// the navigation rail, the environment banner or the safe areas the blueprint
// puts around it.

import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/main.dart';
import 'package:specimen_digitization/src/app/routes.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/theme/app_theme.dart';
import 'package:specimen_digitization/src/theme/motion_preference.dart';
import 'package:specimen_digitization/src/workspace.dart';

import '../widget_test.dart' show TestRepository, TestSession;

/// The four windows the north star's adaptation row names.
///
/// One per size class: compact (a phone), medium (a tablet in portrait),
/// expanded (a tablet in landscape) and large (a desktop browser). The names
/// are the size classes, not the devices, because the window decides the
/// layout.
const Map<String, Size> goldenWindows = <String, Size>{
  'compact-390x844': Size(390, 844),
  'medium-768x1024': Size(768, 1024),
  'expanded-1180x820': Size(1180, 820),
  'large-1440x900': Size(1440, 900),
};

/// Both themes ship, so both themes are captured.
const Map<String, Brightness> goldenThemes = <String, Brightness>{
  'light': Brightness.light,
  'dark': Brightness.dark,
};

/// The collection the fixture repository publishes.
const String goldenCollection = 'org/insects';

/// The record every workbench golden opens.
const String goldenSpecimenId = 'fixture-001';

/// The photograph the source pane draws, read from the checked-in fixture.
final Uint8List goldenPreviewBytes = File(
  'test/fixtures/synthetic-label.png',
).readAsBytesSync();

/// The wire example the record below is derived from.
Json _wireWorkspace() =>
    (jsonDecode(
              File(
                'test/fixtures/backend-wire-examples.json',
              ).readAsStringSync(),
            )
            as Json)['workspace_response']
        as Json;

/// One record with everything the review screen has to draw: a photograph, two
/// label regions, two independent readings that disagree, fields in four
/// different states, an outstanding validation finding and a decision history.
Specimen goldenSpecimen() {
  final Json wire = _wireWorkspace();
  final Json asset = Json.from(wire['asset'] as Json)
    ..['asset_id'] = wire['asset_id']
    ..['preview_bytes'] = goldenPreviewBytes
    ..['pixel_basis'] = 'original_pixel_edges';
  return Specimen(<String, dynamic>{
    'specimen_id': goldenSpecimenId,
    'display_name': 'Pinned beetle, Chicago 1912',
    'revision': wire['revision'],
    'operational_state': 'completed',
    'disposition': 'needs_human_review',
    'reason_codes': wire['reason_codes'],
    'profile_version': wire['profile_version'],
    'available_actions': <String>[
      'field',
      'transcription',
      'coverage',
      'approve',
      'classification',
      'regions',
      'retry',
    ],
    'assets': <Json>[asset],
    'regions': <Json>[
      <String, dynamic>{
        'region_id': 'r1',
        'bbox': <int>[40, 40, 460, 220],
        'order': 0,
        'rotation_quarter_turns': 0,
      },
      <String, dynamic>{
        'region_id': 'r2',
        'bbox': <int>[520, 260, 940, 470],
        'order': 1,
        'rotation_quarter_turns': 0,
      },
    ],
    'observations': <Json>[
      <String, dynamic>{
        'observation_id': 'o1',
        'model_id': 'Reading A',
        'region_id': 'r1',
        'literal_text': 'Chicago 1912',
      },
      <String, dynamic>{
        'observation_id': 'o2',
        'model_id': 'Reading B',
        'region_id': 'r1',
        'literal_text': 'Chicago 1917',
      },
    ],
    'disagreements': <Json>[
      <String, dynamic>{
        'region_id': 'r1',
        'alternatives': <String>['1912', '1917'],
        'resolved': false,
      },
    ],
    'fields': <Json>[
      <String, dynamic>{
        'field_key': 'country',
        'display_name': 'Country',
        'required': true,
        'state': 'supported',
        'literal_value': 'U.S.A.',
        'parsed_value': 'United States',
        'normalized_value': 'United States of America',
      },
      <String, dynamic>{
        'field_key': 'collectors',
        'display_name': 'Collectors',
        'required': true,
        'state': 'unknown',
        'literal_value': null,
      },
      <String, dynamic>{
        'field_key': 'habitat',
        'display_name': 'Habitat',
        'required': false,
        'state': 'unreadable',
        'literal_value': null,
      },
      <String, dynamic>{
        'field_key': 'elevation_from_m',
        'display_name': 'Elevation from',
        'required': false,
        'state': 'not_present',
        'literal_value': null,
      },
    ],
    'validation_findings': <Json>[
      <String, dynamic>{
        'field_key': 'collectors',
        'message': 'A supported collector is required',
        'severity': 'hard',
      },
    ],
    'audit_events': <Json>[
      <String, dynamic>{
        'action': 'intake',
        'actor_id': 'operator-1',
        'created_at': '2026-09-07T10:00:00Z',
      },
      <String, dynamic>{
        'action': 'transcribe',
        'actor_id': 'system',
        'created_at': '2026-09-07T10:04:00Z',
      },
    ],
  });
}

/// The same record, on a photograph whose display transform is known.
///
/// The default fixture carries an original with no verified orientation,
/// which is the honest majority case and the one the workbench refuses to
/// draw overlays on. This variant is the other half of the contract: a
/// decoded derivative, so the label regions are drawn over the pixels and can
/// be reached by number.
Specimen goldenVerifiedSpecimen() {
  final Specimen base = goldenSpecimen();
  final Json asset = Json.from(base.assets.first)
    ..['preview_is_derivative'] = true
    ..['pixel_basis'] = 'original_pixel_edges'
    ..['view_derivative'] = <String, dynamic>{
      'transform': <String, dynamic>{
        // The identity transform: the derivative is the original's own grid,
        // so an overlay coordinate needs no correction.
        'matrix': <num>[1, 0, 0, 0, 1, 0],
        'original_width': 1000,
        'view_width': 1000,
        'view_height': 520,
      },
    };
  return Specimen(<String, dynamic>{
    ...base.data,
    'assets': <Json>[asset],
  });
}

/// The repository every golden reads. It answers the one rich record above and
/// nothing else, so a golden never depends on the order a set iterated in.
class GoldenRepository extends TestRepository {
  GoldenRepository() : record = goldenSpecimen();

  /// A repository whose record carries a verified derivative, so the label
  /// regions are drawn on the photograph.
  GoldenRepository.verified() : record = goldenVerifiedSpecimen();

  /// The record the queue lists and the workbench opens.
  final Specimen record;

  @override
  Future<List<Specimen>> specimens(
    CollectionScope scope, {
    String query = '',
    String status = '',
  }) async => <Specimen>[record];

  @override
  Future<SpecimenPage> specimenPage(
    CollectionScope scope, {
    Map<String, String> filters = const <String, String>{},
    String? cursor,
  }) async => SpecimenPage(<Specimen>[record]);

  @override
  Future<Specimen> specimen(CollectionScope scope, String id) async => record;

  @override
  Future<HistoryPage> historyPage(
    CollectionScope scope,
    String id, {
    required int throughRevision,
    int afterRevision = 0,
  }) async => HistoryPage(
    items: <Json>[
      <String, dynamic>{
        'revision': throughRevision,
        'action': 'transcribe',
        'actor_id': 'system',
        'created_at': '2026-09-07T10:04:00Z',
      },
    ],
    throughRevision: throughRevision,
  );
}

/// The queue location for the fixture collection.
String get goldenQueueLocation =>
    AppRoutes.queueOf(encodeCollectionKey(goldenCollection));

/// The intake location for the fixture collection.
String get goldenIntakeLocation =>
    AppRoutes.intakeOf(encodeCollectionKey(goldenCollection));

/// The record location for the fixture collection.
String get goldenSpecimenLocation => AppRoutes.specimenOf(
  encodeCollectionKey(goldenCollection),
  goldenSpecimenId,
);

/// Pumps the whole app at one window, one theme and one text scale.
Future<void> pumpGoldenApp(
  WidgetTester tester, {
  required Size window,
  required Brightness brightness,
  double textScale = 1.0,
  String location = AppRoutes.setup,
  bool signedIn = true,
  GoldenRepository? repository,
}) async {
  tester.view.devicePixelRatio = 1;
  tester.view.physicalSize = window;
  tester.platformDispatcher.platformBrightnessTestValue = brightness;
  tester.platformDispatcher.textScaleFactorTestValue = textScale;
  addTearDown(tester.view.reset);
  addTearDown(tester.platformDispatcher.clearPlatformBrightnessTestValue);
  addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);

  final TestSession session = TestSession(signedIn: signedIn);
  addTearDown(session.controller.close);
  await tester.pumpWidget(
    SpecimenDigitizationApp(
      session: session,
      repository: repository ?? GoldenRepository(),
      initialLocation: location,
      // In memory, so no golden reaches the platform preference store and
      // every capture starts from the same motion setting.
      motionPreferences: MemoryMotionPreferenceStore(),
    ),
  );
  await tester.pumpAndSettle();
  await settleImages(tester);
}

/// Decodes every `Image` on screen, so a golden shows the photograph rather
/// than the empty box a fake-async frame leaves behind.
Future<void> settleImages(WidgetTester tester) async {
  final Finder images = find.byType(Image);
  if (images.evaluate().isEmpty) return;
  final BuildContext context = tester.element(images.first);
  final List<ImageProvider<Object>> providers = tester
      .widgetList<Image>(images)
      .map((Image image) => image.image)
      .toList();
  await tester.runAsync(() async {
    for (final ImageProvider<Object> provider in providers) {
      await precacheImage(provider, context);
    }
  });
  await tester.pumpAndSettle();
}

/// The two label regions the region editor golden edits.
const List<Json> goldenRegions = <Json>[
  <String, dynamic>{
    'region_id': 'r1',
    'bbox': <int>[40, 40, 460, 220],
    'order': 0,
    'rotation_quarter_turns': 0,
  },
  <String, dynamic>{
    'region_id': 'r2',
    'bbox': <int>[520, 260, 940, 470],
    'order': 1,
    'rotation_quarter_turns': 0,
  },
];

/// An asset the workbench would allow region correction on: a decoded
/// derivative whose display transform is known, which is the state the
/// blueprint requires before a coordinate may be edited.
Json goldenEditableAsset() => <String, dynamic>{
  'asset_id': 'golden-asset',
  'width': 1000,
  'height': 520,
  'pixel_basis': 'original_pixel_edges',
  'preview_bytes': goldenPreviewBytes,
};

/// Pumps one dialog on the product theme, the way the app opens it.
Future<void> pumpGoldenDialog(
  WidgetTester tester, {
  required Size window,
  required Brightness brightness,
  required Widget dialog,
}) async {
  tester.view.devicePixelRatio = 1;
  tester.view.physicalSize = window;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(
    MaterialApp(
      debugShowCheckedModeBanner: false,
      theme: brightness == Brightness.dark ? AppTheme.dark() : AppTheme.light(),
      home: Builder(
        builder: (BuildContext context) => Scaffold(
          body: TextButton(
            onPressed: () => unawaited(
              showDialog<void>(
                context: context,
                builder: (BuildContext _) => dialog,
              ),
            ),
            child: const Text('Open'),
          ),
        ),
      ),
    ),
  );
  await tester.tap(find.text('Open'));
  await tester.pumpAndSettle();
  await settleImages(tester);
}

/// Where a golden for [name] lives.
///
/// One flat directory of PNGs named `screen__window__theme__scale`, so a
/// reviewer scanning the directory sees the matrix without opening anything.
String goldenPath(String name) => 'images/$name.png';

/// Matches the whole app against the golden named [name].
Future<void> expectGolden(WidgetTester tester, String name) =>
    expectGoldenFinder(tester, find.byType(SpecimenDigitizationApp), name);

/// Matches [target] against the golden named [name].
Future<void> expectGoldenFinder(
  WidgetTester tester,
  Finder target,
  String name,
) async {
  await expectLater(target, matchesGoldenFile(goldenPath(name)));
  await tester.pumpWidget(const SizedBox());
}
