/// The harness's calls on one label's text, as a timeline (UI.md T2.7).
library;

import 'package:flutter/widgets.dart';

import '../../thread/thread.dart';

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

  @override
  Widget build(BuildContext context) => const SizedBox.shrink();
}
