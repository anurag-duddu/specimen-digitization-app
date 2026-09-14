/// Widget previews for the shared component library.
///
/// `package:flutter/widget_previews.dart` resolves on Flutter 3.38.5, so
/// these are real previews, viewable with `flutter widget-preview start`.
/// They exist so a component can be looked at in both themes without running
/// the application against a server.
///
/// Nothing in the product imports this file.
library;

import 'package:flutter/material.dart';
import 'package:flutter/widget_previews.dart';
import 'package:material_symbols_icons/symbols.dart';

import '../theme/app_theme.dart';
import 'widgets.dart';

/// Both product themes, for the preview harness. Public because the preview
/// annotation only accepts literals and public symbols.
PreviewThemeData previewThemes() => PreviewThemeData(
  materialLight: AppTheme.light(),
  materialDark: AppTheme.dark(),
);

Widget _surface(Widget child) => Builder(
  builder: (BuildContext context) => Scaffold(
    body: Padding(padding: const EdgeInsets.all(16), child: child),
  ),
);

/// Every status the client renders, light.
@Preview(name: 'Status chips', group: 'Atoms', theme: previewThemes)
Widget statusChips() => _surface(
  SingleChildScrollView(
    child: Wrap(
      spacing: 8,
      runSpacing: 8,
      children: <Widget>[
        for (final SpecimenStatus status in SpecimenStatus.values)
          StatusChip(status),
      ],
    ),
  ),
);

/// The environment band.
@Preview(name: 'Environment banner', group: 'Atoms', theme: previewThemes)
Widget environmentBanner() =>
    _surface(const EnvironmentBanner(environment: 'synthetic'));

/// A caveat, closed.
@Preview(name: 'Caveat', group: 'Atoms', theme: previewThemes)
Widget caveat() => _surface(
  const CaveatText(
    label: 'Not calibrated',
    body:
        'A risk score orders the queue. It is not a probability that the '
        'record is wrong.',
  ),
);

/// Loading placeholders.
@Preview(name: 'Skeletons', group: 'Atoms', theme: previewThemes)
Widget skeletons() => _surface(
  const Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: <Widget>[
      SkeletonBlock(),
      SizedBox(height: 16),
      SkeletonRow(),
      LoadingAnnouncement(thing: 'queue', visible: true),
    ],
  ),
);

/// The empty state pattern.
@Preview(name: 'Empty state', group: 'Molecules', theme: previewThemes)
Widget emptyState() => _surface(
  EmptyState(
    icon: Symbols.inbox,
    title: 'No specimens yet',
    body: 'Upload a photograph to create the first record.',
    actionLabel: 'Add photographs',
    onAction: () {},
  ),
);

/// A reading against a reference reading.
@Preview(name: 'Reading card', group: 'Organisms', theme: previewThemes)
Widget readingCard() => _surface(
  const ReadingCard(
    modelName: 'Synthetic reading B',
    provider: 'Fixture provider',
    literal: 'Chicago 1913',
    reference: 'Chicago 1912',
  ),
);

/// A field with all three layers.
@Preview(name: 'Field row', group: 'Organisms', theme: previewThemes)
Widget fieldRow() => _surface(
  const FieldRow(
    name: 'Locality',
    state: SpecimenStatus.ambiguous,
    required: true,
    asWritten: 'Chicago, Ills.',
    readAs: 'Chicago, Illinois',
    standardized: 'Chicago, Illinois, United States',
    authority: 'Matched in the gazetteer, accepted name',
  ),
);

/// One queue row, measured and calibrated.
@Preview(name: 'Queue row', group: 'Organisms', theme: previewThemes)
Widget queueRow() => _surface(
  QueueRow(
    id: 'fixture-001',
    title: 'FMNH-0001',
    reason: 'Two readings disagree on the locality',
    status: SpecimenStatus.needsReview,
    riskComposite: 62,
    riskComponents: const <String>['Reading disagreement, weight 0.4'],
    riskCalibrated: false,
    updatedAt: DateTime(2026, 9, 13, 14, 32),
    now: DateTime(2026, 9, 14, 9),
    onOpen: () {},
  ),
);

/// The risk meter, measured and unmeasured.
@Preview(name: 'Risk meter', group: 'Organisms', theme: previewThemes)
Widget riskMeter() => _surface(
  Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: <Widget>[
      RiskMeter(
        composite: 62,
        components: const <String>['Reading disagreement, weight 0.4'],
        calibrated: false,
      ),
      const SizedBox(height: 24),
      RiskMeter(
        composite: null,
        components: const <String>[],
        status: 'unmeasured',
      ),
    ],
  ),
);

/// One file on its way into a collection.
@Preview(name: 'Upload item', group: 'Organisms', theme: previewThemes)
Widget uploadItem() => _surface(
  const UploadItem(
    name: 'IMG_4821.jpg',
    state: UploadState.uploading,
    sizeBytes: 4200000,
    pixelWidth: 6000,
    pixelHeight: 4000,
    progress: 0.42,
  ),
);
