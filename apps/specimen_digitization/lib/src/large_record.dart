/// The large record fallback (screen blueprints, section 9).
///
/// The behaviour is unchanged: read only, verified evidence file, paged text.
/// What changed is the presentation. The explanation is one short sentence
/// with a "Why", the section picker is a control sized to the window, and the
/// text page exposes its own real text semantics instead of one flat label
/// (accessibility, 2.2 finding 8).
///
/// Loads the complete, verified artifact but renders only one bounded text
/// page.
library;

import 'dart:convert';

import 'package:flutter/widgets.dart';
import 'package:specimen_ui/specimen_ui.dart';

import 'models.dart';
import 'widgets/widgets.dart';

class LargeRecordEvidence extends StatefulWidget {
  const LargeRecordEvidence({super.key, required this.specimen, this.load});
  final Specimen specimen;
  final Future<Json> Function(ArtifactRequest)? load;
  @override
  State<LargeRecordEvidence> createState() => _LargeRecordEvidenceState();
}

class _LargeRecordEvidenceState extends State<LargeRecordEvidence> {
  Json? _artifact;
  String? _error;
  bool _loading = false;
  String? _section;
  String _text = '';
  int _page = 0;

  /// How much of the evidence file one page shows. Reduced rather than hidden
  /// if the semantics tree ever proves too large, per the accessibility fix.
  static const int pageSize = 12000;

  /// The height of the text page. It scrolls internally, so a larger text
  /// scale reflows inside it rather than clipping.
  static const double pageHeight = 320;

  /// Above this many sections a select replaces the segmented track.
  ///
  /// `UiSegmented` takes between two and five segments; four is the count
  /// this pane has room for beside its label at a medium window.
  static const int segmentedSectionLimit = 4;

  /// The controls this pane names, fixed so the pane and its tests agree.
  static const String loadLabel = 'Load complete evidence';
  static const String loadingLabel = 'Loading complete evidence';
  static const String previousPageLabel = 'Previous text page';
  static const String nextPageLabel = 'Next text page';
  static const String sectionLabel = 'Evidence section';

  /// What the pane says on a connection that cannot reach the evidence.
  static const String unavailableBody =
      'The complete evidence cannot be loaded on this connection. Open this '
      'record again when the connection is restored.';

  /// What it says when the evidence is there to be loaded.
  static const String loadableBody =
      'The complete evidence is verified before it is shown. Load it to read '
      'the record.';

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final Map<dynamic, dynamic> receipt =
          widget.specimen.data['artifact_receipt'] as Map;
      final Json result = await widget.load!(
        ArtifactRequest(
          ArtifactKind.activeGraph,
          widget.specimen.id,
          sha256: receipt['artifact_sha256'] as String?,
        ),
      );
      if (!mounted) return;
      setState(() {
        _artifact = result;
        _select('Envelope');
      });
    } catch (e) {
      if (mounted) {
        setState(
          () => _error = e is ApiFailure
              ? e.message
              : 'Evidence unavailable. Retry to read the same version.',
        );
      }
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  void _select(String section) {
    _section = section;
    final Object? value = section == 'Envelope'
        ? (<String, dynamic>{..._artifact!}..remove('run'))
        : (_artifact!['run'] as Map)[section];
    _text = const JsonEncoder.withIndent('  ').convert(value);
    _page = 0;
  }

  // Avoid splitting astral characters between display pages.
  int _boundary(int offset) {
    if (offset >= _text.length) return _text.length;
    if (offset > 0 &&
        _text.codeUnitAt(offset) >= 0xdc00 &&
        _text.codeUnitAt(offset) <= 0xdfff) {
      return offset - 1;
    }
    return offset;
  }

  List<String> get _sections => <String>[
    'Envelope',
    ...(_artifact!['run'] as Map).keys.cast<String>(),
  ];

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final TextStyle line = ui.type.bodySmall.copyWith(
      color: ui.color.inkSecondary,
    );
    final Map<dynamic, dynamic> receipt =
        widget.specimen.data['artifact_receipt'] as Map;
    final int pages = (_text.length / pageSize).ceil().clamp(1, _maxPages);
    final String pageText = _text.substring(
      _boundary(_page * pageSize),
      _boundary((_page + 1) * pageSize),
    );

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        Semantics(
          container: true,
          header: true,
          child: Text(
            'Large record · Version ${widget.specimen.revision}',
            style: ui.type.titleLarge,
          ),
        ),
        if (widget.specimen.data['mutation_saved'] == true ||
            receipt['mutation_committed'] == true)
          Semantics(
            liveRegion: true,
            child: Text(
              'Your action was saved on version '
              '${widget.specimen.revision}. Do not repeat it.',
              style: ui.type.body,
            ),
          ),
        SizedBox(height: ui.space.s2),
        const CaveatText(
          label: 'This record is too large for the normal view.',
          why:
              'You can read the complete evidence here. Editing and approval '
              'are unavailable until the record is smaller.',
        ),
        Text(
          'Evidence file ${receipt['artifact_size_bytes']} bytes',
          style: line,
        ),
        Text(
          'Checksum (SHA-256) ${receipt['artifact_sha256']}',
          style: ui.type.mono.digest.copyWith(color: ui.color.inkSecondary),
        ),
        if (widget.specimen.data['artifact_summary_error'] != null)
          Semantics(
            liveRegion: true,
            child: Text(
              widget.specimen.data['artifact_summary_error'].toString(),
              style: ui.type.bodySmall.copyWith(
                color: ui.color.status.blocked.content,
              ),
            ),
          ),
        SizedBox(height: ui.space.s3),
        if (_artifact == null)
          // Nothing is loaded yet, so the pane is an empty state with the one
          // action that fills it (blueprint 9).
          EmptyState(
            icon: UiIcons.record.defaultGlyph,
            title: 'The evidence file is not loaded',
            body: widget.load == null ? unavailableBody : loadableBody,
            // Both or neither: the empty state asserts that a label without
            // a callback is a control that does nothing. While the request is
            // out the ring below carries the state instead.
            actionLabel: widget.load == null || _loading ? null : loadLabel,
            onAction: widget.load == null || _loading ? null : _load,
          ),
        if (_loading)
          Padding(
            padding: EdgeInsetsDirectional.only(top: ui.space.s3),
            child: Align(
              child: UiProgress.ring(
                semanticsLabel: loadingLabel,
                announce: true,
              ),
            ),
          ),
        if (_error != null)
          Semantics(
            liveRegion: true,
            child: Text(
              _error!,
              style: ui.type.body.copyWith(
                color: ui.color.status.blocked.content,
              ),
            ),
          ),
        if (_artifact != null) ...<Widget>[
          Text(
            'The complete evidence file is verified. Choose a section to read.',
            style: line,
          ),
          SizedBox(height: ui.space.s2),
          _picker(context),
          SizedBox(height: ui.space.s2),
          Wrap(
            spacing: ui.space.s3,
            runSpacing: ui.space.s2,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: <Widget>[
              Text('Text page ${_page + 1} of $pages', style: ui.type.label),
              UiButton(
                label: previousPageLabel,
                variant: UiButtonVariant.ghost,
                leading: UiIcons.previous,
                disabledReason: 'This is the first page',
                onPressed: _page > 0 ? () => setState(() => _page--) : null,
              ),
              UiButton(
                label: nextPageLabel,
                variant: UiButtonVariant.ghost,
                trailing: UiIcons.next,
                disabledReason: 'This is the last page',
                onPressed: _page + 1 < pages
                    ? () => setState(() => _page++)
                    : null,
              ),
            ],
          ),
          // The text keeps its own semantics: real lines a screen reader can
          // navigate, and a selection the reviewer can act on.
          SizedBox(
            height: pageHeight,
            child: SingleChildScrollView(
              child: SelectableEvidence(
                child: Text(pageText, style: ui.type.mono.code),
              ),
            ),
          ),
        ],
      ],
    );
  }

  /// The section picker: a segmented track where the sections fit one, and a
  /// select where they do not (blueprint 9; 11 section 3.3).
  Widget _picker(BuildContext context) {
    final List<String> sections = _sections;
    final String chosen = _section ?? sections.first;
    final bool segmented =
        sections.length >= UiSegmented.minSegments &&
        sections.length <= segmentedSectionLimit &&
        WindowClass.of(context).isAtLeast(WindowClass.medium);
    if (segmented) {
      return Align(
        alignment: AlignmentDirectional.centerStart,
        child: UiSegmented<String>(
          label: sectionLabel,
          value: chosen,
          segments: <UiSegment<String>>[
            for (final String section in sections)
              UiSegment<String>(value: section, label: section),
          ],
          onChanged: (String next) => setState(() => _select(next)),
        ),
      );
    }
    return UiSelect<String>(
      label: sectionLabel,
      placeholder: sectionLabel,
      value: chosen,
      options: <UiSelectOption<String>>[
        for (final String section in sections)
          UiSelectOption<String>(value: section, label: section),
      ],
      onChanged: (String? value) {
        if (value != null) setState(() => _select(value));
      },
    );
  }

  static const int _maxPages = 100000;
}
