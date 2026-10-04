import 'dart:convert';

import 'package:flutter/widgets.dart';
import 'package:specimen_ui/specimen_ui.dart';

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
    this.networkState = ResearchNetworkState.idle,
    this.paused = false,
    this.hasUnknownState = false,
    this.readOnly = false,
    this.message,
    this.onLoad,
    this.onRefresh,
    this.onRetry,
  });
  final ResearchScope scope;
  final int recordRevision;
  final String fieldKey;
  final String fieldLabel;
  final ResearchFieldThread? field;
  final ResearchNetworkState networkState;
  final bool paused;
  final bool hasUnknownState;
  final bool readOnly;
  final String? message;
  final VoidCallback? onLoad;
  final VoidCallback? onRefresh;
  final VoidCallback? onRetry;

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
    if (field == null) return 'Load this field’s research when needed';
    final prefix = paused ? 'Paused · ' : '';
    return '$prefix${field!.workState.label}'
        '${field!.blockerCode == 'research_retry_blocked' ? ' · Retry blocked' : ''}';
  }

  String get _disabledReason {
    if (!_bound) {
      return 'Research could not be verified. Refresh the current record.';
    }
    if (_denied) return 'Research access is unavailable.';
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
                if (safeField != null) ...[
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
                if (resolution != null) ...[
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
                  if (safeField?.review != null &&
                      researchReviewApplies(safeField!.workState))
                    ResearchReviewBlock(
                      fieldLabel: fieldLabel,
                      field: safeField,
                    ),
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
                    if (safeField?.workState ==
                            ResearchWorkState.operationalFailed ||
                        (safeField?.actions.contains('retry_field') ?? false))
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

  String _sourceDisplayName(String sourceId) => researchSourceName(sourceId);

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
