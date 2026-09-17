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
    this.onUpload,
  });

  final SourceRepository repository;
  final CollectionScope scope;

  /// Opens one source.
  final void Function(RegisteredSource source) onOpen;

  /// The other way photographs arrive: uploading them from this device.
  ///
  /// Null where the host has nowhere to send the reviewer. Intake offers the
  /// way in here; this is the way back, which finding V2-4 asked for along
  /// with the heading.
  final VoidCallback? onUpload;

  /// The screen's own name (finding V2-4).
  static const String title = 'Sources';

  /// What a source is, under the name.
  static const String purpose =
      'Storage an administrator registered for this collection.';

  @override
  State<SourcesScreen> createState() => _SourcesScreenState();
}

class _SourcesScreenState extends State<SourcesScreen> {
  List<RegisteredSource>? _sources;
  ApiFailure? _error;

  /// The frame's slots. This screen takes no decision, so what it publishes
  /// is that it has none: intake is the route under this one and stays
  /// mounted, and a screen arriving says what the frame holds rather than
  /// leaving the last screen's answer standing (13 section 3.4).
  UiScaffoldSlots? _slots;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _slots = UiScaffoldSlots.of(context);
    if (ModalRoute.of(context)?.isCurrent ?? true) {
      _slots?.setActionBar(null, owner: this);
    }
  }

  @override
  void dispose() {
    _slots?.release(this);
    super.dispose();
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
    // One scroll: the heading, the way back to uploading, the rows
    // (13 section 4.5). The rows are a lazy sliver, so a collection with many
    // registered sources lays out the ones on screen.
    return CustomScrollView(
      slivers: <Widget>[
        SliverPadding(
          padding: EdgeInsetsDirectional.all(ui.space.s4),
          sliver: SliverToBoxAdapter(
            child: _SourcesHeader(
              count: sources.length,
              onUpload: widget.onUpload,
            ),
          ),
        ),
        SliverPadding(
          padding: EdgeInsetsDirectional.symmetric(horizontal: ui.space.s4),
          sliver: SliverList.builder(
            itemCount: sources.length,
            itemBuilder: (BuildContext context, int index) => _SourceTile(
              source: sources[index],
              onOpen: () => widget.onOpen(sources[index]),
            ),
          ),
        ),
        SliverToBoxAdapter(
          child: SizedBox(
            height: ui.space.s4 + UiScaffold.of(context).bottomInset,
          ),
        ),
      ],
    );
  }
}

/// The screen's name, what it holds, and the other way photographs arrive.
///
/// Finding V2-4: the registered sources list stated nothing about itself, so
/// a reviewer landed on rows under the environment band with no heading, no
/// count and no way back.
class _SourcesHeader extends StatelessWidget {
  const _SourcesHeader({required this.count, required this.onUpload});

  final int count;
  final VoidCallback? onUpload;

  /// What the count reads as. Counted, because one source is not two.
  static String registeredLabel(int count) =>
      count == 1 ? '1 source registered' : '$count sources registered';

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        Semantics(
          container: true,
          header: true,
          child: Text(
            SourcesScreen.title,
            style: ui.type.headline.copyWith(color: ui.color.ink),
          ),
        ),
        SizedBox(height: ui.space.s1),
        Semantics(
          container: true,
          child: Text(
            '${SourcesScreen.purpose} ${registeredLabel(count)}.',
            style: ui.type.body.copyWith(color: ui.color.inkSecondary),
          ),
        ),
        if (onUpload != null) ...<Widget>[
          SizedBox(height: ui.space.s4),
          UiButtonRow(
            primary: UiButton(
              label: SourcesScreenCopy.uploadLabel,
              variant: UiButtonVariant.secondary,
              leading: UiIcons.uploadFile,
              onPressed: onUpload,
            ),
          ),
        ],
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

  /// The way back to the other way photographs arrive.
  ///
  /// Intake's own control into this screen is "Add from storage"; this is its
  /// return, worded as what it does rather than as where it goes.
  static const String uploadLabel = 'Upload from this device';

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
