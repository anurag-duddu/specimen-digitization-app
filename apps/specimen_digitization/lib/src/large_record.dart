import 'dart:convert';
import 'package:flutter/material.dart';
import 'models.dart';

/// Loads the complete, verified artifact but renders only one bounded text page.
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
  static const pageSize = 12000;
  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final receipt = widget.specimen.data['artifact_receipt'] as Map;
      final result = await widget.load!(
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
              : 'Evidence unavailable. Retry to read the same revision.',
        );
      }
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  void _select(String section) {
    _section = section;
    final value = section == 'Envelope'
        ? ({..._artifact!}..remove('run'))
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

  @override
  Widget build(BuildContext context) {
    final receipt = widget.specimen.data['artifact_receipt'] as Map;
    final pages = (_text.length / pageSize).ceil().clamp(1, 100000);
    final pageText = _text.substring(
      _boundary(_page * pageSize),
      _boundary((_page + 1) * pageSize),
    );
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text(
          'Large record · Revision ${widget.specimen.revision}',
          style: Theme.of(context).textTheme.titleLarge,
        ),
        if (widget.specimen.data['mutation_saved'] == true ||
            receipt['mutation_committed'] == true)
          Text(
            'Action saved at revision ${widget.specimen.revision}. Do not repeat it. The complete evidence requires separate retrieval.',
          ),
        const Text(
          'The standard workspace exceeds its response limit. Complete evidence is available as a read-only artifact. Field edits and approval are unavailable in this view.',
        ),
        Text(
          'Retained artifact: ${receipt['artifact_size_bytes']} bytes · SHA-256 ${receipt['artifact_sha256']}',
        ),
        if (widget.specimen.data['artifact_summary_error'] != null)
          Text(widget.specimen.data['artifact_summary_error']),
        if (_artifact == null)
          OutlinedButton(
            onPressed: _loading || widget.load == null ? null : _load,
            child: Text(
              _loading
                  ? 'Loading complete evidence…'
                  : 'Load complete evidence',
            ),
          ),
        if (_error != null)
          Text(
            _error!,
            style: TextStyle(color: Theme.of(context).colorScheme.error),
          ),
        if (_artifact != null) ...[
          const Text(
            'Complete artifact verified. Choose a section; every text page remains available.',
          ),
          Semantics(
            container: true,
            child: DropdownButtonFormField<String>(
              initialValue: _section,
              isExpanded: true,
              decoration: const InputDecoration(labelText: 'Evidence section'),
              items:
                  [
                        'Envelope',
                        ...(_artifact!['run'] as Map).keys.cast<String>(),
                      ]
                      .map(
                        (key) => DropdownMenuItem(value: key, child: Text(key)),
                      )
                      .toList(),
              onChanged: (value) {
                if (value != null) setState(() => _select(value));
              },
            ),
          ),
          Wrap(
            spacing: 12,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: [
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
          Semantics(
            container: true,
            label: pageText,
            excludeSemantics: true,
            child: SizedBox(
              height: 320,
              child: SingleChildScrollView(
                child: SelectionArea(child: Text(pageText)),
              ),
            ),
          ),
        ],
      ],
    );
  }
}
