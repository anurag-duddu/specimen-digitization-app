/// What the server measured about the photograph, and what it classified the
/// record as (screen blueprints, 6.4).
///
/// Every measurement is named with its unit, every caveat says what it does
/// not prove, and a correction says what it will replace before it is made.
library;

import 'package:flutter/widgets.dart';
import 'package:specimen_ui/specimen_ui.dart';

import 'administrator_contact.dart';
import 'models.dart';
import 'vocabulary.dart';
import 'widgets/widgets.dart';

/// Reads [value] as a JSON object, or an empty one where it is not.
Json objectOf(Object? value) =>
    value is Map ? Map<String, dynamic>.from(value) : {};

/// The image check and the classification, each in its own pane.
class ReviewContext extends StatelessWidget {
  const ReviewContext({super.key, required this.specimen});

  final Specimen specimen;

  /// The two headings, fixed so the panes and their tests agree on them.
  static const String imageHeading = 'Server image check';
  static const String classificationHeading = 'Classification and profile';

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final run = objectOf(specimen.data['run']);
    final classification = objectOf(run['classification']);
    final profile = objectOf(run['profile_snapshot']);
    final asset = specimen.assets.firstOrNull ?? {};
    final quality = objectOf(asset['quality_diagnostics']);
    final metrics = objectOf(quality['metrics']);
    final TextStyle line = ui.type.bodySmall.copyWith(
      color: ui.color.inkSecondary,
    );

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (quality.isNotEmpty)
          _Pane(
            heading: imageHeading,
            children: [
              Text(
                '${vocabularyLabel(textOf(quality['status']))} · ${quality['width']} × ${quality['height']} pixels',
                style: line,
              ),
              if (metrics.isNotEmpty) ...[
                Text(
                  'Brightness ${metrics['mean_luminance']} · Contrast ${metrics['contrast_stddev']}',
                  style: line,
                ),
                Text(
                  'Detail signal ${metrics['mean_neighbor_gradient']} · ${textOf(metrics['algorithm_version'])}',
                  style: line,
                ),
                const CaveatText(
                  label: 'Not calibrated',
                  why:
                      'A readable image does not prove the labels are legible '
                      'or that all of them are in frame.',
                ),
              ],
              for (final issue in quality['issues'] as List? ?? [])
                Text('• ${vocabularyLabel(issue.toString())}', style: line),
              for (final limitation in quality['limitations'] as List? ?? [])
                Text(
                  limitation == 'no_heic_or_raw_decoder' &&
                          asset['processing_derivative'] is Map
                      ? 'Quality measurements use the decoded preview. This measurement stage does not decode HEIC or RAW itself.'
                      : vocabularyLabel(limitation.toString()),
                  style: line,
                ),
              EvidenceDrawer(
                title: 'Image measurements and orientation',
                payload: quality,
              ),
            ],
          ),
        if (classification.isNotEmpty || profile.isNotEmpty)
          _Pane(
            heading: classificationHeading,
            children: [
              if (classification.isNotEmpty) ...[
                Text(
                  '${vocabularyLabel(textOf(classification['status']))} · ${vocabularyLabel(textOf(classification['reason']))}',
                  style: line,
                ),
                Text(
                  classification['synthetic'] == true
                      ? 'Test classifier output'
                      : 'Classifier output',
                  style: line,
                ),
                if (classification['calibration_version'] == null)
                  const CaveatText(
                    label: 'Not calibrated',
                    why:
                        'Scores order the queue. They are not a measure of '
                        'whether a reading is correct.',
                  )
                else
                  Text(
                    'Calibration ${classification['calibration_version']}',
                    style: line,
                  ),
                for (final candidate in objects(classification['candidates']))
                  Padding(
                    padding: EdgeInsetsDirectional.symmetric(
                      vertical: ui.space.s1,
                    ),
                    child: Text(
                      '${candidate['collection_id']} · Score ${candidate['score']}\n${(candidate['reasons'] as List? ?? []).map((v) => vocabularyLabel(v.toString())).join(', ')}',
                      style: line,
                    ),
                  ),
                EvidenceDrawer(
                  title: 'Classification provenance',
                  payload: classification,
                ),
              ],
              if (profile.isNotEmpty) ...[
                Text(
                  'Profile ${profile['id']} · Version ${profile['version']}',
                  style: line,
                ),
                Text(
                  'Schema ${profile['schema_version']} · Policy ${profile['clearance_policy']}',
                  style: line,
                ),
                Text(
                  profile['institutional_policy_approved'] == true
                      ? 'Profile policy approved in this environment'
                      : 'Institutional policy approval is missing',
                  style: line,
                ),
                Text(
                  profile['semantics_confirmed'] == true
                      ? 'Field semantics confirmed in this environment'
                      : 'Required field semantics are not confirmed',
                  style: line,
                ),
                EvidenceDrawer(
                  title: 'Pinned profile dependencies and field rules',
                  payload: profile,
                ),
              ],
              if (run['classification_selection'] != null)
                EvidenceDrawer(
                  title: 'Recorded classification decision',
                  payload: run['classification_selection'],
                ),
              Text(
                'A correction starts a new run and replaces the results that '
                'depend on it. Earlier records stay in history.',
                style: ui.type.body,
              ),
            ],
          ),
      ],
    );
  }
}

/// One headed pane of the review context.
class _Pane extends StatelessWidget {
  const _Pane({required this.heading, required this.children});

  final String heading;
  final List<Widget> children;

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    return Padding(
      padding: EdgeInsetsDirectional.only(bottom: ui.space.s4),
      child: Surface(
        radius: ui.shape.tile,
        hairline: true,
        padding: EdgeInsetsDirectional.all(ui.space.s4),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          mainAxisSize: MainAxisSize.min,
          children: [
            Semantics(
              container: true,
              header: true,
              child: Text(heading, style: ui.type.title),
            ),
            SizedBox(height: ui.space.s1),
            ...children,
          ],
        ),
      ),
    );
  }
}

/// Opens the classification correction form.
Future<Json?> showClassificationForm(
  BuildContext context, {
  required Specimen specimen,
  required CollectionScope scope,
}) => showAdaptiveModal<Json>(
  context,
  title: ClassificationDialog.title,
  body: (BuildContext formContext) =>
      ClassificationDialog(specimen: specimen, scope: scope),
);

/// The classification correction form.
///
/// Exposed as a widget rather than a route so it can be pumped and reviewed
/// on its own; [showClassificationForm] is how a screen opens it.
class ClassificationDialog extends StatefulWidget {
  const ClassificationDialog({
    super.key,
    required this.specimen,
    required this.scope,
  });

  final Specimen specimen;
  final CollectionScope scope;

  /// The form's own title.
  static const String title = 'Correct classification?';

  /// The commit control.
  static const String action = 'Correct classification';

  /// The field that names the classification.
  static const String nodeLabel = 'Classification';

  /// What the form says when the collection published none.
  static const String noNodes =
      'No classifications were returned. Refresh collection access, or ask '
      'the person named below.';

  /// Why the commit control is unavailable without one.
  static const String noNodesReason =
      'This collection published no classification to choose';

  @override
  State<ClassificationDialog> createState() => _ClassificationDialogState();
}

class _ClassificationDialogState extends State<ClassificationDialog> {
  final _reason = TextEditingController();
  String? _node;
  String? _nodeError;
  String? _reasonError;

  @override
  void dispose() {
    _reason.dispose();
    super.dispose();
  }

  void _save() {
    final String? node = _node;
    final String reason = _reason.text.trim();
    setState(() {
      _nodeError = node == null ? 'Choose a classification.' : null;
      _reasonError = reason.isEmpty ? reasonRequired : null;
    });
    if (node == null || reason.isEmpty) return;
    Navigator.pop(context, <String, dynamic>{
      'kind': 'classification_correction',
      'value': widget.scope.collectionId,
      'profile_collection_id': node,
      'reason': reason,
    });
  }

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final nodes = objects(widget.scope.configuration['classification_nodes']);
    final profiles = objects(widget.scope.configuration['profiles']);
    final matching = profiles
        .where((p) => p['collection_id'] == _node)
        .toList();
    final TextStyle line = ui.type.bodySmall.copyWith(
      color: ui.color.inkSecondary,
    );

    return SingleChildScrollView(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(
            'Authorized collection: ${widget.scope.name}',
            style: ui.type.body,
          ),
          Text(
            'Choose the classification that resolves a published profile. '
            'The record stays in this collection.',
            style: line,
          ),
          SizedBox(height: ui.space.s3),
          if (nodes.isEmpty) ...<Widget>[
            Text(ClassificationDialog.noNodes, style: ui.type.body),
            const AdministratorContactLine(),
            SizedBox(height: ui.space.s3),
          ],
          UiSelect<String>(
            label: ClassificationDialog.nodeLabel,
            placeholder: ClassificationDialog.nodeLabel,
            value: _node,
            errorText: _nodeError,
            options: <UiSelectOption<String>>[
              for (final n in nodes)
                UiSelectOption<String>(
                  value: n['id'].toString(),
                  label: textOf(n['name'], n['id'].toString()),
                ),
            ],
            onChanged: (String? value) => setState(() {
              _node = value;
              _nodeError = null;
            }),
          ),
          for (final profile in matching)
            Text(
              'Profile ${profile['id']} · ${profile['version']} · ${profile['state']}',
              style: line,
            ),
          if (_node != null && matching.isEmpty)
            Text(
              'No published profile is shown for this classification. The '
              'server will ask for review if it cannot map one.',
              style: line,
            ),
          SizedBox(height: ui.space.s3),
          Text(
            'A new run replaces the results that depend on the profile. '
            'Earlier evidence and decisions stay in history.',
            style: ui.type.body,
          ),
          SizedBox(height: ui.space.s3),
          UiTextArea(
            label: 'Reason',
            helpText: reasonHelperText,
            errorText: _reasonError,
            controller: _reason,
            minLines: _reasonMinLines,
            maxLines: _reasonMaxLines,
            onChanged: (String _) {
              if (_reasonError != null) setState(() => _reasonError = null);
            },
          ),
          SizedBox(height: ui.space.s6),
          UiButtonRow(
            primary: UiButton(
              label: ClassificationDialog.action,
              disabledReason: ClassificationDialog.noNodesReason,
              onPressed: nodes.isEmpty ? null : _save,
            ),
            secondary: UiButton(
              label: 'Cancel',
              variant: UiButtonVariant.ghost,
              onPressed: () => Navigator.pop(context),
            ),
          ),
        ],
      ),
    );
  }

  static const int _reasonMinLines = 2;
  static const int _reasonMaxLines = 4;
}
