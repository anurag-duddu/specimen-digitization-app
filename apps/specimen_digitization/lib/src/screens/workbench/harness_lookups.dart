/// The harness's calls on one label's text, as a timeline (UI.md T2.7).
///
/// Brief T2 asks for "the harness's lookups as a timeline with their typed
/// outcomes". The thread's `tool_calls` are every call the harness made, in
/// the order they ran; an ambiguous lookup adds no field evidence, so this is
/// the only place it shows. A lookup is named by its source and a check by
/// its tool, so a tool's id never reaches the screen, and a found Google
/// place is its place ID alone (G26).
library;

import 'package:flutter/widgets.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../../models.dart';
import '../../thread/thread.dart';
import '../../vocabulary.dart';

/// The calls the harness made on one label's text, in the order they ran.
class HarnessLookups extends StatelessWidget {
  /// The timeline of [calls].
  const HarnessLookups({
    super.key,
    required this.calls,
    required this.readerName,
    required this.fieldName,
  });

  /// The label's calls, in the order they ran.
  final List<ThreadToolCall> calls;

  /// The name a reader goes by, from its reading's id.
  final String Function(String? observationId) readerName;

  /// A field's name, as the record calls it.
  final String Function(String fieldKey) fieldName;

  /// The section's heading, and what a screen reader hears for the list.
  static const String title = 'Harness lookups';

  /// The checks with no source, by their tool, in the coordinator's words of
  /// 20:05Z on 2026-09-28 ("Catalog" in US spelling, the museum's field and
  /// the tool's name). Any other tool keeps its server word.
  static const Map<String, String> toolWords = <String, String>{
    'date_parser': 'Date parse',
    'catalog_number_validator': 'Catalog number check',
  };

  /// `LookupStatus` values that are the service failing, not an answer
  /// (HAR-008, the backend's `OPERATIONAL` set and its neighbours).
  static const Set<String> _couldNotComplete = <String>{
    'rate_limited',
    'timeout',
    'authentication_error',
    'authorization_error',
    'provider_error',
    'malformed_response',
    'policy_blocked',
  };

  /// Google's source id, whose ambiguous answer is several places (G36).
  static const String _googleSource = 'google-maps-geocoding';

  /// What ran: a lookup by its source, a check by its tool.
  static String titleOf(ThreadToolCall call) {
    if (call.source case final String source) {
      return '${vocabularyLabel(source)} lookup';
    }
    final String? tool = call.tool;
    if (tool == null) return 'Harness call';
    return toolWords[tool] ?? sentenceCase(vocabularyLabel(tool));
  }

  /// How it ended, in the coordinator's words of 20:05Z on 2026-09-28. Any
  /// other outcome keeps the server's word: an ambiguous answer from a source
  /// that is not Google, where "places" would not be true, and an empty one.
  static String outcomeOf(ThreadToolCall call) => switch (call.outcome) {
    'success' => 'Found',
    'ambiguous' when call.source == _googleSource => 'Several places match',
    'no_match' => 'No match',
    final String outcome when _couldNotComplete.contains(outcome) =>
      'Could not complete',
    final String outcome => sentenceCase(vocabularyLabel(outcome)),
    null => 'Outcome not recorded',
  };

  /// A field's name as [specimen] calls it, for a call's meta line.
  static String Function(String fieldKey) namesIn(Specimen specimen) =>
      (String key) {
        for (final Json field in specimen.fields) {
          if (field['field_key'] == key) {
            return textOf(field['display_name'], vocabularyLabel(key));
          }
        }
        return vocabularyLabel(key);
      };

  /// "A", "A and B", "A, B and C".
  static String _listed(List<String> items) => items.length < 2
      ? items.join()
      : '${items.sublist(0, items.length - 1).join(', ')} and ${items.last}';

  /// The text it ran on, the attempt when not the first, the fields it
  /// served, and a found Google place's ID (G26).
  String _meta(ThreadToolCall call) {
    final String? ranOn = switch (call.inputSource) {
      ThreadInputSource.rawReading =>
        "${readerName(call.observationId)}'s reading",
      ThreadInputSource.decidedTranscript => 'Decided transcript',
      ThreadInputSource.review => "Reviewer's text",
      null => switch (call.inputSourceName) {
        final String name => sentenceCase(vocabularyLabel(name)),
        null => null,
      },
    };
    final int? attempt = call.attempt;
    final List<String> fields = <String>[
      for (final String key in call.fieldKeys) fieldName(key),
    ];
    return <String>[
      ?ranOn,
      if (attempt != null && attempt > 1) 'Attempt $attempt',
      if (fields.isNotEmpty) 'For ${_listed(fields)}',
      if (call.outcome == 'success')
        for (final String place in call.placeIds) 'place ID $place',
    ].join(' · ');
  }

  UiTimelineEntry _entry(UiThemeData ui, ThreadToolCall call) {
    final String? outcome = call.outcome;
    final (UiStatusTriple?, IconSpec) marker = switch (outcome) {
      'success' when call.source != null => (
        ui.color.status.authority,
        UiIcons.authority,
      ),
      'success' => (null, UiIcons.check),
      // The field state's glyph for ambiguous (specimen_status.dart).
      'ambiguous' => (ui.color.status.needsReview, UiIcons.superseded),
      'no_match' => (ui.color.status.needsReview, UiIcons.unknown),
      final String failed when _couldNotComplete.contains(failed) => (
        ui.color.status.blocked,
        UiIcons.blocked,
      ),
      _ => (null, UiIcons.unknown),
    };
    final String meta = _meta(call);
    return UiTimelineEntry(
      title: titleOf(call),
      meta: meta.isEmpty ? null : meta,
      tone: marker.$1,
      glyph: marker.$2,
      trailing: Text(
        outcomeOf(call),
        style: ui.type.bodySmall.copyWith(
          color: marker.$1?.content ?? ui.color.inkSecondary,
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    if (calls.isEmpty) return const SizedBox.shrink();
    final UiThemeData ui = context.ui;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        Text(title, style: ui.type.label),
        SizedBox(height: ui.space.s2),
        UiTimeline(
          semanticsLabel: title,
          entries: <UiTimelineEntry>[
            for (final ThreadToolCall call in calls) _entry(ui, call),
          ],
        ),
      ],
    );
  }
}
