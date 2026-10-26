/// Composable headings for pages, sections and cards.
library;

import 'package:flutter/widgets.dart';

import '../../foundation/theme.dart';
import '../../foundation/type.dart';
import '../actions/icon_button.dart';

/// The hierarchy of a [UiSectionHeader].
enum UiSectionHeaderRole {
  /// The main heading of a page.
  page,

  /// A heading within a page.
  section,

  /// A heading within a card or table.
  card,
}

/// Token-derived heading layout and typography.
@immutable
class UiSectionHeaderStyle {
  /// Resolves the heading's hierarchy and minimum useful text allocation.
  UiSectionHeaderStyle.resolve(UiThemeData ui, UiSectionHeaderRole role)
    : title = switch (role) {
        UiSectionHeaderRole.page => ui.type.headline,
        UiSectionHeaderRole.section => ui.type.titleLarge,
        UiSectionHeaderRole.card => ui.type.title,
      }.copyWith(color: ui.color.ink),
      supporting = ui.type.bodySmall.copyWith(color: ui.color.inkSecondary),
      gap = ui.space.s2,
      groupGap = ui.space.s4,
      horizontalMin = ui.space.readingMax;

  /// The title's type role.
  final TextStyle title;

  /// Supporting copy beneath the title.
  final TextStyle supporting;

  /// Space between related text or metadata.
  final double gap;

  /// Space between the heading and its commands.
  final double groupGap;

  /// Minimum width to share a row with commands before text scaling.
  final double horizontalMin;
}

/// A responsive title, supporting sentence, metadata and action group.
///
/// Long headings wrap. Actions move beneath the text when this component's
/// actual allocation is narrow; the surrounding window size is irrelevant.
/// Actions should be owned buttons, and metadata can be a count or badge.
class UiSectionHeader extends StatelessWidget {
  /// Creates a heading with optional metadata and commands.
  const UiSectionHeader({
    super.key,
    required this.title,
    this.role = UiSectionHeaderRole.section,
    this.supporting,
    this.supportingLiveRegion = false,
    this.meta,
    this.leading,
    this.help,
    this.toolbar,
    this.tabs,
    this.trailingAction,
    this.actions = const <Widget>[],
  });

  /// The visible and accessible heading.
  final String title;

  /// The heading's place in the content hierarchy.
  final UiSectionHeaderRole role;

  /// Context that helps the reader understand this section.
  final String? supporting;

  /// Announces changes when supporting copy reports a live save or load state.
  final bool supportingLiveRegion;

  /// Count, badge or other compact supporting information.
  final Widget? meta;

  /// Optional identity/icon, help control, filter row and section navigation.
  final Widget? leading, help, toolbar, tabs;

  /// One compact command beside the heading. The title wraps independently
  /// while the command keeps its full interaction target.
  final UiIconButton? trailingAction;

  /// Commands, in reading order. They wrap without shrinking hit targets.
  final List<Widget> actions;

  @override
  Widget build(BuildContext context) {
    final UiSectionHeaderStyle style = UiSectionHeaderStyle.resolve(
      context.ui,
      role,
    );
    final Widget headingContent = Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        if (leading != null)
          Padding(
            padding: EdgeInsets.only(bottom: style.gap),
            child: leading,
          ),
        Wrap(
          spacing: style.gap,
          runSpacing: style.gap,
          crossAxisAlignment: WrapCrossAlignment.center,
          children: <Widget>[
            Semantics(header: true, child: Text(title, style: style.title)),
            ?meta,
            ?help,
          ],
        ),
        if (supporting != null) ...<Widget>[
          SizedBox(height: style.gap),
          Semantics(
            liveRegion: supportingLiveRegion,
            child: Text(supporting!, style: style.supporting),
          ),
        ],
      ],
    );
    final Widget heading = trailingAction == null
        ? headingContent
        : LayoutBuilder(
            builder: (context, constraints) => Row(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                if (constraints.hasBoundedWidth)
                  Expanded(child: headingContent)
                else
                  headingContent,
                SizedBox(width: style.gap),
                trailingAction!,
              ],
            ),
          );
    Widget complete(Widget header) => LayoutBuilder(
      builder: (context, constraints) => Column(
        crossAxisAlignment: constraints.hasBoundedWidth
            ? CrossAxisAlignment.stretch
            : CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          header,
          if (toolbar != null)
            Padding(
              padding: EdgeInsets.only(top: style.groupGap),
              child: toolbar,
            ),
          if (tabs != null)
            Padding(
              padding: EdgeInsets.only(top: style.groupGap),
              child: tabs,
            ),
        ],
      ),
    );
    if (actions.isEmpty) return complete(heading);
    final Widget commands = Wrap(
      spacing: style.gap,
      runSpacing: style.gap,
      children: actions,
    );
    return complete(
      LayoutBuilder(
        builder: (BuildContext context, BoxConstraints constraints) {
          final double scale =
              UiType.lineHeightOf(style.title, context) /
              UiType.unscaledLineHeightOf(style.title);
          if (!constraints.hasBoundedWidth ||
              constraints.maxWidth < style.horizontalMin * scale) {
            return Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: <Widget>[
                heading,
                SizedBox(height: style.groupGap),
                commands,
              ],
            );
          }
          return Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Expanded(flex: 3, child: heading),
              SizedBox(width: style.groupGap),
              Flexible(flex: 2, child: commands),
            ],
          );
        },
      ),
    );
  }
}
