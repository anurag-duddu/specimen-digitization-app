/// Local synthetic previews of the populated reading inspector.
///
/// No application code imports this fixture and no server is contacted.
library;

import 'package:flutter/widget_previews.dart';
import 'package:flutter/widgets.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../../models.dart';
import '../../widgets/previews.dart' show previewThemes;
import 'readings_panel.dart';

/// Two readings and one disagreement within the previewer's current bounds.
@Preview(
  name: 'Readings · synthetic · light',
  group: 'Review workspace',
  theme: previewThemes,
  brightness: Brightness.light,
)
@Preview(
  name: 'Readings · synthetic · dark',
  group: 'Review workspace',
  theme: previewThemes,
  brightness: Brightness.dark,
)
Widget readingsInspectorPreview() => Builder(
  builder: (BuildContext context) => UiScaffold(
    sky: SkyPreset.none,
    body: SingleChildScrollView(
      padding: EdgeInsetsDirectional.all(context.ui.space.s5),
      child: WorkbenchReadings(
        specimen: Specimen(<String, dynamic>{
          'specimen_id': 'synthetic-inspector-preview',
          'revision': 1,
          'regions': <Json>[
            <String, dynamic>{'region_id': 'preview-label'},
          ],
          'observations': <Json>[
            <String, dynamic>{
              'id': 'preview-a',
              'region_id': 'preview-label',
              'model_id': 'Synthetic reader A',
              'provider': 'Fixture provider',
              'literal_text': 'FIELD MUSEUM\nChicago, Illinois\n12 July 1912',
              'latency_seconds': 1.4,
            },
            <String, dynamic>{
              'id': 'preview-b',
              'region_id': 'preview-label',
              'model_id': 'Synthetic reader B',
              'provider': 'Fixture provider',
              'literal_text': 'FIELD MUSEUM\nChicago, Illinois\n12 July 1913',
            },
          ],
          'disagreements': <Json>[
            <String, dynamic>{
              'region_id': 'preview-label',
              'alternatives': <String>['12 July 1912', '12 July 1913'],
            },
          ],
        }),
        anchors: <String, GlobalKey>{},
        selectedRegionId: 'preview-label',
        onSelectRegion: (_) {},
        onChange: (_) async {},
        transcriptionBlockedReason: 'Synthetic preview is read only',
        declarationsBlocked: true,
      ),
    ),
  ),
);
