import 'dart:async';

import 'package:flutter/widgets.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../api_repository.dart';
import '../models.dart';
import '../vocabulary.dart';
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
    this.builder,
  });
  final ApiSpecimenRepository repository;
  final CollectionScope collection;
  final Specimen specimen;
  final bool readOnly;

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
  StreamSubscription<ApiFailure>? _access;
  int _epoch = 0;
  String? _message;
  bool _denied = false;

  @override
  void initState() {
    super.initState();
    _subscribe();
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

  @override
  void didUpdateWidget(ResearchHost oldWidget) {
    super.didUpdateWidget(oldWidget);
    final replaced = !identical(oldWidget.repository, widget.repository);
    if (replaced ||
        oldWidget.collection.key != widget.collection.key ||
        oldWidget.specimen.id != widget.specimen.id ||
        oldWidget.specimen.revision != widget.specimen.revision ||
        oldWidget.specimen.recordVersionId != widget.specimen.recordVersionId ||
        oldWidget.readOnly != widget.readOnly) {
      _epoch++;
      _clear();
      _message = null;
      if (replaced) {
        unawaited(_access?.cancel());
        _denied = false;
        _subscribe();
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

  Widget _researchForField(
    String fieldKey,
    ValueChanged<ResearchReviewCandidate>? onSelectCandidate,
  ) {
    if (!researchFieldKeys.contains(fieldKey)) return const SizedBox.shrink();
    final controller = _controller;
    if (controller == null) {
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
    return ResearchThreadCard(
      key: ValueKey('research:${widget.specimen.id}:$fieldKey'),
      scope: controller.scope,
      recordRevision: controller.recordRevision,
      fieldKey: fieldKey,
      fieldLabel: vocabularyLabel(fieldKey),
      field: controller.thread?.field(fieldKey),
      historical: controller.thread?.historical ?? false,
      canonicalRevision: controller.thread?.canonicalRevision,
      reviewSavedRevision: controller.thread?.reviewSavedRevision,
      paused: controller.thread?.paused ?? false,
      hasUnknownState: controller.thread?.hasUnknownState ?? false,
      readOnly: controller.readOnly,
      message: controller.message,
      networkState: controller.networkState,
      fieldCentered: true,
      onSelectCandidate: onSelectCandidate,
      onLoad: () => controller.ensureLoaded(),
      onRefresh: () => controller.refresh(),
      onRetry: controller.canRetry(fieldKey)
          ? () => controller.retryField(fieldKey)
          : null,
    );
  }
}
