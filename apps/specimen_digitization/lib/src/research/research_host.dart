import 'dart:async';

import 'package:flutter/widgets.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../api_repository.dart';
import '../models.dart';
import '../vocabulary.dart';
import 'derivation_controller.dart';
import 'derivation_models.dart';
import 'derivation_repository.dart';
import 'derivation_request_sheet.dart';
import 'research_controller.dart';
import 'research_models.dart';
import 'research_repository.dart';
import 'research_thread_card.dart';

/// Production research uses the same authenticated transport as the record.
class ResearchHost extends StatefulWidget {
  const ResearchHost({
    super.key,
    required this.repository,
    required this.collection,
    required this.specimen,
    this.readOnly = false,
    this.refreshRecord,
    this.builder,
  });
  final ApiSpecimenRepository repository;
  final CollectionScope collection;
  final Specimen specimen;
  final bool readOnly;

  /// Reloads the open record after the queued canonical review save.
  final Future<void> Function()? refreshRecord;

  /// Places research beside a field while retaining one record-bound controller.
  /// The supplied function creates only that field's lazy disclosure.
  final Widget Function(
    BuildContext context,
    Widget Function(
      String fieldKey,
      ValueChanged<ResearchReviewCandidate>? onSelectCandidate,
    )
    researchForField,
  )?
  builder;

  @override
  State<ResearchHost> createState() => _ResearchHostState();
}

class _ResearchHostState extends State<ResearchHost> {
  ResearchController? _controller;
  ResearchDerivationController? _derivationController;
  StreamSubscription<ApiFailure>? _access;
  int _epoch = 0;
  String? _message;
  bool _denied = false;

  @override
  void initState() {
    super.initState();
    _subscribe();
    _createDerivationController();
    _discover();
  }

  void _subscribe() {
    _access = widget.repository.accessFailures.listen((failure) {
      if (failure.status != 401 && failure.status != 403) return;
      _epoch++;
      _clear();
      if (mounted) {
        setState(() {
          _denied = true;
          _message = failure.status == 401
              ? 'Sign in again to view research.'
              : 'Research access is unavailable for this collection.';
        });
      }
    });
  }

  void _clear() {
    _controller?.removeListener(_changed);
    _controller?.dispose();
    _controller = null;
  }

  void _disposeDerivationController() {
    _derivationController?.removeListener(_changed);
    _derivationController?.dispose();
    _derivationController = null;
  }

  void _createDerivationController() {
    _derivationController = ResearchDerivationController(
      repository: ApiResearchDerivationRepository(
        request: widget.repository.request,
      ),
      collection: widget.collection,
      specimen: widget.specimen,
      readOnly: widget.readOnly,
      accessFailures: widget.repository.accessFailures,
    )..addListener(_changed);
  }

  @override
  void didUpdateWidget(ResearchHost oldWidget) {
    super.didUpdateWidget(oldWidget);
    final replaced = !identical(oldWidget.repository, widget.repository);
    final recordChanged =
        oldWidget.collection.key != widget.collection.key ||
        oldWidget.specimen.id != widget.specimen.id ||
        oldWidget.specimen.revision != widget.specimen.revision ||
        oldWidget.specimen.recordVersionId != widget.specimen.recordVersionId ||
        oldWidget.readOnly != widget.readOnly;
    if (replaced || recordChanged) {
      _epoch++;
      _clear();
      _message = null;
      if (replaced) {
        _disposeDerivationController();
        unawaited(_access?.cancel());
        _denied = false;
        _subscribe();
        _createDerivationController();
      } else {
        _derivationController?.bind(
          collection: widget.collection,
          specimen: widget.specimen,
          readOnly: widget.readOnly,
        );
      }
      if (!_denied) _discover();
    }
  }

  void _changed() {
    if (mounted) setState(() {});
  }

  Future<void> _discover() async {
    if (_denied) return;
    final epoch = ++_epoch;
    final specimen = widget.specimen;
    final repository = ApiResearchRepository(
      request: widget.repository.request,
    );
    try {
      final scope = await repository.discover(widget.collection, specimen);
      if (!mounted || _denied || epoch != _epoch) return;
      final controller = ResearchController(
        repository: repository,
        scope: scope,
        recordRevision: specimen.revision,
        readOnly: widget.readOnly,
        accessFailures: widget.repository.accessFailures,
      );
      controller.addListener(_changed);
      if (_derivationController == null) _createDerivationController();
      setState(() {
        _controller = controller;
        _message = null;
      });
    } on ResearchFailure catch (failure) {
      if (!mounted || epoch != _epoch) return;
      setState(() {
        _denied =
            failure.kind == ResearchFailureKind.unauthenticated ||
            failure.kind == ResearchFailureKind.forbidden;
        _message = failure.message;
      });
    }
  }

  @override
  void dispose() {
    _epoch++;
    _clear();
    _disposeDerivationController();
    unawaited(_access?.cancel());
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final builder = widget.builder;
    if (builder != null) return builder(context, _researchForField);
    final controller = _controller;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: [
        Text('Field research', style: context.ui.type.label),
        if (controller == null) ...[
          Text(_message ?? 'Checking this record’s research.'),
          if (_message != null && !_denied)
            UiButton(
              label: 'Refresh research',
              onPressed: () {
                setState(() => _message = null);
                _discover();
              },
            ),
        ] else
          for (final key in researchFieldKeys)
            ResearchThreadCard(
              key: ValueKey('research:${widget.specimen.id}:$key'),
              scope: controller.scope,
              recordRevision: controller.recordRevision,
              fieldKey: key,
              fieldLabel: vocabularyLabel(key),
              field: controller.thread?.field(key),
              historical: controller.thread?.historical ?? false,
              canonicalRevision: controller.thread?.canonicalRevision,
              reviewSavedRevision: controller.thread?.reviewSavedRevision,
              paused: controller.thread?.paused ?? false,
              hasUnknownState: controller.thread?.hasUnknownState ?? false,
              readOnly: controller.readOnly,
              message: controller.message,
              networkState: controller.networkState,
              onLoad: () => controller.ensureLoaded(),
              onRefresh: () => controller.refresh(),
              onRetry: controller.canRetry(key)
                  ? () => controller.retryField(key)
                  : null,
            ),
      ],
    );
  }

  Future<void> _loadFieldResearch(String fieldKey) async {
    if (fieldKey == 'country') {
      final derivation = _derivationController;
      if (derivation != null &&
          (derivation.capability == null ||
              derivation.state == DerivationNetworkState.error)) {
        unawaited(derivation.loadCapability());
      }
    }
    final controller = _controller;
    if (controller == null) return;
    unawaited(controller.ensureLoaded());
  }

  Future<void> _requestLocationSuggestions() async {
    final derivation = _derivationController;
    final capability = derivation?.capability;
    if (!mounted ||
        derivation == null ||
        capability == null ||
        !derivation.canRequest) {
      return;
    }
    final choice = await showResearchDerivationRequest(
      context,
      eligibleFields: capability.eligibleFields,
    );
    if (!mounted || choice == null || !derivation.canRequest) return;
    await derivation.request(
      fields: choice.fields,
      reason: choice.reason,
      refreshRecord: widget.refreshRecord ?? () async {},
    );
  }

  String? _derivationStatus(ResearchDerivationController? controller) {
    if (controller == null) return null;
    if (controller.state == DerivationNetworkState.loading) {
      return 'Checking location suggestions.';
    }
    if (controller.state == DerivationNetworkState.submitting) {
      return 'Saving your request.';
    }
    final result = controller.result;
    if (result?.stale == true) {
      return 'The record changed. Refresh this record before reviewing suggestions.';
    }
    final capability = controller.capability;
    if (capability != null &&
        (!capability.available || capability.eligibleFields.isEmpty)) {
      return 'Location suggestions are not available for this record.';
    }
    if (controller.state == DerivationNetworkState.error) {
      return controller.message;
    }
    if (controller.message != null) return controller.message;
    return switch (result?.status) {
      'queued' => 'Your location request is waiting to start.',
      'running' => 'Your location request is in progress.',
      'blocked' => 'No suggestions are ready. Your saved values are unchanged.',
      'completed' when result!.proposals.isEmpty =>
        'No additional location suggestions were prepared.',
      _ => null,
    };
  }

  Widget _researchForField(
    String fieldKey,
    ValueChanged<ResearchReviewCandidate>? onSelectCandidate,
  ) {
    if (!researchFieldKeys.contains(fieldKey)) return const SizedBox.shrink();
    final controller = _controller;
    if (controller == null) {
      if (fieldKey == 'country') {
        final derivation = _derivationController;
        return UiDisclosure(
          title: 'Research',
          summary: 'Check the saved location for suggestions',
          hideSummaryWhenExpanded: true,
          onExpansionChanged: (expanded) {
            if (expanded) unawaited(_loadFieldResearch(fieldKey));
          },
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text(
                _message ?? 'Research history is not available right now.',
                style: context.ui.type.bodySmall,
              ),
              if (_derivationStatus(derivation) case final status?) ...[
                SizedBox(height: context.ui.space.s2),
                Semantics(
                  liveRegion: true,
                  child: Text(status, style: context.ui.type.bodySmall),
                ),
              ],
              if (derivation?.canRequest ?? false) ...[
                SizedBox(height: context.ui.space.s2),
                UiButton(
                  label: 'Fill the rest',
                  busyLabel: 'Saving request',
                  variant: UiButtonVariant.secondary,
                  leading: UiIcons.search,
                  onPressed: _requestLocationSuggestions,
                  loading:
                      derivation?.state == DerivationNetworkState.submitting,
                ),
              ],
              if (derivation?.accepted != null &&
                  derivation?.state == DerivationNetworkState.ready)
                UiButton(
                  label: 'Refresh suggestion status',
                  variant: UiButtonVariant.ghost,
                  onPressed: () => unawaited(
                    derivation!.refreshResult(
                      refreshRecord: widget.refreshRecord ?? () async {},
                    ),
                  ),
                  leading: UiIcons.reload,
                ),
              if (_message != null && !_denied)
                UiButton(
                  label: 'Refresh research',
                  variant: UiButtonVariant.ghost,
                  onPressed: () {
                    setState(() => _message = null);
                    _discover();
                  },
                ),
            ],
          ),
        );
      }
      return Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text('Research', style: context.ui.type.label),
          Text(_message ?? 'Checking this record’s research.'),
          if (_message != null && !_denied)
            UiButton(
              label: 'Refresh research',
              variant: UiButtonVariant.ghost,
              onPressed: () {
                setState(() => _message = null);
                _discover();
              },
            ),
        ],
      );
    }
    final thread = controller.thread;
    final field = thread?.field(fieldKey);
    final derivation = _derivationController;
    final historical = thread?.historical ?? false;
    return ResearchThreadCard(
      key: ValueKey('research:${widget.specimen.id}:$fieldKey'),
      scope: controller.scope,
      recordRevision: controller.recordRevision,
      fieldKey: fieldKey,
      fieldLabel: vocabularyLabel(fieldKey),
      field: field,
      historical: historical,
      canonicalRevision: thread?.canonicalRevision,
      reviewSavedRevision: thread?.reviewSavedRevision,
      paused: thread?.paused ?? false,
      hasUnknownState: thread?.hasUnknownState ?? false,
      readOnly: controller.readOnly,
      message: controller.message,
      networkState: controller.networkState,
      fieldCentered: true,
      onSelectCandidate: onSelectCandidate,
      derivationProposals: derivation?.hasCurrentResult == true
          ? derivation!.result!.proposalsFor(fieldKey)
          : const <ResearchDerivationProposal>[],
      canSelectDerivationProposals:
          !widget.readOnly &&
          derivation?.hasCurrentResult == true &&
          derivation?.state == DerivationNetworkState.ready &&
          derivation?.result?.stale != true,
      fillRestAvailable:
          fieldKey == 'country' && (derivation?.canRequest ?? false),
      fillRestLoading: derivation?.state == DerivationNetworkState.submitting,
      fillRestStatus: fieldKey == 'country'
          ? _derivationStatus(derivation)
          : null,
      onFillRest: _requestLocationSuggestions,
      onRefreshDerivation:
          fieldKey == 'country' &&
              derivation?.accepted != null &&
              derivation?.state == DerivationNetworkState.ready
          ? () => unawaited(
              derivation!.refreshResult(
                refreshRecord: widget.refreshRecord ?? () async {},
              ),
            )
          : null,
      onLoad: () => unawaited(_loadFieldResearch(fieldKey)),
      onRefresh: () {
        unawaited(controller.refresh());
        if (fieldKey == 'country') unawaited(derivation?.loadCapability());
      },
      onRetry: controller.canRetry(fieldKey)
          ? () => controller.retryField(fieldKey)
          : null,
    );
  }
}
