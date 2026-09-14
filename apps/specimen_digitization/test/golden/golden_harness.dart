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
import 'package:specimen_digitization/src/sources.dart';
import 'package:specimen_digitization/src/theme/app_theme.dart';
import 'package:specimen_digitization/src/theme/icons.dart';
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

/// The registered sources for the fixture collection.
String get goldenSourcesLocation =>
    AppRoutes.sourcesOf(encodeCollectionKey(goldenCollection));

/// One registered source in the fixture collection.
String get goldenSourceLocation =>
    AppRoutes.sourceOf(encodeCollectionKey(goldenCollection), 'src-1');

/// The record location for the fixture collection.
String get goldenSpecimenLocation => goldenSpecimenLocationOf(goldenSpecimenId);

/// The location of one record in the fixture collection.
String goldenSpecimenLocationOf(String id) =>
    AppRoutes.specimenOf(encodeCollectionKey(goldenCollection), id);

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

/// The narrowest window that gets the dialog form of a surface.
///
/// `WindowClass.expanded` starts at 840; every surface in this product that
/// chooses between a dialog and a full screen route chooses on that number.
const double expandedWindowFloor = 840;

/// Pumps one full screen route on the product theme, the way the app pushes
/// it below the expanded breakpoint.
Future<void> pumpGoldenRoute(
  WidgetTester tester, {
  required Size window,
  required Brightness brightness,
  required Widget child,
}) async {
  tester.view.devicePixelRatio = 1;
  tester.view.physicalSize = window;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(
    MaterialApp(
      debugShowCheckedModeBanner: false,
      theme: brightness == Brightness.dark ? AppTheme.dark() : AppTheme.light(),
      home: child,
    ),
  );
  await tester.pumpAndSettle();
  await settleImages(tester);
}

/// Why a golden comparison does not run away from a macOS host.
///
/// The PNGs in `test/golden/images/` are generated on macOS. A Linux CI
/// runner draws the same widget tree with the same deterministic test font but
/// antialiases it differently, which moves 1 to 4 percent of the pixels in
/// about half the files: a real difference in bytes and no difference at all
/// in what the golden is evidence of. Comparing them there reports failures
/// nobody can act on and hides the ones that matter.
///
/// Everything else in this suite still runs on every platform. In particular
/// the overflow assertions in `size_classes_golden_test.dart`, the semantics
/// fixtures and the keyboard walkthrough are layout and semantics checks
/// rather than pixel checks, and they are the ones that carry the findings.
const String goldenPlatformSkip =
    'Goldens are generated on macOS; Linux font rendering differs by 1 to 4 '
    'percent';

/// True where a golden comparison is meaningful.
bool get goldensCompare => Platform.isMacOS;

/// Where a golden for [name] lives.
///
/// One flat directory of PNGs named `screen__window__theme__scale`, so a
/// reviewer scanning the directory sees the matrix without opening anything.
String goldenPath(String name) => 'images/$name.png';

/// Matches the whole app against the golden named [name].
Future<void> expectGolden(WidgetTester tester, String name) =>
    expectGoldenFinder(tester, find.byType(SpecimenDigitizationApp), name);

/// Matches [target] against the golden named [name].
///
/// Off a macOS host the comparison is skipped rather than failed, for the
/// reason in [goldenPlatformSkip]. The test still built the screen, so every
/// other assertion in it, including the overflow check, has already run.
Future<void> expectGoldenFinder(
  WidgetTester tester,
  Finder target,
  String name,
) async {
  if (!goldensCompare) {
    markTestSkipped('$name: $goldenPlatformSkip');
    await tester.pumpWidget(const SizedBox());
    return;
  }
  await expectLater(target, matchesGoldenFile(goldenPath(name)));
  await tester.pumpWidget(const SizedBox());
}

/// The records the queue answers when a test moves between specimens.
///
/// Built from [goldenVerifiedSpecimen] so every one of them draws the same
/// rich record, with only the identifier and the name changing: the point of
/// these is the order they are in, not what is on them.
List<Specimen> goldenQueue(int count) => <Specimen>[
  for (int i = 1; i <= count; i++)
    Specimen(<String, dynamic>{
      ...goldenVerifiedSpecimen().data,
      'specimen_id': 'fixture-00$i',
      'display_name': 'Pinned beetle $i',
    }),
];

/// A repository whose queue holds more than one record.
class GoldenQueueRepository extends GoldenRepository {
  GoldenQueueRepository(this.records) : super.verified();

  /// The queue, in the order the list shows it.
  final List<Specimen> records;

  @override
  Future<List<Specimen>> specimens(
    CollectionScope scope, {
    String query = '',
    String status = '',
  }) async => records;

  @override
  Future<SpecimenPage> specimenPage(
    CollectionScope scope, {
    Map<String, String> filters = const <String, String>{},
    String? cursor,
  }) async => SpecimenPage(records);

  @override
  Future<Specimen> specimen(CollectionScope scope, String id) async =>
      records.where((Specimen record) => record.id == id).firstOrNull ??
      records.first;
}

/// The boundary a component golden captures.
///
/// A component is captured at its own size rather than at the window's, so
/// the canvas can be made tall enough for 200 percent text without every
/// golden gaining a field of empty pixels below the content. The boundary is
/// explicit because `matchesGoldenFile` captures the nearest repaint boundary
/// above the finder it is given, and for a plain `Column` that is the whole
/// window.
const Key goldenComponentKey = ValueKey<String>('golden-component');

/// The canvas a component golden is drawn on.
///
/// Deliberately taller than any sheet needs. Nothing inside
/// [goldenComponentKey] may be clipped, and a component that overflows this
/// canvas fails its test rather than being captured half drawn: `testWidgets`
/// fails on the layout error, which is the same gate
/// `size_classes_golden_test.dart` installs a collector for.
const Size goldenComponentCanvas = Size(900, 4200);

/// Pumps one component on the product theme, at a fixed measure.
///
/// The third entry point into this suite, beside [pumpGoldenApp] for a screen
/// and [pumpGoldenDialog] / [pumpGoldenRoute] for a surface the app opens. A
/// component that a screen golden cannot reach needs one of its own: see
/// `diff_text_golden_test.dart` for why the reading comparison is such a
/// component.
///
/// [measure] is the width the component is given, because a component has no
/// window class of its own. What decides its layout is the measure its
/// container hands it, so that is the axis these goldens vary.
///
/// The product surface is painted inside the boundary rather than around it.
/// A `RepaintBoundary` composites only its own subtree, so a capture that
/// leaves the surface to the `Scaffold` behind it records marked runs against
/// transparency, and a fill or an underline token is then evidence of
/// nothing.
Future<void> pumpGoldenComponent(
  WidgetTester tester, {
  required Brightness brightness,
  required double measure,
  required Widget child,
  double textScale = 1.0,
}) async {
  tester.view.devicePixelRatio = 1;
  tester.view.physicalSize = goldenComponentCanvas;
  tester.platformDispatcher.textScaleFactorTestValue = textScale;
  addTearDown(tester.view.reset);
  addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);

  await tester.pumpWidget(
    MaterialApp(
      debugShowCheckedModeBanner: false,
      theme: brightness == Brightness.dark ? AppTheme.dark() : AppTheme.light(),
      home: Scaffold(
        body: Align(
          alignment: AlignmentDirectional.topStart,
          child: Builder(
            builder: (BuildContext context) => RepaintBoundary(
              key: goldenComponentKey,
              child: ColoredBox(
                color: Theme.of(context).colorScheme.surface,
                child: Padding(
                  padding: EdgeInsets.all(context.space.space4),
                  child: SizedBox(width: measure, child: child),
                ),
              ),
            ),
          ),
        ),
      ),
    ),
  );
  await tester.pumpAndSettle();
}

/// Matches the component under [goldenComponentKey] against [name].
Future<void> expectGoldenComponent(WidgetTester tester, String name) =>
    expectGoldenFinder(tester, find.byKey(goldenComponentKey), name);

/// The repository the source goldens read.
///
/// One snapshot with a page of rows in each of the three states, so a golden
/// shows the chip vocabulary rather than one row repeated.
class GoldenSourceRepository extends GoldenRepository
    implements SourceRepository {
  GoldenSourceRepository();

  /// The snapshot, in order.
  static final List<SourceObject> rows = <SourceObject>[
    _row('subject_105526321.jpg'),
    _row('subject_105526322.jpg'),
    _row(
      'subject_105526323.jpg',
      state: 'imported',
      specimenId: goldenSpecimenId,
    ),
    _row('field_notes_1946.tiff', mediaType: 'image/tiff'),
    _row('catalogue.pdf', state: 'unsupported_media_type', mediaType: 'application/pdf'),
  ];

  static SourceObject _row(
    String name, {
    String state = 'available',
    String mediaType = 'image/jpeg',
    String? specimenId,
  }) => SourceObject(<String, dynamic>{
    'bucket': 'specimen-digitization.firebasestorage.app',
    'object_name': 'microscopic-slides/$name',
    'generation': '1757000000000001',
    'sha256': 'sha-$name',
    'size_bytes': 312000,
    'media_type': mediaType,
    'state': state,
    'specimen_id': specimenId,
  });

  @override
  Future<List<RegisteredSource>> sources(CollectionScope scope) async =>
      <RegisteredSource>[
        RegisteredSource(<String, dynamic>{
          'source_id': 'src-1',
          'collection_id': scope.collectionId,
          'bucket': 'specimen-digitization.firebasestorage.app',
          'prefix': 'microscopic-slides/',
          'media_types': <String>['image/jpeg', 'image/png', 'image/tiff'],
          'registered_by': 'administrator',
          'registered_at': '2026-09-14T10:22:00Z',
          'inventory': <String, dynamic>{
            'inventory_id': 'inv-1',
            'object_count': 1000,
            'captured_at': '2026-09-14T10:22:00Z',
          },
        }),
      ];

  @override
  Future<SourceObjectPage> sourceObjectPage(
    CollectionScope scope,
    String sourceId, {
    Map<String, String> filters = const <String, String>{},
    String? cursor,
  }) async => SourceObjectPage(
    rows,
    inventoryId: 'inv-1',
    capturedAt: DateTime.utc(2026, 9, 14, 10, 22),
    objectCount: 1000,
    matchingCount: 1000,
  );

  @override
  Future<SourceImportResult> importFromSource(
    CollectionScope scope,
    String sourceId,
    List<SourceObject> selection,
    String key, {
    bool sensitive = true,
  }) async => SourceImportResult(const <String, dynamic>{
    'requested': 0,
    'imported': 0,
    'duplicates': 0,
    'items': <Map<String, dynamic>>[],
  });
}
