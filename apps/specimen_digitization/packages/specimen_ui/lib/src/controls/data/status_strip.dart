/// The status strip (13 section 3.2, `UiStatusStrip`).
library;

import 'dart:async' show unawaited;
import 'dart:math' as math;

import 'package:flutter/widgets.dart';

import '../../foundation/density.dart';
import '../../foundation/icons.dart';
import '../../foundation/theme.dart';
import '../../foundation/type.dart';
import '../../primitives/label.dart';
import '../../primitives/pressable.dart';
import '../../primitives/fit.dart';
import '../actions/icon_button.dart';
import '../overlays/sheet.dart';
import 'list_row.dart';

/// One thing standing between the record and a decision.
@immutable
class UiBlocker {
  /// Names a blocker, and the control that clears it.
  ///
  /// [actionLabel] and [onAction] are the control: a blocker the reviewer can
  /// do something about carries the way to do it, and one they cannot is a
  /// statement with no role, which is what a row with nothing to do publishes
  /// (10 section 4.5).
  const UiBlocker({
    required this.label,
    this.detail,
    this.actionLabel,
    this.onAction,
  }) : assert(
         (actionLabel == null) == (onAction == null),
         'a blocker offers both a control and a label for it, or neither',
       );

  /// What is blocking, in the reviewer's words.
  final String label;

  /// One supporting line. Null where the label is the whole statement.
  final String? detail;

  /// What the control that clears it is called. Verb first
  /// (02 section 4.3).
  final String? actionLabel;

  /// What that control does.
  final VoidCallback? onAction;
}

/// What blocks a decision, and the one line that summarises it.
@immutable
class UiBlockers {
  /// Binds [summary] to the [items] the sheet lists.
  const UiBlockers({
    required this.summary,
    required this.items,
    this.sheetTitle,
  });

  /// The line the strip carries, such as the count and what it blocks.
  ///
  /// The caller's words. A count in a sentence is product copy and a design
  /// system does not write it (02 section 6).
  final String summary;

  /// Each blocker, in the order the reviewer should read them.
  final List<UiBlocker> items;

  /// The sheet's title. Defaults to [summary].
  final String? sheetTitle;
}

/// The resolved measurements of one status strip (10 section 1.5).
@immutable
class UiStatusStripStyle {
  /// Binds every token the strip draws with.
  const UiStatusStripStyle({
    required this.minHeight,
    required this.gap,
    required this.fact,
    required this.factColor,
    required this.summary,
    required this.summaryColor,
    required this.radius,
    required this.sheetGap,
    required this.partMin,
  });

  /// The strip's own height, before a control's hit box floors it.
  ///
  /// 40 dp, which is what 13 section 4.1 budgets for it. The blockers summary
  /// opens a sheet, so it is a control, and a control's hit box is 48 in both
  /// densities and is never shrunk: a strip that carries one is 48 and a
  /// strip that carries none is 40.
  final double minHeight;

  /// The gap between the disposition, the facts and the summary.
  final double gap;

  /// The type role the facts are set in.
  final TextStyle fact;

  /// The ink the facts are drawn in.
  final Color factColor;

  /// The type role the blockers summary is set in.
  final TextStyle summary;

  /// The ink the blockers summary is drawn in.
  final Color summaryColor;

  /// The summary control's corner radius.
  final double radius;

  /// The gap between two rows of the blockers sheet.
  final double sheetGap;

  /// The least width the disposition slot and the facts are each given
  /// before the summary drops its word (11 section 3.3, rule 3).
  final double partMin;

  /// The style for [ui].
  static UiStatusStripStyle resolve(UiThemeData ui) => UiStatusStripStyle(
    minHeight: ui.space.s10,
    gap: ui.space.s3,
    fact: ui.type.label,
    factColor: ui.color.inkSecondary,
    summary: ui.type.label,
    // The summary is the one thing on the line that asks to be acted on, so
    // it carries full ink where the facts carry secondary. It is not a status
    // colour: what blocks a decision is stated by the blockers, and a line
    // tinted red would be the strip judging them (09 section 3.2).
    summaryColor: ui.color.ink,
    radius: ui.shape.inner,
    sheetGap: ui.space.s2,
    partMin: ui.space.labelMin,
  );

  /// What separates two facts on the line.
  static const String factSeparator = '  ·  ';
}

/// One line at the top of the evidence: where the record stands, what made it
/// and what is holding it up.
///
/// It scrolls with the evidence rather than pinning, so it costs the chrome
/// budget nothing (13 sections 2.3 and 4.1). Everything on it is one line:
/// the [disposition] slot, the [facts] joined into a single [UiLabel], and
/// the [blockers] summary, which opens a sheet listing each blocker with the
/// control that clears it.
///
/// ```dart
/// UiStatusStrip(
///   disposition: StatusChip(status: record.status),
///   facts: <String>['Run 42', 'Version 3'],
///   blockers: UiBlockers(
///     summary: '2 things block clearance',
///     items: <UiBlocker>[
///       UiBlocker(
///         label: 'Label coverage is not confirmed',
///         actionLabel: 'Correct label regions',
///         onAction: openRegionEditor,
///       ),
///     ],
///   ),
/// )
/// ```
class UiStatusStrip extends StatelessWidget {
  /// A strip stating [disposition], [facts] and [blockers].
  const UiStatusStrip({
    super.key,
    this.disposition,
    this.facts = const <String>[],
    this.blockers,
    this.onBlockers,
    this.closeLabel = defaultCloseLabel,
    this.style,
  });

  /// Where the record stands: a status chip the caller builds.
  ///
  /// A slot, because a disposition is product vocabulary and this family
  /// draws no vocabulary of its own (10 section 1.1).
  final Widget? disposition;

  /// What made the reading: the run and the version, in that order.
  ///
  /// Joined onto one line with [UiStatusStripStyle.factSeparator] and drawn
  /// as one label, so the line ellipsises at its end rather than dropping a
  /// fact the reviewer was reading.
  final List<String> facts;

  /// What is holding the decision up, or null where nothing is.
  final UiBlockers? blockers;

  /// What pressing the summary does.
  ///
  /// Null shows [UiBlockersSheet], which lists each blocker with the control
  /// that clears it and is what 13 section 3.2 asks for. A screen that
  /// presents them somewhere of its own, a panel beside the evidence on a
  /// wide window, passes its own.
  final VoidCallback? onBlockers;

  /// What the control that closes the blockers sheet is called.
  final String closeLabel;

  /// Overrides the resolved style. A code review event (10 section 1.5).
  final UiStatusStripStyle? style;

  /// The default label of the control that closes the blockers sheet.
  static const String defaultCloseLabel = 'Close';

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final UiStatusStripStyle paint = style ?? UiStatusStripStyle.resolve(ui);
    final UiBlockers? blocking = blockers;
    if (blocking == null) {
      return _line(context, paint, summary: null);
    }
    // **Fit** (11 section 3.3; clause 15). Two arrangements. The summary
    // keeps its words while the line holds them; below that it drops to its
    // glyph, with the words on the tooltip and on the semantics label, which
    // is the rung the list row's trailing already has. The facts ellipsise
    // last, because a run and a version read from their start.
    final double summaryWidth =
        UiIconSize.small.dimension +
        ui.space.s2 +
        measureLabel(context, blocking.summary, paint.summary).width;
    final double reserved =
        (disposition == null ? 0 : paint.partMin + paint.gap) +
        (facts.isEmpty ? 0 : paint.partMin) +
        paint.gap;
    return FitBuilder(
      variants: <FitVariant>[
        FitVariant(
          intrinsicWidth: reserved + summaryWidth,
          builder: (BuildContext context, bool _) => _line(
            context,
            paint,
            summary: _BlockersSummary(
              blockers: blocking,
              style: paint,
              closeLabel: closeLabel,
              onPressed: onBlockers,
              words: true,
            ),
          ),
        ),
        FitVariant(
          intrinsicWidth: 0,
          builder: (BuildContext context, bool _) => _line(
            context,
            paint,
            summary: _BlockersSummary(
              blockers: blocking,
              style: paint,
              closeLabel: closeLabel,
              onPressed: onBlockers,
              words: false,
            ),
          ),
        ),
      ],
    );
  }

  Widget _line(
    BuildContext context,
    UiStatusStripStyle paint, {
    required Widget? summary,
  }) => ConstrainedBox(
    constraints: BoxConstraints(minHeight: paint.minHeight),
    child: Row(
      children: <Widget>[
        if (disposition != null) ...<Widget>[
          disposition!,
          SizedBox(width: paint.gap),
        ],
        // The facts take the line the summary leaves, so a short run sits
        // next to the disposition and the summary stays at the end.
        if (facts.isEmpty)
          const Spacer()
        else
          Expanded(
            child: UiLabel(
              facts.join(UiStatusStripStyle.factSeparator),
              style: paint.fact.copyWith(color: paint.factColor),
            ),
          ),
        if (summary != null) ...<Widget>[SizedBox(width: paint.gap), summary],
      ],
    ),
  );
}

/// The blockers summary, and the sheet behind it.
class _BlockersSummary extends StatelessWidget {
  const _BlockersSummary({
    required this.blockers,
    required this.style,
    required this.closeLabel,
    required this.onPressed,
    required this.words,
  });

  final UiBlockers blockers;
  final UiStatusStripStyle style;
  final String closeLabel;
  final VoidCallback? onPressed;

  /// True while the line has room for the summary's words.
  final bool words;

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final UiDensity density = Density.of(context);
    if (!words) {
      // The glyph rung. The words are on the tooltip and on the semantics
      // label, so a pointer reviewer reads them and a screen reader hears
      // exactly what it heard at 1400 dp (11 section 3.3, rule 4).
      return UiIconButton(
        icon: UiIcons.blocked,
        semanticsLabel: blockers.summary,
        tooltip: blockers.summary,
        onPressed: () => _press(context),
      );
    }
    final double height = math.max(
      UiDensity.hitBox,
      UiType.controlHeightFor(density, style.summary, context),
    );
    return Pressable(
      semanticsLabel: blockers.summary,
      onPressed: () => _press(context),
      radius: style.radius,
      builder: (BuildContext context, Set<WidgetState> states) => SizedBox(
        height: height,
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            UiIcon(
              UiIcons.blocked,
              size: UiIconSize.small,
              color: style.summaryColor,
            ),
            SizedBox(width: ui.space.s2),
            Flexible(
              child: UiLabel(
                blockers.summary,
                style: style.summary.copyWith(color: style.summaryColor),
              ),
            ),
          ],
        ),
      ),
    );
  }

  void _press(BuildContext context) {
    if (onPressed != null) {
      onPressed!();
      return;
    }
    unawaited(
      UiBlockersSheet.show(
        context: context,
        blockers: blockers,
        closeLabel: closeLabel,
        gap: style.sheetGap,
      ),
    );
  }
}

/// The sheet behind a status strip's blockers summary (13 section 3.2).
///
/// One row per blocker: what is blocking, the line under it that says more,
/// and the control that clears it. A blocker the reviewer cannot act on is a
/// row with nothing to do, which publishes one node with no role rather than
/// announcing a button that is not there (10 section 4.5).
///
/// Public because a screen may reach the same list from somewhere other than
/// the strip: a top bar command on a wide window, or a link out of an empty
/// state. There is one list and one presentation of it either way.
abstract final class UiBlockersSheet {
  /// Shows [blockers] and returns when the sheet closes.
  static Future<void> show({
    required BuildContext context,
    required UiBlockers blockers,
    String closeLabel = UiStatusStrip.defaultCloseLabel,
    double? gap,
  }) {
    final double spacing = gap ?? context.ui.space.s2;
    return UiSheet.show<void>(
      context: context,
      title: blockers.sheetTitle ?? blockers.summary,
      dismissLabel: closeLabel,
      body: (BuildContext context) => Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          for (final UiBlocker blocker in blockers.items)
            Padding(
              padding: EdgeInsetsDirectional.only(bottom: spacing),
              child: UiListRow(
                title: blocker.label,
                subtitle: blocker.detail,
                trailing: blocker.actionLabel == null
                    ? null
                    : UiRowTrailing(
                        label: blocker.actionLabel!,
                        icon: UiIcons.next,
                      ),
                // The sheet closes on the way to the control: a reviewer who
                // has chosen what to correct is finished with the list of
                // what is wrong.
                onPressed: blocker.onAction == null
                    ? null
                    : () {
                        Navigator.of(context).pop();
                        blocker.onAction!();
                      },
              ),
            ),
        ],
      ),
    );
  }
}
