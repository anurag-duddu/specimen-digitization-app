/// The one live "Loading" node (10 section 4.5; 06 section 3).
///
/// The placeholders themselves are `UiSkeleton` from `specimen_ui`, drawn at
/// each call site in the shape of the content they stand for; they are
/// outside the semantics tree. This is what a screen reader hears instead.
library;

import 'package:flutter/semantics.dart';
import 'package:flutter/widgets.dart';
import 'package:specimen_ui/specimen_ui.dart';

/// The one live node that says something is loading.
///
/// Pair exactly one of these with any number of placeholders, so a screen
/// reader hears "Loading queue" once rather than hearing nothing at all from
/// a screen full of hidden boxes.
///
/// The invisible form is an announcement, not a node. A live region whose
/// child is a zero-sized box has an empty rect, an empty rect is dropped from
/// the semantics tree, and a reviewer using a screen reader then got silence
/// for the whole first load: finding V-4. A momentary event with no text on
/// screen to host it is exactly what `sendAnnouncement` is for. It is not
/// given a one-pixel box instead: a node a screen reader can focus and nobody
/// can see is worse than the announcement.
///
/// It says its phrase once per element, so a screen that can start a second
/// load of the same thing gives this a `Key` naming what is being loaded: a
/// collection, a record, a page. Without one the second load reuses the
/// element and passes in silence, because [message] has not changed and
/// nothing else on a screen of placeholders is in the semantics tree at all.
class LoadingAnnouncement extends StatefulWidget {
  const LoadingAnnouncement({
    super.key,
    required this.thing,
    this.visible = false,
  });

  /// What is loading, as a noun phrase: "queue", "evidence", "authority
  /// candidates". The word "Loading" is added here so every announcement is
  /// worded the same way.
  final String thing;

  /// When true the label is also drawn, for a wait longer than three seconds
  /// (02 section 4.7). Placeholders alone carry a shorter wait.
  final bool visible;

  /// The exact phrase this widget exposes.
  String get message => 'Loading $thing';

  @override
  State<LoadingAnnouncement> createState() => _LoadingAnnouncementState();
}

class _LoadingAnnouncementState extends State<LoadingAnnouncement> {
  @override
  void initState() {
    super.initState();
    if (!widget.visible) _announce();
  }

  @override
  void didUpdateWidget(covariant LoadingAnnouncement oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (!widget.visible && oldWidget.message != widget.message) _announce();
  }

  /// Says it once, after the frame that mounted this widget.
  void _announce() {
    final String message = widget.message;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      if (!MediaQuery.supportsAnnounceOf(context)) return;
      SemanticsService.sendAnnouncement(
        View.of(context),
        message,
        Directionality.of(context),
      );
    });
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.visible) return const SizedBox.shrink();
    final UiThemeData ui = context.ui;
    return Semantics(
      liveRegion: true,
      label: widget.message,
      excludeSemantics: true,
      child: Text(
        // The ellipsis character, never three periods.
        '${widget.message}…',
        style: ui.type.bodySmall.copyWith(color: ui.color.inkSecondary),
      ),
    );
  }
}
