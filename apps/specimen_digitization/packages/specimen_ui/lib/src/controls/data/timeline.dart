/// The timeline (10 section 4.5, `UiTimeline`).
library;

import 'package:flutter/semantics.dart';
import 'package:flutter/widgets.dart';

import '../../foundation/color.dart';
import '../../foundation/icons.dart';
import '../../foundation/theme.dart';

/// The resolved paint of one timeline.
@immutable
class UiTimelineStyle {
  /// Binds every token a timeline draws with.
  const UiTimelineStyle({
    required this.markerSize,
    required this.stroke,
    required this.markerFill,
    required this.connectorColor,
    required this.neutralTone,
    required this.title,
    required this.titleColor,
    required this.meta,
    required this.metaColor,
    required this.position,
    required this.railGap,
    required this.entryGap,
    required this.childGap,
    required this.trailingGap,
    required this.trailingRunGap,
  });

  /// The marker disc's diameter, the size of an action glyph.
  final double markerSize;

  /// The marker's ring and the connector's width.
  final double stroke;

  /// The disc behind the marker's number or glyph.
  final Color markerFill;

  /// The line from one marker to the next.
  final Color connectorColor;

  /// The ring and the content of a marker with no tone.
  final Color neutralTone;

  /// The title's type role.
  final TextStyle title;

  /// The title's colour.
  final Color titleColor;

  /// The meta line's type role.
  final TextStyle meta;

  /// The meta line's colour.
  final Color metaColor;

  /// The type role of the position drawn in a marker with no glyph.
  final TextStyle position;

  /// The gap between the rail and the content column.
  final double railGap;

  /// The gap between one entry and the next.
  final double entryGap;

  /// The gap above an entry's child.
  final double childGap;

  /// The gap between the title and the trailing beside it.
  final double trailingGap;

  /// The gap between the title and the trailing when it takes the next line.
  final double trailingRunGap;

  /// The style a timeline draws with in [ui].
  static UiTimelineStyle resolve(UiThemeData ui) => UiTimelineStyle(
    markerSize: ui.space.iconAction,
    stroke: ui.shape.stroke.emphasis,
    markerFill: ui.color.paper,
    connectorColor: ui.color.hairline,
    neutralTone: ui.color.inkSecondary,
    title: ui.type.label,
    titleColor: ui.color.ink,
    meta: ui.type.bodySmall,
    metaColor: ui.color.inkSecondary,
    position: ui.type.labelSmall,
    railGap: ui.space.s3,
    entryGap: ui.space.s4,
    childGap: ui.space.s2,
    trailingGap: ui.space.s2,
    trailingRunGap: ui.space.s1,
  );
}

/// One event in a [UiTimeline].
@immutable
class UiTimelineEntry {
  /// An event titled [title].
  const UiTimelineEntry({
    required this.title,
    this.meta,
    this.glyph,
    this.tone,
    this.trailing,
    this.child,
    this.semanticsLabel,
    this.key,
  });

  /// What happened, sentence case, no terminal period.
  final String title;

  /// One line of detail under the title: an attempt, a time, a source.
  final String? meta;

  /// The registry glyph the marker draws. Without one the marker draws the
  /// entry's position.
  final IconSpec? glyph;

  /// The status triple the marker is drawn in, or none for a neutral marker.
  ///
  /// Never the only carrier of a state: pair it with [glyph] and with words,
  /// as a status chip does (02 section 4.13).
  final UiStatusTriple? tone;

  /// Beside the title, and under it when the line cannot hold both: a word
  /// or a chip. A word is read as part of the entry's phrase, after the
  /// label; a chip that is its own semantics container keeps its own node.
  final Widget? trailing;

  /// Below the meta line: a disclosure, evidence, a control. Its controls
  /// keep their own semantics nodes.
  final Widget? child;

  /// The phrase a screen reader hears for the entry, which should stand
  /// alone. Without one it is "N of M: title, meta".
  final String? semanticsLabel;

  /// The entry's key, so a list that grows keeps each entry's state.
  final Key? key;
}

/// An ordered record of what happened, one entry per event, in the order it
/// happened.
///
/// Each entry is a marker on a rail and a column of words. The marker is a
/// disc holding the entry's position or a glyph, in the entry's tone, and a
/// connector runs from each marker to the next; the last entry has none. It
/// is the anatomy the application draws by hand for its phase steps, so a
/// sequence reads the same wherever the product shows one.
///
/// Not interactive: the timeline takes no focus, and a control inside an
/// entry's child carries its own contract. An empty timeline draws nothing,
/// because the absence is the caller's to name with an empty state.
class UiTimeline extends StatelessWidget {
  /// A timeline of [entries], in order.
  const UiTimeline({super.key, required this.entries, this.semanticsLabel});

  /// The events, first to last.
  final List<UiTimelineEntry> entries;

  /// What the list is, for a screen reader: "Lookups".
  final String? semanticsLabel;

  @override
  Widget build(BuildContext context) {
    if (entries.isEmpty) return const SizedBox.shrink();
    final UiTimelineStyle style = UiTimelineStyle.resolve(context.ui);
    return Semantics(
      container: true,
      role: SemanticsRole.list,
      label: semanticsLabel,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          for (final (int i, UiTimelineEntry entry) in entries.indexed)
            _Entry(
              key: entry.key,
              entry: entry,
              position: i + 1,
              count: entries.length,
              last: i == entries.length - 1,
              style: style,
            ),
        ],
      ),
    );
  }
}

class _Entry extends StatelessWidget {
  const _Entry({
    super.key,
    required this.entry,
    required this.position,
    required this.count,
    required this.last,
    required this.style,
  });

  final UiTimelineEntry entry;
  final int position;
  final int count;
  final bool last;
  final UiTimelineStyle style;

  String get _phrase {
    final String? meta = entry.meta;
    return entry.semanticsLabel ??
        '$position of $count: ${entry.title}${meta == null ? '' : ', $meta'}';
  }

  @override
  Widget build(BuildContext context) {
    final Color tone = entry.tone?.content ?? style.neutralTone;
    final String? meta = entry.meta;
    final Widget? trailing = entry.trailing;
    final Widget? child = entry.child;
    return Semantics(
      container: true,
      role: SemanticsRole.listItem,
      label: _phrase,
      // A `Stack` rather than an `IntrinsicHeight`: the connector runs from
      // under the marker to the foot of the entry, and a child that carries
      // a `UiLabel` measures itself with a `LayoutBuilder`, which has no
      // intrinsic dimension to give (11 section 3.3). The line is positioned
      // against the entry instead, so the entry is laid out once.
      child: Stack(
        children: <Widget>[
          if (!last)
            PositionedDirectional(
              start: (style.markerSize - style.stroke) / 2,
              top: style.markerSize,
              bottom: 0,
              width: style.stroke,
              child: ColoredBox(color: style.connectorColor),
            ),
          Padding(
            padding: EdgeInsetsDirectional.only(
              bottom: last ? 0 : style.entryGap,
            ),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                // The label already says what the marker says.
                ExcludeSemantics(
                  child: _Marker(
                    glyph: entry.glyph,
                    position: position,
                    tone: tone,
                    style: style,
                  ),
                ),
                SizedBox(width: style.railGap),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    mainAxisSize: MainAxisSize.min,
                    children: <Widget>[
                      // A wrap, so the trailing stays beside the title while
                      // the line holds both and takes the next line when it
                      // does not, rather than squeezing the title.
                      Wrap(
                        spacing: style.trailingGap,
                        runSpacing: style.trailingRunGap,
                        crossAxisAlignment: WrapCrossAlignment.center,
                        children: <Widget>[
                          ExcludeSemantics(
                            child: Text(
                              entry.title,
                              style: style.title.copyWith(
                                color: style.titleColor,
                              ),
                            ),
                          ),
                          ?trailing,
                        ],
                      ),
                      if (meta != null)
                        ExcludeSemantics(
                          child: Text(
                            meta,
                            style: style.meta.copyWith(color: style.metaColor),
                          ),
                        ),
                      if (child != null)
                        Padding(
                          padding: EdgeInsetsDirectional.only(
                            top: style.childGap,
                          ),
                          child: child,
                        ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

/// The disc on the rail: the entry's position or its glyph, in its tone.
class _Marker extends StatelessWidget {
  const _Marker({
    required this.glyph,
    required this.position,
    required this.tone,
    required this.style,
  });

  final IconSpec? glyph;
  final int position;
  final Color tone;
  final UiTimelineStyle style;

  @override
  Widget build(BuildContext context) {
    final IconSpec? spec = glyph;
    return SizedBox.square(
      dimension: style.markerSize,
      child: DecoratedBox(
        decoration: ShapeDecoration(
          shape: CircleBorder(
            side: BorderSide(color: tone, width: style.stroke),
          ),
          color: style.markerFill,
        ),
        child: Center(
          child: spec != null
              ? UiIcon(spec, size: UiIconSize.small, color: tone)
              // The disc keeps the size of a glyph at every text scale, as a
              // glyph does (09 section 7), and the number it holds repeats
              // the position the entry's label already reads whole. So the
              // number is drawn unscaled and fitted, never cut by its disc.
              : MediaQuery.withNoTextScaling(
                  child: FittedBox(
                    fit: BoxFit.scaleDown,
                    child: Text(
                      '$position',
                      style: style.position.copyWith(color: tone),
                    ),
                  ),
                ),
        ),
      ),
    );
  }
}
