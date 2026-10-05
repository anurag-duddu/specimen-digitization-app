import 'dart:convert';

import 'package:flutter/widgets.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../widgets/evidence_drawer.dart';
import 'research_controller.dart';
import 'research_models.dart';
import 'research_review_block.dart';

/// A collapsed field disclosure driven entirely by verified host input.
///
/// The host supplies the trusted scope and lazy callbacks. This card performs
/// no network work, edits, approval, navigation or nested scrolling.
class ResearchThreadCard extends StatelessWidget {
  const ResearchThreadCard({
    super.key,
    required this.scope,
    required this.recordRevision,
    required this.fieldKey,
    required this.fieldLabel,
    this.field,
    this.historical = false,
    this.canonicalRevision,
    this.reviewSavedRevision,
    this.networkState = ResearchNetworkState.idle,
    this.paused = false,
    this.hasUnknownState = false,
    this.readOnly = false,
    this.message,
    this.onLoad,
    this.onRefresh,
    this.onRetry,
    this.onSelectCandidate,
    this.fieldCentered = false,
  });
  final ResearchScope scope;
  final int recordRevision;
  final String fieldKey;
  final String fieldLabel;
  final ResearchFieldThread? field;
  final bool historical;
  final int? canonicalRevision;
  final int? reviewSavedRevision;
  final ResearchNetworkState networkState;
  final bool paused;
  final bool hasUnknownState;
  final bool readOnly;
  final String? message;
  final VoidCallback? onLoad;
  final VoidCallback? onRefresh;
  final VoidCallback? onRetry;
  final ValueChanged<ResearchReviewCandidate>? onSelectCandidate;

  /// Concise presentation inside a specimen field, without repeating its form.
  final bool fieldCentered;

  bool get _bound =>
      researchFieldKeys.contains(fieldKey) &&
      (field == null ||
          (field!.fieldKey == fieldKey &&
              field!.scope.matches(scope) &&
              (field!.checkpoint?.scope.matches(scope) ?? true)));
  bool get _busy =>
      networkState == ResearchNetworkState.loading ||
      networkState == ResearchNetworkState.submitting;
  bool get _denied => networkState == ResearchNetworkState.denied;
  bool get _unknown =>
      hasUnknownState ||
      field?.workState == ResearchWorkState.unknown ||
      field?.checkpoint?.resolution.workState == ResearchWorkState.unknown;
  bool get _retryEnabled =>
      _bound &&
      !_busy &&
      !_denied &&
      !_unknown &&
      !paused &&
      !historical &&
      !readOnly &&
      networkState == ResearchNetworkState.ready &&
      (field?.canRetry ?? false) &&
      onRetry != null;
  bool get _refreshEnabled => _bound && !_busy && !_denied && onRefresh != null;

  String get _summary {
    if (!_bound) return 'Research could not be verified';
    if (_denied) return 'Research access unavailable';
    if (_busy) {
      return networkState == ResearchNetworkState.submitting
          ? 'Queuing retry'
          : 'Loading research';
    }
    if (_unknown) return 'Status unavailable · Actions disabled';
    if (networkState == ResearchNetworkState.error) {
      return 'Research unavailable';
    }
    if (field == null) {
      return networkState == ResearchNetworkState.ready
          ? 'No research recorded for this field'
          : 'Load this field’s research when needed';
    }
    final prefix = paused ? 'Paused · ' : '';
    return '${historical ? 'Historical report · ' : ''}$prefix${field!.workState.label}'
        '${field!.blockerCode == 'research_retry_blocked' ? ' · Retry blocked' : ''}';
  }

  String get _disabledReason {
    if (!_bound) {
      return 'Research could not be verified. Refresh the current record.';
    }
    if (_denied) return 'Research access is unavailable.';
    if (historical) {
      return 'This historical report no longer has current review selection tokens.';
    }
    if (networkState == ResearchNetworkState.error) {
      return 'Refresh research before retrying this field.';
    }
    if (networkState == ResearchNetworkState.idle) {
      return 'Load research before retrying this field.';
    }
    if (readOnly) return 'This view is read-only.';
    if (paused) return 'Research is paused.';
    if (_unknown) {
      return 'This research status is not supported. Actions are disabled.';
    }
    if (_busy) return 'Wait for the current request.';
    if (field?.blockerCode == 'research_retry_blocked') {
      return 'Retry is blocked for this field.';
    }
    if (onRetry == null) return 'Retry is unavailable in this view.';
    return 'Retry is unavailable for this field’s current checkpoint.';
  }

  String get _refreshDisabledReason {
    if (!_bound) {
      return 'Research could not be verified. Refresh the current record.';
    }
    if (_denied) return 'Research access is unavailable.';
    if (_busy) return 'Wait for the current request.';
    return 'Research refresh is unavailable in this view.';
  }

  String? get _notice {
    if (!_bound) {
      return 'Research could not be verified. Refresh the current record.';
    }
    if (_denied) {
      return message ?? 'Research access is unavailable for this collection.';
    }
    if (_unknown) {
      return 'This research status is not supported. Actions are disabled.';
    }
    if (networkState == ResearchNetworkState.error) {
      return message ??
          'Research could not be loaded. Refresh before retrying this field.';
    }
    return message;
  }

  @override
  Widget build(BuildContext context) {
    final ui = context.ui;
    final safeField =
        _bound &&
            !_denied &&
            (networkState == ResearchNetworkState.ready ||
                networkState == ResearchNetworkState.submitting)
        ? field
        : null;
    final resolution = safeField?.checkpoint?.resolution;
    final key = jsonEncode([
      scope.organizationId,
      scope.collectionId,
      scope.specimenId,
      scope.jobId,
      scope.generation,
      scope.inputDigest,
      scope.profileDigest,
      scope.sensitive,
      recordRevision,
      fieldKey,
    ]);
    return Semantics(
      container: true,
      label: '$fieldLabel research',
      child: Surface(
        hairline: true,
        child: UiDisclosure(
          key: ValueKey(key),
          title: 'Research',
          summary: _summary,
          hideSummaryWhenExpanded: true,
          onExpansionChanged: (expanded) {
            if (expanded &&
                _bound &&
                !_denied &&
                networkState == ResearchNetworkState.idle) {
              onLoad?.call();
            }
          },
          child: LayoutBuilder(
            builder: (context, constraints) {
              final retry = UiButton(
                label: 'Retry field',
                busyLabel: 'Queuing retry',
                semanticsLabel: 'Retry $fieldLabel research',
                variant: UiButtonVariant.secondary,
                onPressed: _retryEnabled ? onRetry : null,
                loading: networkState == ResearchNetworkState.submitting,
                disabledReason: _retryEnabled ? null : _disabledReason,
                leading: UiIcons.reload,
              );
              final refresh = UiButton(
                label: 'Refresh research',
                busyLabel: 'Loading research',
                variant: UiButtonVariant.ghost,
                onPressed: _refreshEnabled ? onRefresh : null,
                loading: networkState == ResearchNetworkState.loading,
                disabledReason: _refreshEnabled ? null : _refreshDisabledReason,
                leading: UiIcons.reload,
              );
              final children = <Widget>[
                if (_notice != null)
                  Semantics(
                    liveRegion: true,
                    child: Text(_notice!, style: ui.type.bodySmall),
                  ),
                if (paused)
                  Text('Research is paused.', style: ui.type.bodySmall),
                if (readOnly)
                  Text(
                    'This research view is read-only.',
                    style: ui.type.bodySmall,
                  ),
                if (historical)
                  Text(
                    _historicalBanner,
                    style: ui.type.bodySmall.copyWith(
                      color: ui.color.inkSecondary,
                    ),
                  ),
                if (fieldCentered && safeField != null)
                  ..._fieldResult(context, safeField),
                if (!fieldCentered && safeField != null) ...[
                  Text(safeField.workState.label, style: ui.type.body),
                  if (safeField.blockerCode != null &&
                      !(safeField.workState ==
                              ResearchWorkState.operationalFailed &&
                          safeField.blockerCode ==
                              'research_operational_failure'))
                    Text(
                      safeField.blockerCode == 'research_retry_blocked'
                          ? 'Retry blocked. Review the current prerequisites before continuing.'
                          : safeField.blockerCode ==
                                'research_operational_failure'
                          ? 'Research was interrupted for this field.'
                          : 'This field has a research blocker. Review its current prerequisites.',
                      style: ui.type.bodySmall,
                    ),
                  _layer(context, 'As written', safeField.value.literal),
                  _layer(context, 'Read as', safeField.value.parsed),
                  _layer(context, 'Standardized', safeField.value.normalized),
                ],
                if (!fieldCentered && resolution != null) ...[
                  Text(
                    'Research layer: ${(switch (resolution.valueLayer) {
                      'settled' => 'Settled',
                      'derived' => 'Derived',
                      _ => 'Verbatim',
                    })}',
                    style: ui.type.bodySmall,
                  ),
                  if (resolution.evidenceIds.isNotEmpty)
                    Text(
                      '${resolution.evidenceIds.length.toString()}'
                      '${resolution.evidenceIds.length == 1 ? ' evidence reference' : ' evidence references'}',
                      style: ui.type.bodySmall,
                    ),
                  for (final coverage in resolution.sourceCoverage)
                    Text(
                      '${_sourceDisplayName(coverage.sourceId)}: '
                      '${_coverageStatus(coverage.state)} Scope: ${coverage.coverageLimit}',
                      style: ui.type.bodySmall,
                    ),
                  if (resolution.question != null)
                    Text(resolution.question!.text, style: ui.type.body),
                  if (resolution.exception != null) ...[
                    Text(
                      'Policy exception: ${resolution.exception!.reason}',
                      style: ui.type.bodySmall,
                    ),
                    Text(
                      'Reevaluate when: ${resolution.exception!.reevaluateWhen}',
                      style: ui.type.bodySmall,
                    ),
                  ],
                  if (safeField?.actions.contains('supply_information') ??
                      false)
                    Text(
                      'Providing information is not available in this view yet.',
                      style: ui.type.bodySmall,
                    ),
                  if (safeField?.actions.contains('review_proposal') ?? false)
                    Text(
                      'Proposal review is not available in this view yet.',
                      style: ui.type.bodySmall,
                    ),
                ],
                Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children: [
                    if ((!fieldCentered &&
                            safeField?.workState ==
                                ResearchWorkState.operationalFailed ||
                        (safeField?.actions.contains('retry_field') ?? false)))
                      retry.intrinsicWidth(context) <= constraints.maxWidth
                          ? retry
                          : UiButton(
                              label: 'Retry',
                              busyLabel: 'Queuing',
                              semanticsLabel: 'Retry $fieldLabel research',
                              variant: UiButtonVariant.secondary,
                              onPressed: _retryEnabled ? onRetry : null,
                              loading:
                                  networkState ==
                                  ResearchNetworkState.submitting,
                              disabledReason: _retryEnabled
                                  ? null
                                  : _disabledReason,
                            ),
                    refresh.intrinsicWidth(context) <= constraints.maxWidth
                        ? refresh
                        : UiButton(
                            label: 'Refresh',
                            busyLabel: 'Loading',
                            variant: UiButtonVariant.ghost,
                            onPressed: _refreshEnabled ? onRefresh : null,
                            loading:
                                networkState == ResearchNetworkState.loading,
                            disabledReason: _refreshEnabled
                                ? null
                                : _refreshDisabledReason,
                          ),
                  ],
                ),
              ];
              return Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  for (var i = 0; i < children.length; i++) ...[
                    if (i > 0) SizedBox(height: context.ui.space.s2),
                    children[i],
                  ],
                ],
              );
            },
          ),
        ),
      ),
    );
  }

  Widget _layer(BuildContext context, String label, String? value) => Column(
    mainAxisSize: MainAxisSize.min,
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: [
      Text(label, style: context.ui.type.bodySmall),
      SizedBox(height: context.ui.space.s2),
      Text(value ?? 'Not recorded', style: context.ui.type.body),
    ],
  );

  List<Widget> _fieldResult(BuildContext context, ResearchFieldThread field) {
    final ui = context.ui;
    final resolution = field.checkpoint?.resolution;
    final value = field.value;
    final current = [
      value.normalized,
      value.parsed,
      value.literal,
    ].whereType<String>().where((item) => item.trim().isNotEmpty).firstOrNull;
    return [
      Text(field.workState.label, style: ui.type.label),
      if (current != null) ...[
        Text('Research value', style: ui.type.bodySmall),
        Text(current, style: ui.type.body),
      ] else
        Text('No supported value yet.', style: ui.type.bodySmall),
      if (resolution?.question != null)
        Text(resolution!.question!.text, style: ui.type.body)
      else if (resolution != null)
        Text(_reviewExplanation(resolution), style: ui.type.bodySmall),
      if (field.review != null && researchReviewApplies(field.workState))
        ResearchReviewBlock(
          fieldLabel: fieldLabel,
          field: field,
          canSelectCandidates:
              !readOnly &&
              !paused &&
              !historical &&
              networkState == ResearchNetworkState.ready &&
              !hasUnknownState &&
              field.workState == ResearchWorkState.waitingHuman &&
              field.actions.contains('review_proposal'),
          onSelectCandidate: onSelectCandidate,
        ),
      if (resolution?.exception != null)
        Text(
          'This field has a recorded policy exception. '
          'Its conditions are available in research details.',
          style: ui.type.bodySmall,
        ),
      if (resolution != null && resolution.sourceCoverage.isNotEmpty)
        UiDisclosure(
          title: 'Sources searched',
          summary:
              '${resolution.sourceCoverage.length} '
              '${resolution.sourceCoverage.length == 1 ? 'source' : 'sources'}',
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              for (final coverage in resolution.sourceCoverage)
                Padding(
                  padding: EdgeInsets.only(bottom: ui.space.s2),
                  child: Text(
                    '${_sourceDisplayName(coverage.sourceId)}: '
                    '${_coverageStatus(coverage.state)}',
                    style: ui.type.bodySmall,
                  ),
                ),
            ],
          ),
        ),
      if (current != null)
        UiDisclosure(
          title: 'Value provenance',
          summary: switch (resolution?.valueLayer) {
            'settled' => 'Resolved from evidence',
            'derived' => 'Derived from other fields',
            _ => 'Recorded label interpretation',
          },
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              if (value.literal?.trim().isNotEmpty ?? false)
                _layer(context, 'As written', value.literal),
              if (value.parsed?.trim().isNotEmpty ?? false)
                _layer(context, 'Read as', value.parsed),
              if (value.normalized?.trim().isNotEmpty ?? false)
                _layer(context, 'Standardized', value.normalized),
              if (resolution != null && resolution.evidenceIds.isNotEmpty)
                Text(
                  '${resolution.evidenceIds.length} retained '
                  '${resolution.evidenceIds.length == 1 ? 'evidence reference' : 'evidence references'}',
                  style: ui.type.bodySmall,
                ),
            ],
          ),
        ),
      EvidenceDrawer(
        title: 'Research details',
        section: fieldLabel,
        payload: {
          'field_key': field.fieldKey,
          'work_state': field.workState.name,
          'value': field.value.json,
          'blocker_code': field.blockerCode,
          'actions': field.actions,
          if (field.checkpoint != null) 'checkpoint': field.checkpoint!.json,
        },
      ),
    ];
  }

  String get _historicalBanner {
    final String? canonical = canonicalRevision == null
        ? null
        : 'record revision $canonicalRevision';
    final String? saved = reviewSavedRevision == null
        ? null
        : 'review saved at revision $reviewSavedRevision';
    final String revisions = [?canonical, ?saved].join('; ');
    return revisions.isEmpty
        ? 'Historical research report. Candidate actions are unavailable because current selection tokens were removed after review was saved.'
        : 'Historical research report for $revisions. Candidate actions are unavailable because current selection tokens were removed after review was saved.';
  }

  String _reviewExplanation(ResearchResolution resolution) {
    final reason = resolution.reason.trim();
    // Machine reasons remain in the audit payload, never guessed into science.
    if (reason.contains(' ') &&
        !RegExp(r'[_{}\[\]]|[a-f0-9]{32,}').hasMatch(reason)) {
      return reason;
    }
    return switch (resolution.workState) {
      ResearchWorkState.pending => 'Research has not started for this field.',
      ResearchWorkState.researching => 'Research is in progress.',
      ResearchWorkState.resolved => 'Research recorded a value for this field.',
      ResearchWorkState.waitingSource =>
        'A supporting source is needed before research can continue.',
      ResearchWorkState.waitingPolicy =>
        'Research is waiting for the collection’s policy decision.',
      ResearchWorkState.retryScheduled => 'A research retry is queued.',
      ResearchWorkState.operationalFailed =>
        'Research was interrupted. The current value has not been resolved.',
      ResearchWorkState.waitingHuman => 'A reviewer decision is needed.',
      ResearchWorkState.nonblockingException =>
        'Research recorded an exception for this field.',
      ResearchWorkState.cancelled => 'Research was cancelled for this field.',
      ResearchWorkState.unknown => 'Research status is unavailable.',
    };
  }

  String _sourceDisplayName(String sourceId) => switch (sourceId) {
    'global_names_verifier' => 'Global Names Verifier',
    'catalogue_of_life' => 'Catalogue of Life',
    'gbif' => 'GBIF',
    'bugguide' => 'BugGuide',
    'mapcarta' => 'Mapcarta',
    'geolocate' => 'GEOLocate',
    'field_museum_ipt' => 'Field Museum IPT',
    'field_museum_emudata' => 'Field Museum EMu data',
    _ => 'Research source',
  };

  String _coverageStatus(String state) => switch (state) {
    'not_attempted' => 'Search has not started.',
    'unqualified' => 'Source needs qualification before use.',
    'inaccessible' => 'Source is unavailable.',
    'schema_only' =>
      'Source structure is available; records have not been searched.',
    'failed' => 'Search could not be completed.',
    'searched' => 'Search completed.',
    'exhausted' => 'Search completed within the recorded scope.',
    _ => 'Source status is unavailable.',
  };
}
