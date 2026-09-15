/// The registered sources a collection may add from (screen blueprints,
/// section 13).
///
/// A source is configuration, not a resource: no endpoint creates one, and a
/// reviewer chooses within a source rather than naming a bucket. So this is a
/// short list a reviewer picks from, never a form. A collection with none
/// registered sees an empty state naming who can register one, which is the
/// same answer as a runtime configured with no sources at all.
library;

import 'package:flutter/material.dart';
import 'package:material_symbols_icons/symbols.dart';

import '../../models.dart';
import '../../sources.dart';
import '../../theme/icons.dart';
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
    final ApiFailure? failure = _error;
    if (failure != null) {
      return EmptyState(
        icon: Symbols.inventory_2,
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
        padding: EdgeInsets.all(context.space.space4),
        child: const SkeletonRow(),
      );
    }
    if (sources.isEmpty) {
      return const EmptyState(
        icon: Symbols.inventory_2,
        title: 'No sources registered',
        body: SourcesScreenCopy.noneBody,
      );
    }
    return ListView(
      padding: EdgeInsets.all(context.space.space4),
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

class _SourceTile extends StatelessWidget {
  const _SourceTile({required this.source, required this.onOpen});

  final RegisteredSource source;
  final VoidCallback onOpen;

  /// What the tile says under the name.
  String get summary {
    final SourceInventory? inventory = source.inventory;
    return inventory == null
        ? SourcesScreenCopy.notListed
        : photographsLabel(inventory.objectCount);
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return Padding(
      padding: EdgeInsets.only(bottom: context.space.space2),
      child: MergeSemantics(
        child: Semantics(
          button: true,
          label: '${source.displayName}, $summary',
          child: Material(
            type: MaterialType.transparency,
            child: InkWell(
              onTap: onOpen,
              borderRadius: BorderRadius.circular(context.shape.radiusSm),
              child: ExcludeSemantics(
                child: ConstrainedBox(
                  constraints: BoxConstraints(
                    minHeight: context.sizes.targetMin,
                  ),
                  child: Padding(
                    padding: EdgeInsets.all(context.space.space3),
                    child: Row(
                      children: <Widget>[
                        Icon(
                          Symbols.folder,
                          color: theme.colorScheme.onSurfaceVariant,
                        ),
                        SizedBox(width: context.space.space3),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            mainAxisSize: MainAxisSize.min,
                            children: <Widget>[
                              Text(
                                source.displayName,
                                style: context.mono.identifier,
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                              ),
                              SizedBox(height: context.space.space1),
                              Text(
                                summary,
                                style: theme.textTheme.bodySmall?.copyWith(
                                  color: theme.colorScheme.onSurfaceVariant,
                                ),
                              ),
                            ],
                          ),
                        ),
                        Icon(
                          Symbols.chevron_right,
                          color: theme.colorScheme.onSurfaceVariant,
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
