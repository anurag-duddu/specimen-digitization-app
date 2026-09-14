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

import 'package:flutter/material.dart';
import 'package:material_symbols_icons/symbols.dart';

import 'models.dart';
import 'theme/icons.dart';
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

  /// Above this many sections a dropdown replaces the segmented control.
  static const int segmentedSectionLimit = 4;

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
    final ThemeData theme = Theme.of(context);
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
        Text(
          'Large record · Version ${widget.specimen.revision}',
          style: theme.textTheme.titleLarge,
        ),
        if (widget.specimen.data['mutation_saved'] == true ||
            receipt['mutation_committed'] == true)
          Semantics(
            liveRegion: true,
            child: Text(
              'Your action was saved on version '
              '${widget.specimen.revision}. Do not repeat it.',
            ),
          ),
        SizedBox(height: context.space.space2),
        const CaveatText(
          label: 'This record is too large for the normal view.',
          why:
              'You can read the complete evidence here. Editing and approval '
              'are unavailable until the record is smaller.',
        ),
        Text(
          'Evidence file ${receipt['artifact_size_bytes']} bytes',
          style: theme.textTheme.bodySmall,
        ),
        SelectableText(
          'Checksum (SHA-256) ${receipt['artifact_sha256']}',
          style: context.mono.identifier,
        ),
        if (widget.specimen.data['artifact_summary_error'] != null)
          Semantics(
            liveRegion: true,
            child: Text(
              widget.specimen.data['artifact_summary_error'].toString(),
              style: theme.textTheme.bodySmall?.copyWith(
                color: theme.colorScheme.error,
              ),
            ),
          ),
        SizedBox(height: context.space.space3),
        if (_artifact == null)
          Align(
            alignment: AlignmentDirectional.centerStart,
            child: OutlinedButton.icon(
              onPressed: _loading || widget.load == null ? null : _load,
              icon: _loading
                  ? SizedBox.square(
                      dimension: context.sizes.iconInline,
                      child: CircularProgressIndicator(
                        strokeWidth: context.shape.strokeEmphasis,
                        semanticsLabel: 'Loading the complete evidence',
                      ),
                    )
                  : const Icon(Symbols.download),
              label: Text(
                _loading
                    ? 'Loading complete evidence'
                    : 'Load complete evidence',
              ),
            ),
          ),
        if (_error != null)
          Semantics(
            liveRegion: true,
            child: Text(
              _error!,
              style: TextStyle(color: theme.colorScheme.error),
            ),
          ),
        if (_artifact != null) ...<Widget>[
          Text(
            'The complete evidence file is verified. Choose a section to read.',
            style: theme.textTheme.bodySmall,
          ),
          SizedBox(height: context.space.space2),
          _picker(context),
          SizedBox(height: context.space.space2),
          Wrap(
            spacing: context.space.space3,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: <Widget>[
              Text('Text page ${_page + 1} of $pages'),
              TextButton(
                onPressed: _page > 0 ? () => setState(() => _page--) : null,
                child: const Text('Previous text page'),
              ),
              TextButton(
                onPressed: _page + 1 < pages
                    ? () => setState(() => _page++)
                    : null,
                child: const Text('Next text page'),
              ),
            ],
          ),
          // The text keeps its own semantics: real lines a screen reader can
          // navigate, and a selection the reviewer can act on.
          SizedBox(
            height: pageHeight,
            child: SingleChildScrollView(
              child: SelectionArea(
                child: Text(pageText, style: context.mono.code),
              ),
            ),
          ),
        ],
      ],
    );
  }

  Widget _picker(BuildContext context) {
    final List<String> sections = _sections;
    final bool segmented =
        sections.length <= segmentedSectionLimit &&
        WindowClass.of(context).isAtLeast(WindowClass.medium);
    if (segmented) {
      return Align(
        alignment: AlignmentDirectional.centerStart,
        child: SingleChildScrollView(
          scrollDirection: Axis.horizontal,
          child: SegmentedButton<String>(
            segments: <ButtonSegment<String>>[
              for (final String section in sections)
                ButtonSegment<String>(value: section, label: Text(section)),
            ],
            selected: <String>{_section ?? sections.first},
            showSelectedIcon: false,
            onSelectionChanged: (Set<String> next) =>
                setState(() => _select(next.first)),
          ),
        ),
      );
    }
    return Semantics(
      container: true,
      child: DropdownButtonFormField<String>(
        initialValue: _section,
        isExpanded: true,
        decoration: const InputDecoration(labelText: 'Evidence section'),
        items: <DropdownMenuItem<String>>[
          for (final String section in sections)
            DropdownMenuItem<String>(value: section, child: Text(section)),
        ],
        onChanged: (String? value) {
          if (value != null) setState(() => _select(value));
        },
      ),
    );
  }

  static const int _maxPages = 100000;
}
