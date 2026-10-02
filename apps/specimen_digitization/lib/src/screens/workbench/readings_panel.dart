/// The readings segment (screen blueprints, 6.3).
///
/// Readings share one label chooser and a quiet document flow. Each literal
/// carries a `DiffText` against the first reading for its region, so the
/// difference is quantified in a sentence and marked with an underline and
/// a symbol, never with colour alone. Provenance remains available through
/// an explicit disclosure. Resolving keeps both readings beside the field.
library;

import 'package:flutter/foundation.dart';
import 'package:flutter/scheduler.dart' show SchedulerPhase;
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../../models.dart';
import '../../reading_alignment.dart';
import '../../reading_declarations.dart';
import '../../review_context.dart';
import '../../risk_assessment.dart';
import '../../evidence_panel.dart';
import '../../vocabulary.dart';
import '../../widgets/widgets.dart';
import 'reader_identity.dart';

const List<String> _transcriptionStates = <String>[
  'supported',
  'unknown',
  'unreadable',
  'ambiguous',
  'not_present',
  'unresolved',
];

/// One model reading's place in the panel, so a region can be scrolled to.
typedef RegionAnchors = Map<String, GlobalKey>;

/// Connects record navigation to the actual retained label drafts.
/// A deliberate discard is refused while a save is awaiting acknowledgement.
class LabelDraftController extends ChangeNotifier {
  _WorkbenchReadingsState? _owner;
  bool _disposed = false;
  bool _notificationPending = false;

  bool get hasChanges => _owner?._drafts.values.any((d) => d.dirty) ?? false;
  bool get isSaving => _owner?._drafts.values.any((d) => d.busy) ?? false;

  bool discardAll() => _owner?._discardAllDrafts() ?? true;

  void _changed() {
    if (_disposed) return;
    if (WidgetsBinding.instance.schedulerPhase !=
        SchedulerPhase.persistentCallbacks) {
      notifyListeners();
      return;
    }
    if (_notificationPending) return;
    _notificationPending = true;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _notificationPending = false;
      if (!_disposed) notifyListeners();
    });
  }

  @override
  void dispose() {
    _disposed = true;
    _owner = null;
    super.dispose();
  }
}

/// The readings, their comparison, and the controls that resolve them.
class WorkbenchReadings extends StatefulWidget {
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
    this.onCommit,
    this.onDraftChanged,
    this.draftController,
    this.presentationIdentity,
    this.compact = false,
  });

  final Specimen specimen;

  /// One key per region, so the blockers list and the source pane can scroll
  /// the reviewer to the right label.
  final RegionAnchors anchors;

  /// The region the source pane is showing.
  final String? selectedRegionId;

  /// Selects the region shared by a group of readings.
  final ValueChanged<String?> onSelectRegion;

  /// Sends one decision.
  final Future<void> Function(Json) onChange;

  /// Why resolving a transcription is unavailable, or null when it is not.
  final String? transcriptionBlockedReason;

  /// True when the server does not permit recording a declaration.
  final bool declarationsBlocked;

  /// Loads a lazily fetched evidence payload.
  final Future<Json> Function(ArtifactRequest)? loadArtifact;

  /// Acknowledgement-aware save for inline label corrections.
  ///
  /// The host returns true only after the decision has been accepted. An
  /// unacknowledged draft is retained even if the request completed.
  final Future<bool> Function(Json)? onCommit;

  /// Whether any label has an unsaved correction, for the host's leave guard.
  final ValueChanged<bool>? onDraftChanged;

  /// Lets the host discard real draft state after its leave confirmation.
  final LabelDraftController? draftController;

  /// The scroll host's layout identity. Draft state survives a host change,
  /// while its clipped render and semantics descendants are recreated.
  final Object? presentationIdentity;

  /// Omits the repeated selector caption in a short, scrollable inspector.
  /// Control hit targets, accessible names and reading type stay unchanged.
  final bool compact;

  static const String differencesHeading = 'Comparison evidence';
  static const String resolveLabel = 'Save label text';
  static const String noReadingsReason = 'No model has read this specimen yet';

  @override
  State<WorkbenchReadings> createState() => _WorkbenchReadingsState();
}

class _WorkbenchReadingsState extends State<WorkbenchReadings> {
  final Map<String, _LabelTextDraft> _drafts = <String, _LabelTextDraft>{};
  final FocusNode _saveFocus = FocusNode(debugLabel: 'Save label text');
  final FocusNode _presentationFocus = FocusNode(
    debugLabel: 'Reading presentation transition',
    skipTraversal: true,
  );
  bool _reportedDirty = false;

  @override
  void initState() {
    super.initState();
    widget.draftController?._owner = this;
  }

  bool _discardAllDrafts() {
    if (_drafts.values.any((_LabelTextDraft draft) => draft.busy)) return false;
    setState(() {
      for (final _LabelTextDraft draft in _drafts.values) {
        draft.dispose();
      }
      _drafts.clear();
    });
    _reportDrafts();
    return true;
  }

  Specimen get specimen => widget.specimen;
  RegionAnchors get anchors => widget.anchors;
  String? get selectedRegionId => widget.selectedRegionId;
  ValueChanged<String?> get onSelectRegion => widget.onSelectRegion;
  Future<void> Function(Json) get onChange => widget.onChange;
  String? get transcriptionBlockedReason => widget.transcriptionBlockedReason;
  bool get declarationsBlocked => widget.declarationsBlocked;
  Future<Json> Function(ArtifactRequest)? get loadArtifact =>
      widget.loadArtifact;

  Map<String, String> get _readerNames => readerNames(specimen.observations);

  String? _editBlocked(String regionId) =>
      transcriptionBlockedReason ??
      (_accepted(regionId).isEmpty
          ? 'No saved transcription exists for this label. Text correction is unavailable.'
          : null);

  String _literalOf(Json o) =>
      textOf(o['literal_text'], textOf(o['verbatim_text'], ''));

  @override
  void didUpdateWidget(WorkbenchReadings oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.presentationIdentity != widget.presentationIdentity) {
      final activeDraft = _drafts.entries
          .where(
            (entry) =>
                entry.value.valueFocus.hasPrimaryFocus ||
                entry.value.reasonFocus.hasPrimaryFocus,
          )
          .firstOrNull;
      final FocusNode? activeEditor = activeDraft == null
          ? null
          : activeDraft.value.valueFocus.hasPrimaryFocus
          ? activeDraft.value.valueFocus
          : activeDraft.value.reasonFocus;
      final presentation = widget.presentationIdentity;
      for (final draft in _drafts.values) {
        // Preserve only the active input client. Other, potentially clipped
        // field presentations must renew their semantics with the scroll host.
        if (!draft.valueFocus.hasPrimaryFocus) {
          draft.valueFieldKey = GlobalKey();
        }
        if (!draft.reasonFocus.hasPrimaryFocus) {
          draft.reasonFieldKey = GlobalKey();
        }
      }
      if (activeEditor != null && activeDraft != null) {
        bool stillCurrent() =>
            mounted &&
            widget.presentationIdentity == presentation &&
            activeEditor.context?.mounted == true &&
            identical(_drafts[activeDraft.key], activeDraft.value) &&
            !activeDraft.value.busy &&
            !activeDraft.value.stale &&
            _editBlocked(activeDraft.key) == null;
        WidgetsBinding.instance.addPostFrameCallback((_) async {
          if (!stillCurrent() || !activeEditor.hasPrimaryFocus) return;
          final controller = activeEditor == activeDraft.value.valueFocus
              ? activeDraft.value.value
              : activeDraft.value.reason;
          final editingValue = controller.value;
          final restoreWebFocus =
              kIsWeb && WidgetsBinding.instance.semanticsEnabled;
          if (restoreWebFocus) {
            // Revealing a reparented web semantics input can blur it. Park
            // synchronously first, so that blur cannot consume its focus owner.
            _presentationFocus.requestFocus();
            FocusManager.instance.applyFocusChangesIfNeeded();
          }
          await Scrollable.ensureVisible(
            activeEditor.context!,
            alignmentPolicy: ScrollPositionAlignmentPolicy.keepVisibleAtEnd,
          );
          if (!restoreWebFocus) return;
          // A real focus transition reactivates the web input; an unchanged
          // semantics configuration or a keyboard request alone does not.
          await WidgetsBinding.instance.endOfFrame;
          // The web engine defers DOM safeBlur through a Future. Let those
          // already-queued blur events drain before restoring the input.
          await Future<void>(() {});
          if (!stillCurrent() || !_presentationFocus.hasPrimaryFocus) return;
          // Blur clears composing. Restore it only when no newer text or
          // selection arrived, and never reclaim focus from another control.
          if (controller.value != editingValue &&
              controller.value !=
                  editingValue.copyWith(composing: TextRange.empty)) {
            return;
          }
          controller.value = editingValue;
          activeEditor.requestFocus();
        });
      }
    }
    if (oldWidget.draftController != widget.draftController) {
      if (oldWidget.draftController?._owner == this) {
        oldWidget.draftController?._owner = null;
      }
      widget.draftController?._owner = this;
      widget.draftController?._changed();
    }
    if (oldWidget.specimen.id != specimen.id) {
      for (final _LabelTextDraft draft in _drafts.values) {
        draft.dispose();
      }
      _drafts.clear();
      _reportDrafts();
    } else if (oldWidget.specimen.revision != specimen.revision) {
      for (final String id in _drafts.keys.toList()) {
        final _LabelTextDraft draft = _drafts[id]!;
        if (draft.busy) continue;
        if (draft.dirty) {
          draft.stale = true;
        } else {
          _drafts.remove(id)!.dispose();
        }
      }
    }
  }

  @override
  void dispose() {
    _saveFocus.dispose();
    _presentationFocus.dispose();
    if (widget.draftController?._owner == this) {
      widget.draftController?._owner = null;
    }
    for (final _LabelTextDraft draft in _drafts.values) {
      draft.dispose();
    }
    // The host resets its guard when leaving this record. Calling its
    // setState synchronously during child disposal would be unsafe.
    super.dispose();
  }

  void _reportDrafts() {
    widget.draftController?._changed();
    final bool dirty = _drafts.values.any((_LabelTextDraft d) => d.dirty);
    if (_reportedDirty == dirty) return;
    _reportedDirty = dirty;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) {
        widget.onDraftChanged?.call(
          _drafts.values.any((_LabelTextDraft d) => d.dirty),
        );
      }
    });
  }

  Map<String, List<Json>> get _readingsByLabel {
    final Map<String, List<Json>> groups = <String, List<Json>>{
      for (final Json r in specimen.regions)
        if (r['region_id'] is String && (r['region_id'] as String).isNotEmpty)
          r['region_id'] as String: <Json>[],
    };
    for (final Json o in specimen.observations) {
      final Object? region = o['region_id'];
      if (region is String && groups.containsKey(region)) {
        groups[region]!.add(o);
      }
    }
    for (final List<Json> group in groups.values) {
      group.sort((Json a, Json b) {
        final int producer = (readerIdentity(a) ?? '~').compareTo(
          readerIdentity(b) ?? '~',
        );
        return producer != 0
            ? producer
            : textOf(a['id'], '').compareTo(textOf(b['id'], ''));
      });
    }
    return groups;
  }

  String _regionName(Object? regionId) {
    final int index = specimen.regions.indexWhere(
      (Json r) => r['region_id'] == regionId,
    );
    return index < 0 ? 'Unassigned label' : 'Label ${index + 1}';
  }

  Json _accepted(String regionId) =>
      objects(
        specimen.data['transcriptions'],
      ).where((Json t) => t['region_id'] == regionId).firstOrNull ??
      <String, dynamic>{};

  _LabelTextDraft _draftFor(String regionId) =>
      _drafts.putIfAbsent(regionId, () {
        final Json current = _accepted(regionId);
        return _LabelTextDraft(
          revision: specimen.revision,
          text: textOf(current['verbatim_text'], textOf(current['text'], '')),
          state: textOf(
            current['value_state'],
            textOf(current['state'], 'unresolved'),
          ),
        );
      });

  @override
  Widget build(BuildContext context) {
    final String? selected = selectedRegionId;
    final Map<String, List<Json>> groups = _readingsByLabel;
    return Focus(
      focusNode: _presentationFocus,
      skipTraversal: true,
      includeSemantics: false,
      child: Column(
        key: ValueKey<Object?>(widget.presentationIdentity),
        crossAxisAlignment: CrossAxisAlignment.stretch,
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          UiSelect<String>(
            label: 'Label',
            showLabel: !widget.compact,
            semanticsLabel: 'Label to review',
            placeholder: 'Choose a label',
            value: selected ?? '',
            options: <UiSelectOption<String>>[
              const UiSelectOption<String>(value: '', label: 'All labels'),
              for (final String regionId in groups.keys)
                UiSelectOption<String>(
                  value: regionId,
                  label: _regionName(regionId),
                ),
            ],
            onChanged: (String id) => onSelectRegion(id.isEmpty ? null : id),
          ),
          SizedBox(
            height: widget.compact ? context.ui.space.s1 : context.ui.space.s3,
          ),
          if (selected == null)
            _summary(context, groups)
          else
            _label(context, selected, groups[selected] ?? <Json>[]),
        ],
      ),
    );
  }

  Widget _summary(BuildContext context, Map<String, List<Json>> groups) {
    final UiThemeData ui = context.ui;
    final List<Json> unassigned = specimen.observations.where((Json o) {
      final Object? id = o['region_id'];
      return id is! String || !groups.containsKey(id);
    }).toList();
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        if (groups.isEmpty && unassigned.isEmpty)
          Text('No label results yet.', style: ui.type.body),
        for (final MapEntry<String, List<Json>> entry in groups.entries)
          Padding(
            key: anchors[entry.key],
            padding: EdgeInsetsDirectional.symmetric(vertical: ui.space.s2),
            child: Wrap(
              key: ValueKey<Object?>(widget.presentationIdentity),
              spacing: ui.space.s3,
              runSpacing: ui.space.s1,
              crossAxisAlignment: WrapCrossAlignment.center,
              children: <Widget>[
                Text(_regionName(entry.key), style: ui.type.label),
                Text(
                  _comparisonState(entry.key, entry.value),
                  style: ui.type.bodySmall.copyWith(
                    color: ui.color.inkSecondary,
                  ),
                ),
                if (_drafts[entry.key]?.dirty == true)
                  Text('Unsaved changes', style: ui.type.labelSmall),
              ],
            ),
          ),
        if (unassigned.isNotEmpty)
          UiDisclosure(
            title: 'Unassigned model results',
            child: Column(
              children: <Widget>[
                for (final (int index, Json observation) in unassigned.indexed)
                  _reading(
                    context,
                    observation,
                    null,
                    'Unassigned label',
                    index,
                    null,
                  ),
              ],
            ),
          ),
      ],
    );
  }

  String _comparisonState(String regionId, List<Json> readings) {
    if (_accepted(regionId)['resolved'] == true) return 'Text accepted';
    if (readings.isEmpty) return 'No model result';
    final int variants = readings.map(_literalOf).toSet().length;
    final String count =
        '${readings.length} model ${readings.length == 1 ? 'result' : 'results'}';
    return variants > 1 ? '$count · Differences to review' : count;
  }

  Widget _label(BuildContext context, String regionId, List<Json> readings) {
    final UiThemeData ui = context.ui;
    final String name = _regionName(regionId);
    final _LabelTextDraft draft = _draftFor(regionId);
    final Json run = objectOf(specimen.data['run']);
    return KeyedSubtree(
      key: anchors[regionId],
      child: Column(
        key: ValueKey<Object?>(widget.presentationIdentity),
        crossAxisAlignment: CrossAxisAlignment.stretch,
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          if (readings.isEmpty)
            Text('No model result for this label.', style: ui.type.body)
          else
            LayoutBuilder(
              builder: (BuildContext context, BoxConstraints constraints) {
                final double fontSize = ui.type.body.fontSize!;
                final double scale =
                    MediaQuery.textScalerOf(context).scale(fontSize) / fontSize;
                final int columns =
                    ((constraints.maxWidth + ui.space.s4) /
                            (_modelColumnMinimum * scale + ui.space.s4))
                        .floor()
                        .clamp(1, readings.length.clamp(1, 3));
                final double width =
                    (constraints.maxWidth - ui.space.s4 * (columns - 1)) /
                    columns;
                return Wrap(
                  spacing: ui.space.s4,
                  runSpacing: ui.space.s4,
                  children: <Widget>[
                    for (final (int index, Json observation)
                        in readings.indexed)
                      SizedBox(
                        width: width,
                        child: _reading(
                          context,
                          observation,
                          index == 0 ? null : _literalOf(readings.first),
                          name,
                          index,
                          draft,
                        ),
                      ),
                  ],
                );
              },
            ),
          for (final MapEntry<String, String> reader in _readerNames.entries)
            if (!readings.any((Json o) => readerIdentity(o) == reader.key))
              Padding(
                padding: EdgeInsetsDirectional.only(top: ui.space.s2),
                child: Text(
                  '${reader.value} · No result for this label',
                  style: ui.type.bodySmall,
                ),
              ),
          SizedBox(height: ui.space.s4),
          const UiHairline(),
          SizedBox(height: ui.space.s4),
          _acceptedEditor(context, regionId, draft),
          SizedBox(height: ui.space.s4),
          UiDisclosure(
            title: WorkbenchReadings.differencesHeading,
            child: _differences(context, run),
          ),
          if (run['label_language_handling'] is Map)
            UiDisclosure(
              title: 'Languages and scripts',
              child: _declarations(context, run),
            ),
        ],
      ),
    );
  }

  /// A full line of literal text remains useful before stacking at large text.
  static const double _modelColumnMinimum = 200;

  Widget _reading(
    BuildContext context,
    Json o,
    String? reference,
    String regionName,
    int index,
    _LabelTextDraft? draft,
  ) {
    final UiThemeData ui = context.ui;
    final String name =
        _readerNames[readerIdentity(o)] ?? 'Unidentified reader';
    final List<Json> sameReader =
        specimen.observations
            .where(
              (Json item) =>
                  item['region_id'] == o['region_id'] &&
                  readerIdentity(item) == readerIdentity(o),
            )
            .toList()
          ..sort(
            (Json a, Json b) =>
                textOf(a['id'], '').compareTo(textOf(b['id'], '')),
          );
    final String resultName = sameReader.length > 1
        ? '$name, result ${sameReader.indexWhere((Json item) => (item['id'] ?? item['observation_id']) == (o['id'] ?? o['observation_id'])) + 1}'
        : name;
    final String? blocked =
        (draft == null
            ? transcriptionBlockedReason
            : _editBlocked(textOf(o['region_id'], ''))) ??
        (draft?.stale == true
            ? 'Reset this draft after the record changed'
            : null);
    return Semantics(
      container: true,
      explicitChildNodes: true,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          Row(
            children: <Widget>[
              Expanded(child: Text(name, style: ui.type.label)),
              UiIconButton(
                icon: UiIcons.info,
                semanticsLabel:
                    'How this reading was produced, $regionName, $resultName',
                tooltip: 'Reading source',
                onPressed: () => showProductModal<void>(
                  context: context,
                  title: '$regionName · $resultName',
                  body: (context) => _readingDetails(context, o),
                  secondaryAction: (context) => UiButton(
                    label: 'Close',
                    variant: UiButtonVariant.ghost,
                    onPressed: () => Navigator.of(context).pop(),
                  ),
                ),
              ),
            ],
          ),
          if (sameReader.length > 1) Text(resultName, style: ui.type.bodySmall),
          SizedBox(height: widget.compact ? ui.space.s1 : ui.space.s2),
          DiffText(text: _literalOf(o), reference: reference),
          if (draft != null)
            Align(
              alignment: AlignmentDirectional.centerStart,
              child: UiButton(
                label: 'Use this text',
                semanticsLabel: 'Use text from $resultName',
                variant: UiButtonVariant.ghost,
                disabledReason: blocked,
                onPressed: blocked != null || draft.busy
                    ? null
                    : () {
                        setState(() {
                          draft.value.text = _literalOf(o);
                          draft.state = 'supported';
                          draft.dirty = true;
                          draft.error = null;
                        });
                        _reportDrafts();
                      },
              ),
            ),
        ],
      ),
    );
  }

  Widget _acceptedEditor(
    BuildContext context,
    String regionId,
    _LabelTextDraft draft,
  ) {
    final UiThemeData ui = context.ui;
    final String? blocked = _editBlocked(regionId);
    final bool readOnly = blocked != null || draft.busy || draft.stale;
    void changed() {
      setState(() {
        draft.dirty = true;
        draft.error = null;
      });
      _reportDrafts();
    }

    final bool complete =
        draft.reason.text.trim().isNotEmpty &&
        (draft.state != 'supported' || draft.value.text.trim().isNotEmpty);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        UiTextArea(
          key: draft.valueFieldKey,
          label: 'Accepted label text',
          controller: draft.value,
          focusNode: draft.valueFocus,
          readOnly: readOnly,
          disabledReason: blocked,
          autocorrect: false,
          textCapitalization: TextCapitalization.none,
          minLines: 2,
          maxLines: 6,
          onChanged: readOnly
              ? null
              : (_) {
                  draft.state = 'supported';
                  changed();
                },
        ),
        if (blocked != null)
          Text(blocked, style: ui.type.body.copyWith(color: ui.color.ink)),
        if (draft.dirty) ...<Widget>[
          SizedBox(height: ui.space.s2),
          Text('Unsaved changes', style: ui.type.labelSmall),
        ],
        if (draft.stale) ...<Widget>[
          SizedBox(height: ui.space.s2),
          Text(
            'This record changed. Your draft is kept; reset it before editing the new version.',
            style: ui.type.body,
          ),
        ],
        SizedBox(height: ui.space.s3),
        UiSelect<String>(
          label: 'Text status',
          disabledReason: readOnly
              ? (blocked ?? 'Text correction unavailable')
              : null,
          placeholder: 'Choose text status',
          value: draft.state,
          options: <UiSelectOption<String>>[
            for (final String state in _transcriptionStates)
              UiSelectOption<String>(
                value: state,
                label: vocabularyLabel(state),
              ),
          ],
          onChanged: readOnly
              ? null
              : (String? next) {
                  if (next != null) {
                    draft.state = next;
                    changed();
                  }
                },
        ),
        if (draft.dirty) ...<Widget>[
          SizedBox(height: ui.space.s3),
          UiTextArea(
            key: draft.reasonFieldKey,
            label: 'Reason for correction',
            controller: draft.reason,
            focusNode: draft.reasonFocus,
            readOnly: readOnly,
            minLines: 1,
            maxLines: 3,
            onChanged: readOnly ? null : (_) => changed(),
          ),
          if (draft.state != 'supported')
            Text(
              'No text will be saved for this status.',
              style: ui.type.bodySmall,
            ),
        ],
        if (draft.error != null) ...<Widget>[
          SizedBox(height: ui.space.s2),
          Semantics(
            liveRegion: true,
            child: Text(draft.error!, style: ui.type.body),
          ),
        ],
        SizedBox(height: ui.space.s3),
        Wrap(
          spacing: ui.space.s2,
          runSpacing: ui.space.s2,
          children: <Widget>[
            UiButton(
              label: WorkbenchReadings.resolveLabel,
              focusNode: _saveFocus,
              disabledReason:
                  blocked ??
                  (draft.stale
                      ? 'Reset this draft after the record changed'
                      : draft.busy
                      ? 'Saving label text'
                      : 'Enter text and a reason'),
              onPressed: !readOnly && draft.dirty && complete
                  ? () => _saveDraft(regionId, draft)
                  : null,
            ),
            if (draft.dirty)
              UiButton(
                label: draft.stale ? 'Reset draft' : 'Discard changes',
                variant: UiButtonVariant.ghost,
                onPressed: draft.busy
                    ? null
                    : () {
                        setState(() {
                          _drafts.remove(regionId)?.dispose();
                        });
                        _reportDrafts();
                      },
              ),
          ],
        ),
      ],
    );
  }

  Future<void> _saveDraft(String regionId, _LabelTextDraft draft) async {
    if (draft.busy || draft.stale || _editBlocked(regionId) != null) return;
    // Close the active editor connection before busy makes it read-only.
    // This node belongs to the panel, so acknowledged draft disposal cannot
    // dispose keyboard focus or leave it attached to a removed reason field.
    _saveFocus.requestFocus();
    FocusManager.instance.applyFocusChangesIfNeeded();
    final Json change = <String, dynamic>{
      'kind': 'transcription_adjudication',
      'target_id': regionId,
      'value': draft.state == 'supported' ? draft.value.text : null,
      'state': draft.state,
      'reason': draft.reason.text.trim(),
      'evidence_ids': <String>[],
    };
    setState(() {
      draft.busy = true;
      draft.error = null;
    });
    _reportDrafts();
    bool acknowledged = false;
    try {
      if (widget.onCommit != null) {
        acknowledged = await widget.onCommit!(change);
      } else {
        await onChange(change);
      }
    } catch (_) {
      // The host owns any request-level error. Keep the editable draft here.
    }
    if (!mounted || !identical(_drafts[regionId], draft)) return;
    final Json accepted = _accepted(regionId);
    final bool matchesReadback =
        specimen.revision > draft.revision &&
        (accepted['value_state'] ?? accepted['state']) == change['state'] &&
        (accepted['verbatim_text'] ?? accepted['text']) == change['value'] &&
        accepted['reason'] == change['reason'];
    setState(() {
      draft.busy = false;
      if (acknowledged && matchesReadback) {
        _drafts.remove(regionId)!.dispose();
      } else {
        draft.stale = draft.revision != specimen.revision;
        draft.error = 'Save not confirmed. Your changes are kept.';
      }
    });
    _reportDrafts();
  }

  Widget _readingDetails(BuildContext context, Json o) {
    final UiThemeData ui = context.ui;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        Text(textOf(o['model_id'], 'Model not recorded'), style: ui.type.label),
        TermText(
          'Provider',
          displayText: textOf(o['provider'], 'Not recorded'),
          style: ui.type.bodySmall.copyWith(color: ui.color.inkSecondary),
        ),
        if (o.containsKey('latency_seconds') ||
            o.containsKey('completion_state')) ...<Widget>[
          SizedBox(height: ui.space.s2),
          Text(ReadingCard.executionTitle, style: ui.type.label),
          ObservationExecutionDetails(observation: o),
        ],
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
                  objectOf(objectOf(specimen.data['run'])['reading_metadata']),
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
            render: (Json metadata) => ReadingMetadataView(metadata: metadata),
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
    );
  }

  Widget _declarations(BuildContext context, Json run) {
    final Object? handling = run['label_language_handling'];
    if (handling is! Map) return const SizedBox.shrink();
    return LabelLanguagePolicy(
      handling: <String, dynamic>{
        ...objectOf(handling),
        'labels': objects(handling['labels'])
            .where((Json label) => label['region_id'] == selectedRegionId)
            .toList(),
      },
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
    final List<Json> transcriptions = objects(
      specimen.data['transcriptions'],
    ).where((Json t) => t['region_id'] == selectedRegionId).toList();
    // One row per region. A region with a transcription is described by it;
    // the list of differences speaks only for a region no transcription
    // covers, which is the shape older records and fixtures carry.
    final Set<Object?> described = <Object?>{
      for (final Json t in transcriptions) t['region_id'],
    };
    final List<Json> disagreements = objects(specimen.data['disagreements'])
        .where(
          (Json d) =>
              d['region_id'] == selectedRegionId &&
              !described.contains(d['region_id']),
        )
        .toList();

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        if (loadArtifact != null)
          for (final Json d in objects(
            run['disagreements'],
          ).where((Json d) => d['region_id'] == selectedRegionId))
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
        for (final Json d in disagreements) _regionRow(d),
        for (final Json t in transcriptions)
          _regionRow(
            t,
            extra: t.containsKey('alignment_status')
                ? TranscriptionComparisonSummary(transcription: t)
                : null,
          ),
      ],
    );
  }

  /// What a region's row says after its name, one word per state (02
  /// section 6, rule 18).
  static const String resolvedState = 'resolved';

  /// The row of a region whose readings differ and are not resolved.
  static const String differState = 'the readings differ';

  /// The row of a region whose readings agree but are not resolved.
  static const String unresolvedState = 'unresolved';

  /// One region's row: resolved, the readings differ, or unresolved, by the
  /// one rule the blockers use (UI.md T1.3), whichever list it came from.
  Widget _regionRow(Json t, {Widget? extra}) {
    final bool resolved = t['resolved'] == true;
    final bool differ = readingsDiffer(t, specimen.observations);
    final String state = resolved
        ? resolvedState
        : differ
        ? differState
        : unresolvedState;
    return _DifferenceRow(
      title: '${_regionName(t['region_id'])}: $state',
      detail: !resolved && differ
          ? _alternatives(t)
          : textOf(t['verbatim_text'], textOf(t['text'], '')),
      // A resolved region whose readings differed keeps them in view: a
      // decision is audited against what it chose between.
      readings: resolved && differ ? _alternatives(t) : null,
      payload: t,
      extra: extra,
    );
  }

  /// A region's distinct readings, as one line of metadata values: the
  /// transcription's alternatives, or the region's own readings when it has
  /// none (see `distinctReadings`).
  String _alternatives(Json transcription) {
    final Object? alternatives = transcription['alternatives'];
    final Iterable<String> texts = alternatives is List
        ? alternatives.map((Object? a) => a.toString())
        : specimen.observations
              .where((Json o) => o['region_id'] == transcription['region_id'])
              .map(_literalOf)
              .toSet();
    return texts.join(' · ');
  }
}

class _LabelTextDraft {
  _LabelTextDraft({
    required this.revision,
    required String text,
    required this.state,
  }) : value = TextEditingController(text: text);

  final int revision;
  final TextEditingController value;
  final TextEditingController reason = TextEditingController();
  final FocusNode valueFocus = FocusNode(debugLabel: 'Accepted label text');
  final FocusNode reasonFocus = FocusNode(debugLabel: 'Reason for correction');
  GlobalKey valueFieldKey = GlobalKey();
  GlobalKey reasonFieldKey = GlobalKey();
  String state;
  bool dirty = false;
  bool busy = false;
  bool stale = false;
  String? error;

  void dispose() {
    valueFocus.dispose();
    reasonFocus.dispose();
    value.dispose();
    reason.dispose();
  }
}

class _DifferenceRow extends StatelessWidget {
  const _DifferenceRow({
    required this.title,
    required this.detail,
    required this.payload,
    this.readings,
    this.extra,
  });

  final String title;
  final String detail;
  final Json payload;

  /// The readings a resolved region chose between, when they differed.
  final String? readings;

  final Widget? extra;

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    return Semantics(
      container: true,
      child: Padding(
        padding: EdgeInsetsDirectional.only(bottom: ui.space.s2),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            Text(title, style: ui.type.label),
            if (detail.isNotEmpty && detail != 'Not recorded')
              Text(detail, style: ui.type.mono.literalDense),
            if (readings case final String chosenFrom)
              Text.rich(
                TextSpan(
                  children: <InlineSpan>[
                    TextSpan(
                      text: 'Readings: ',
                      style: ui.type.bodySmall.copyWith(
                        color: ui.color.inkSecondary,
                      ),
                    ),
                    TextSpan(
                      text: chosenFrom,
                      style: ui.type.mono.literalDense,
                    ),
                  ],
                ),
              ),
            ?extra,
            EvidenceDrawer(payload: payload, section: title),
          ],
        ),
      ),
    );
  }
}
