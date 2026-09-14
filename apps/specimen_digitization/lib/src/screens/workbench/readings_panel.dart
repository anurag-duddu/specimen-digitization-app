/// The readings segment (screen blueprints, 6.3).
///
/// Two readings are two readings. Each is a `ReadingCard` carrying a
/// `DiffText` against the other reading for its region, so the difference is
/// quantified in a sentence and marked with an underline and a symbol, never
/// with colour alone. Resolving one opens a form that keeps both readings on
/// screen beside the field (audit finding H6.2).
library;

import 'package:flutter/material.dart';
import 'package:material_symbols_icons/symbols.dart';

import '../../models.dart';
import '../../reading_alignment.dart';
import '../../reading_declarations.dart';
import '../../review_context.dart';
import '../../risk_assessment.dart';
import '../../evidence_panel.dart';
import '../../theme/icons.dart';
import '../../vocabulary.dart';
import '../../widgets/widgets.dart';
import 'evidence_picker.dart';

/// The width below which two reading cards stack instead of sitting side by
/// side. Two literals need a measure each; below this they get one.
const double readingsSideBySideMin = 520;

/// One model reading's place in the panel, so a region can be scrolled to.
typedef RegionAnchors = Map<String, GlobalKey>;

/// The readings, their comparison, and the controls that resolve them.
class WorkbenchReadings extends StatelessWidget {
  const WorkbenchReadings({
    super.key,
    required this.specimen,
    required this.anchors,
    required this.selectedRegionId,
    required this.onSelectRegion,
    required this.onChange,
    required this.transcriptionBlockedReason,
    required this.declarationsBlocked,
    this.loadArtifact,
  });

  final Specimen specimen;

  /// One key per region, so the blockers list and the source pane can scroll
  /// the reviewer to the right card.
  final RegionAnchors anchors;

  /// The region the source pane is showing.
  final String? selectedRegionId;

  /// Selects a region from a reading card.
  final ValueChanged<String?> onSelectRegion;

  /// Sends one decision.
  final Future<void> Function(Json) onChange;

  /// Why resolving a transcription is unavailable, or null when it is not.
  final String? transcriptionBlockedReason;

  /// True when the server does not permit recording a declaration.
  final bool declarationsBlocked;

  /// Loads a lazily fetched evidence payload.
  final Future<Json> Function(ArtifactRequest)? loadArtifact;

  String _literalOf(Json o) =>
      textOf(o['literal_text'], textOf(o['verbatim_text'], ''));

  /// The position of the first reading recorded for each region.
  ///
  /// Identity is the position, not the text: two models can return the same
  /// characters, and the first reading of a region still has nothing before
  /// it to be compared against.
  Map<String, int> get _referenceIndex {
    final Map<String, int> first = <String, int>{};
    for (final (int i, Json o) in specimen.observations.indexed) {
      final Object? region = o['region_id'];
      if (region is String && region.trim().isNotEmpty) {
        first.putIfAbsent(region, () => i);
      }
    }
    return first;
  }

  String _regionName(Object? regionId) {
    final int index = specimen.regions.indexWhere(
      (Json r) => r['region_id'] == regionId,
    );
    return index < 0 ? 'Unassigned label' : 'Label ${index + 1}';
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final Map<String, int> firstOfRegion = _referenceIndex;
    final Json run = objectOf(specimen.data['run']);
    final List<Json> observations = specimen.observations;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        if (observations.isEmpty)
          const EmptyState(
            icon: Symbols.memory,
            title: 'No readings yet',
            body: 'No model has read this specimen. Refresh to check again.',
          ),
        LayoutBuilder(
          builder: (BuildContext context, BoxConstraints c) {
            final bool sideBySide = c.maxWidth >= readingsSideBySideMin;
            final double cardWidth = sideBySide
                ? (c.maxWidth - context.space.space4) / 2
                : c.maxWidth;
            return Wrap(
              spacing: context.space.space4,
              runSpacing: context.space.space4,
              children: <Widget>[
                for (final (int i, Json o) in observations.indexed)
                  SizedBox(
                    width: cardWidth,
                    child: Builder(
                      builder: (BuildContext context) {
                        // A reading with no region, or the first reading of
                        // its region, has nothing to be compared against.
                        final int? first = firstOfRegion[o['region_id']];
                        final bool isFirst = first == null || first == i;
                        return KeyedSubtree(
                          key: isFirst ? _anchorFor(o['region_id']) : null,
                          child: _card(
                            context,
                            o,
                            isFirst ? null : _literalOf(observations[first]),
                          ),
                        );
                      },
                    ),
                  ),
              ],
            );
          },
        ),
        SizedBox(height: context.space.space6),
        _declarations(context, run),
        SizedBox(height: context.space.space6),
        Text('Differences and resolution', style: theme.textTheme.titleMedium),
        SizedBox(height: context.space.space2),
        _differences(context, run),
      ],
    );
  }

  /// The first card of a region carries that region's anchor.
  GlobalKey? _anchorFor(Object? regionId) {
    if (regionId is! String) return null;
    return anchors[regionId];
  }

  Widget _card(BuildContext context, Json o, String? reference) {
    final String regionName = _regionName(o['region_id']);

    // The region name sits above the card rather than inside its title row:
    // `ReadingCard` lays its model name and provider out in one unwrapped
    // row, so a long pair overflows. The PR asks for the shared component to
    // make its provider flexible.
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        Text(
          regionName,
          style: Theme.of(context).textTheme.labelMedium?.copyWith(
            color: Theme.of(context).colorScheme.onSurfaceVariant,
          ),
        ),
        SizedBox(height: context.space.space1),
        _reading(context, o, reference, regionName),
      ],
    );
  }

  Widget _reading(
    BuildContext context,
    Json o,
    String? reference,
    String regionName,
  ) {
    final String literal = _literalOf(o);
    return ReadingCard(
      modelName: textOf(o['model_id'], 'Model'),
      provider: textOf(o['provider'], 'Not recorded'),
      literal: literal,
      // The first reading of a region has nothing before it to differ from.
      reference: reference,
      selected: selectedRegionId != null && selectedRegionId == o['region_id'],
      executionDetails:
          o.containsKey('latency_seconds') || o.containsKey('completion_state')
          ? ObservationExecutionDetails(observation: o)
          : null,
      footerActions: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          if (o['region_id'] is String)
            Align(
              alignment: AlignmentDirectional.centerStart,
              child: TextButton.icon(
                onPressed: () => onSelectRegion(o['region_id'] as String),
                icon: const Icon(Symbols.crop_free),
                label: Text('Show $regionName on the photograph'),
              ),
            ),
          if (loadArtifact != null && o['raw_ref'] != null)
            LazyEvidence(
              key: ValueKey<String>(
                'raw:${specimen.id}:${specimen.revision}:${o['id']}',
              ),
              label: 'Read raw reading',
              load: () => loadArtifact!(
                ArtifactRequest(
                  ArtifactKind.observationRaw,
                  textOf(o['id'], textOf(o['observation_id'])),
                  sha256: o['raw_sha256'] as String?,
                ),
              ),
              render: (Json raw) =>
                  EvidenceDrawer(title: 'Raw reading response', payload: raw),
            ),
          if (loadArtifact != null &&
              objectOf(
                    objectOf(
                      objectOf(specimen.data['run'])['reading_metadata'],
                    ),
                  )[o['id']] !=
                  null)
            LazyEvidence(
              key: ValueKey<String>(
                'metadata:${specimen.id}:${specimen.revision}:${o['id']}',
              ),
              label: 'Read language and script metadata',
              load: () => loadArtifact!(
                ArtifactRequest(ArtifactKind.readingMetadata, textOf(o['id'])),
              ),
              render: (Json metadata) =>
                  ReadingMetadataView(metadata: metadata),
            ),
          if (loadArtifact != null && o['declaration_evidence'] is Map)
            LazyEvidence(
              key: ValueKey<String>(
                'declaration:${specimen.id}:${specimen.revision}:${o['id']}',
              ),
              label: 'Read declaration provenance',
              load: () => loadArtifact!(
                ArtifactRequest(
                  ArtifactKind.readingDeclarations,
                  textOf(o['id']),
                ),
              ),
              render: (Json value) => ReadingDeclarationView(
                provenance: value,
                onChange: declarationsBlocked ? null : onChange,
              ),
            ),
          EvidenceDrawer(
            title: 'Reading provenance and raw response',
            payload: o,
          ),
        ],
      ),
    );
  }

  Widget _declarations(BuildContext context, Json run) {
    final Object? handling = run['label_language_handling'];
    if (handling is! Map) return const SizedBox.shrink();
    return LabelLanguagePolicy(
      handling: objectOf(handling),
      regionName: _regionName,
      onDeclare: declarationsBlocked
          ? null
          : (String regionId) async {
              final List<Json> forRegion = specimen.observations
                  .where((Json o) => o['region_id'] == regionId)
                  .toList();
              if (forRegion.isEmpty) return;
              final Json? change = await showDeclarationForm(
                context,
                observationId: textOf(
                  forRegion.first['id'],
                  textOf(forRegion.first['observation_id'], ''),
                ),
              );
              if (change != null && context.mounted) await onChange(change);
            },
    );
  }

  Widget _differences(BuildContext context, Json run) {
    final List<Json> transcriptions = objects(specimen.data['transcriptions']);
    final List<Json> disagreements = objects(specimen.data['disagreements']);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        if (loadArtifact != null)
          for (final Json d in objects(run['disagreements']))
            LazyEvidence(
              key: ValueKey<String>(
                'alignment:${specimen.id}:${specimen.revision}:${d['region_id']}',
              ),
              label: 'Read the comparison for ${_regionName(d['region_id'])}',
              load: () => loadArtifact!(
                ArtifactRequest(
                  ArtifactKind.disagreement,
                  textOf(d['region_id']),
                ),
              ),
              render: (Json alignment) {
                String? retained(String side) =>
                    specimen.observations
                            .where(
                              (Json o) =>
                                  o['id'] ==
                                  objectOf(alignment[side])['observation_id'],
                            )
                            .firstOrNull?['literal_text']
                        as String?;
                return ReadingAlignmentView(
                  alignment: alignment,
                  leftText: retained('left'),
                  rightText: retained('right'),
                );
              },
            ),
        if (disagreements.isEmpty && transcriptions.isEmpty)
          const CaveatText(
            label: 'No differences recorded between the readings.',
            why:
                'Agreement between readings does not mean every label was '
                'found.',
          ),
        for (final Json d in disagreements)
          _DifferenceRow(
            title: '${_regionName(d['region_id'])}: the readings differ',
            detail: (d['alternatives'] as List? ?? <Object?>[])
                .map((Object? a) => a.toString())
                .join(' · '),
            payload: d,
          ),
        for (final Json t in transcriptions)
          _DifferenceRow(
            title: t['resolved'] == true
                ? '${_regionName(t['region_id'])}: resolved'
                : '${_regionName(t['region_id'])}: unresolved',
            detail: textOf(t['verbatim_text'], textOf(t['text'], '')),
            payload: t,
            extra: t.containsKey('alignment_status')
                ? TranscriptionComparisonSummary(transcription: t)
                : null,
          ),
        SizedBox(height: context.space.space2),
        Align(
          alignment: AlignmentDirectional.centerStart,
          child: Tooltip(
            message:
                transcriptionBlockedReason ??
                'Record which reading the source supports',
            child: Semantics(
              hint: transcriptionBlockedReason ?? '',
              child: FilledButton.tonalIcon(
                onPressed:
                    transcriptionBlockedReason != null ||
                        specimen.observations.isEmpty
                    ? null
                    : () => _resolve(context),
                icon: const Icon(Symbols.edit_note),
                label: const Text('Resolve transcription'),
              ),
            ),
          ),
        ),
      ],
    );
  }

  Future<void> _resolve(BuildContext context) async {
    final String? regionId =
        selectedRegionId ??
        (specimen.regions.isEmpty
            ? specimen.observations.first['region_id'] as String?
            : specimen.regions.first['region_id'] as String?);
    final List<Json> readings = specimen.observations
        .where((Json o) => o['region_id'] == regionId)
        .toList();
    final Json? change = await showResolveTranscription(
      context,
      regionName: _regionName(regionId),
      regionId: regionId,
      readings: <({String model, String literal})>[
        for (final Json o
            in (readings.isEmpty ? specimen.observations : readings))
          (model: textOf(o['model_id'], 'Model'), literal: _literalOf(o)),
      ],
      choices: evidenceChoices(specimen),
    );
    if (change != null && context.mounted) await onChange(change);
  }
}

class _DifferenceRow extends StatelessWidget {
  const _DifferenceRow({
    required this.title,
    required this.detail,
    required this.payload,
    this.extra,
  });

  final String title;
  final String detail;
  final Json payload;
  final Widget? extra;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return Padding(
      padding: EdgeInsets.only(bottom: context.space.space2),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          Text(title, style: theme.textTheme.titleSmall),
          if (detail.isNotEmpty && detail != 'Not recorded')
            Text(detail, style: context.mono.literalDense),
          ?extra,
          EvidenceDrawer(payload: payload),
        ],
      ),
    );
  }
}

/// Resolves a transcription with both readings visible beside the field.
///
/// Deliberately not a plain reason sheet and deliberately not a modal that
/// hides the pixels: the readings the reviewer is choosing between are on
/// screen the whole time (blueprint 6.3, audit finding H6.2).
Future<Json?> showResolveTranscription(
  BuildContext context, {
  required String regionName,
  required String? regionId,
  required List<({String model, String literal})> readings,
  required List<EvidenceChoice> choices,
}) => showAdaptiveForm<Json>(
  context,
  width: DialogWidths.wide,
  builder: (BuildContext formContext) => _ResolveTranscriptionForm(
    regionName: regionName,
    regionId: regionId,
    readings: readings,
    choices: choices,
  ),
);

class _ResolveTranscriptionForm extends StatefulWidget {
  const _ResolveTranscriptionForm({
    required this.regionName,
    required this.regionId,
    required this.readings,
    required this.choices,
  });

  final String regionName;
  final String? regionId;
  final List<({String model, String literal})> readings;
  final List<EvidenceChoice> choices;

  @override
  State<_ResolveTranscriptionForm> createState() =>
      _ResolveTranscriptionFormState();
}

class _ResolveTranscriptionFormState extends State<_ResolveTranscriptionForm> {
  late final TextEditingController _value = TextEditingController(
    text: widget.readings.isEmpty ? '' : widget.readings.first.literal,
  );
  final TextEditingController _reason = TextEditingController();
  String _state = 'supported';
  Set<String> _evidence = <String>{};

  /// The states a transcription can be recorded in. `not_applicable` is not
  /// one of them: a label either has a reading or it does not.
  static const List<String> states = <String>[
    'supported',
    'unknown',
    'unreadable',
    'ambiguous',
    'not_present',
    'unresolved',
  ];

  @override
  void dispose() {
    _value.dispose();
    _reason.dispose();
    super.dispose();
  }

  bool get _complete {
    if (_reason.text.trim().isEmpty) return false;
    if (_state != 'supported') return true;
    return _value.text.trim().isNotEmpty && _evidence.isNotEmpty;
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return PopScope<Json?>(
      canPop: _reason.text.trim().isEmpty,
      onPopInvokedWithResult: (bool didPop, Json? result) {
        if (!didPop) _confirmDismiss();
      },
      child: SafeArea(
        child: SingleChildScrollView(
          padding: EdgeInsets.all(context.space.space6),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              Text(
                'Resolve ${widget.regionName}',
                style: theme.textTheme.titleLarge,
              ),
              SizedBox(height: context.space.space2),
              const Text(
                'Both readings stay unchanged. Your decision is recorded '
                'beside them.',
              ),
              SizedBox(height: context.space.space4),
              // Both readings, on screen, beside the field.
              LayoutBuilder(
                builder: (BuildContext context, BoxConstraints c) {
                  final bool sideBySide = c.maxWidth >= readingsSideBySideMin;
                  return Wrap(
                    spacing: context.space.space4,
                    runSpacing: context.space.space4,
                    children: <Widget>[
                      for (final (
                            int i,
                            ({String model, String literal}) reading,
                          )
                          in widget.readings.indexed)
                        SizedBox(
                          width: sideBySide
                              ? (c.maxWidth - context.space.space4) / 2
                              : c.maxWidth,
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            mainAxisSize: MainAxisSize.min,
                            children: <Widget>[
                              Text(
                                reading.model,
                                style: theme.textTheme.titleSmall,
                              ),
                              DiffText(
                                text: reading.literal,
                                reference: i == 0
                                    ? null
                                    : widget.readings.first.literal,
                                dense: true,
                              ),
                              SizedBox(height: context.space.space1),
                              OutlinedButton(
                                onPressed: () => setState(() {
                                  _state = 'supported';
                                  _value.text = reading.literal;
                                }),
                                child: const Text('Use this reading'),
                              ),
                            ],
                          ),
                        ),
                    ],
                  );
                },
              ),
              SizedBox(height: context.space.space4),
              DropdownButtonFormField<String>(
                initialValue: _state,
                decoration: const InputDecoration(labelText: 'Evidence state'),
                items: <DropdownMenuItem<String>>[
                  for (final String s in states)
                    DropdownMenuItem<String>(
                      value: s,
                      child: Text(vocabularyLabel(s)),
                    ),
                ],
                onChanged: (String? s) => setState(() => _state = s!),
              ),
              SizedBox(height: context.space.space2),
              if (_state != 'supported')
                const CaveatText(
                  label:
                      'Both readings are kept unchanged and the record stays '
                      'blocked from clearance.',
                  why:
                      'Absence is recorded as a state, never as a made up '
                      'value.',
                ),
              if (_state == 'supported') ...<Widget>[
                TextField(
                  controller: _value,
                  minLines: 2,
                  maxLines: 6,
                  onChanged: (String _) => setState(() {}),
                  decoration: const InputDecoration(
                    labelText: 'Value as written',
                    helperText:
                        'Keep the text exactly as written. Do not add missing '
                        'evidence.',
                  ),
                ),
                SizedBox(height: context.space.space4),
                EvidencePicker(
                  choices: widget.choices,
                  selected: _evidence,
                  required: true,
                  onChanged: (Set<String> next) =>
                      setState(() => _evidence = next),
                ),
              ],
              SizedBox(height: context.space.space4),
              TextField(
                controller: _reason,
                minLines: 2,
                maxLines: 4,
                onChanged: (String _) => setState(() {}),
                decoration: const InputDecoration(
                  labelText: 'Reason',
                  helperText: reasonHelperText,
                ),
              ),
              SizedBox(height: context.space.space6),
              Wrap(
                alignment: WrapAlignment.end,
                spacing: context.space.space2,
                runSpacing: context.space.space2,
                children: <Widget>[
                  TextButton(
                    onPressed: () => Navigator.of(context).pop(),
                    child: const Text('Cancel'),
                  ),
                  Semantics(
                    hint: _complete
                        ? ''
                        : 'Choose a value, evidence and a reason',
                    child: FilledButton(
                      onPressed: _complete ? _save : null,
                      child: const Text('Resolve transcription'),
                    ),
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }

  void _save() => Navigator.of(context).pop(<String, dynamic>{
    'kind': 'transcription_adjudication',
    'target_id': widget.regionId,
    'value': _state == 'supported' ? _value.text : null,
    'state': _state,
    'reason': _reason.text.trim(),
    'evidence_ids': _evidence.toList(),
  });

  Future<void> _confirmDismiss() async {
    final NavigatorState navigator = Navigator.of(context);
    final bool discard =
        await showDialog<bool>(
          context: context,
          builder: (BuildContext c) => AlertDialog(
            title: const Text('Discard this resolution?'),
            content: const Text('The text you typed is not saved anywhere.'),
            actions: <Widget>[
              TextButton(
                onPressed: () => Navigator.of(c).pop(false),
                child: const Text('Keep editing'),
              ),
              FilledButton(
                onPressed: () => Navigator.of(c).pop(true),
                child: const Text('Discard the resolution'),
              ),
            ],
          ),
        ) ??
        false;
    if (discard && navigator.mounted) navigator.pop();
  }
}
