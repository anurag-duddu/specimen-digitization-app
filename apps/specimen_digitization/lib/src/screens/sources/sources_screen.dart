/// The registered sources a collection may add from (07 section 13).
///
/// A source is configuration, not a resource: no endpoint creates one, and a
/// reviewer chooses within a source rather than naming a bucket. So this is a
/// short list a reviewer picks from, never a form. A collection with none
/// registered sees an empty state naming who can register one, which is the
/// same answer as a runtime configured with no sources at all.
library;

import 'package:flutter/widgets.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../../models.dart';
import '../../sources.dart';
import '../../widgets/source_object_row.dart';
import '../../widgets/widgets.dart';

/// The sources registered to one collection.
class SourcesScreen extends StatefulWidget {
  const SourcesScreen({
    super.key,
    required this.repository,
    required this.scope,
    required this.onOpen,
  });

  final SourceRepository repository;
  final CollectionScope scope;

  /// Opens one source.
  final void Function(RegisteredSource source) onOpen;

  @override
  State<SourcesScreen> createState() => _SourcesScreenState();
}

class _SourcesScreenState extends State<SourcesScreen> {
  List<RegisteredSource>? _sources;
  ApiFailure? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final List<RegisteredSource> sources = await widget.repository.sources(
        widget.scope,
      );
      if (mounted) setState(() => _sources = sources);
    } on ApiFailure catch (failure) {
      if (mounted) setState(() => _error = failure);
    }
  }

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final ApiFailure? failure = _error;
    if (failure != null) {
      return EmptyState(
        icon: UiIcons.syncProblem.defaultGlyph,
        title: 'Sources not loaded',
        body: failure.message,
        actionLabel: 'Retry',
        onAction: () {
          setState(() => _error = null);
          _load();
        },
      );
    }
    final List<RegisteredSource>? sources = _sources;
    if (sources == null) {
      return Padding(
        padding: EdgeInsetsDirectional.all(ui.space.s4),
        child: const Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            LoadingAnnouncement(thing: 'the registered sources'),
            SkeletonRow(),
          ],
        ),
      );
    }
    if (sources.isEmpty) {
      return EmptyState(
        icon: UiIcons.source.defaultGlyph,
        title: 'No sources registered',
        body: SourcesScreenCopy.noneBody,
      );
    }
    return ListView(
      padding: EdgeInsetsDirectional.all(ui.space.s4),
      children: <Widget>[
        for (final RegisteredSource source in sources)
          _SourceTile(source: source, onOpen: () => widget.onOpen(source)),
      ],
    );
  }
}

/// The strings on this screen, in one place so a test names them rather than
/// repeating them.
abstract final class SourcesScreenCopy {
  /// What a collection with nothing registered is told.
  ///
  /// Naming the administrator is the fix, because a reviewer cannot register a
  /// source and no endpoint exists that would let them (writing guidelines,
  /// rule 9: if you cannot say what to do, say who can).
  static const String noneBody =
      'An administrator registers the storage a collection can add from.';

  /// What a source that has never been listed says instead of a count.
  ///
  /// Never listed and empty are different facts, and a reviewer choosing
  /// between sources is owed the difference (writing guidelines, rule 14).
  static const String notListed = 'Not listed yet';
}

/// One registered source, as a row.
class _SourceTile extends StatelessWidget {
  const _SourceTile({required this.source, required this.onOpen});

  final RegisteredSource source;
  final VoidCallback onOpen;

  /// What the row says under the name.
  String get summary {
    final SourceInventory? inventory = source.inventory;
    return inventory == null
        ? SourcesScreenCopy.notListed
        : photographsLabel(inventory.objectCount);
  }

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    return UiListRow(
      title: source.displayName,
      subtitle: summary,
      semanticsLabel: '${source.displayName}, $summary',
      leading: const UiIcon(UiIcons.source),
      trailing: UiIcon(
        UiIcons.next,
        size: UiIconSize.inline,
        color: ui.color.inkTertiary,
      ),
      onPressed: onOpen,
    );
  }
}
