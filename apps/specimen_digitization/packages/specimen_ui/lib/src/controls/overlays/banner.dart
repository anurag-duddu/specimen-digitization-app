/// The banner (10 section 4.3, `UiBanner`).
library;

import 'dart:async' show unawaited;

import 'package:flutter/widgets.dart';

import '../../foundation/color.dart';
import '../../foundation/icons.dart';
import '../../foundation/theme.dart';
import '../../primitives/announcer.dart';
import '../../primitives/fit.dart';
import '../../primitives/label.dart';
import '../../primitives/pressable.dart';
import '../actions/button.dart';
import 'sheet.dart';

/// What a banner is reporting.
///
/// One enum rather than a boolean per case, so a banner cannot be both
/// informational and blocked, and so the fill, the text colour and the glyph
/// are chosen together (09 section 3.5).
enum UiBannerTone {
  /// A condition of the session that carries no status of its own.
  info,

  /// A build that is not production. The band the environment banner is.
  synthetic,

  /// A human affirmed it.
  cleared,

  /// Attention, not failure.
  needsReview,

  /// Shelved, not judged.
  deferred,

  /// Work is running.
  processing,

  /// Operational, not evidentiary.
  blocked,
}

/// Which of the band's two forms is drawn (13 sections 2.3 and 3.5).
enum UiBannerForm {
  /// Glyph, sentence, and the controls the band carries. The default.
  full,

  /// One `label` line on the tint, with everything else behind a tap.
  ///
  /// What a compact window gets, where a two line paragraph with a chevron
  /// spends a twelfth of the viewport on a condition of the build
  /// (13 section 2.3).
  strip,
}

/// The band form a route has asked for, published around a banner.
///
/// `UiScaffold` publishes it around its own banner slot when the routed
/// screen calls `UiScaffoldSlots.setBandCompact`, so the shell writes one
/// call site and the route decides which form it draws. A banner that names
/// its own [UiBanner.form] ignores this: an explicit form is a decision and
/// the ambient one is a default.
class UiBandForm extends InheritedWidget {
  /// Asks every banner under [child] for [form].
  const UiBandForm({super.key, required this.form, required super.child});

  /// The form to draw.
  final UiBannerForm form;

  /// The form asked for around [context], or null where nothing asked.
  static UiBannerForm? of(BuildContext context) =>
      context.dependOnInheritedWidgetOfExactType<UiBandForm>()?.form;

  @override
  bool updateShouldNotify(UiBandForm oldWidget) => oldWidget.form != form;
}

/// The resolved paint of one banner.
@immutable
class UiBannerStyle {
  /// Binds every token a banner draws with.
  const UiBannerStyle({
    required this.fill,
    required this.border,
    required this.foreground,
    required this.icon,
    required this.padding,
    required this.gap,
    required this.minHeight,
    required this.message,
    required this.detail,
    required this.messageMin,
    required this.stripPadding,
    required this.stripGap,
    required this.stripMinHeight,
    required this.stripLabel,
    required this.radius,
  });

  /// The strip's fill.
  final Color fill;

  /// The strip's edge, or null where the fill already separates it.
  ///
  /// A status band carries its own colour and needs none. An informational
  /// band is `paper`, which is also what a pane under it is, so a hairline on
  /// the top and the bottom is what makes it read as a band rather than as a
  /// stray line of text (09 section 3.1: structure comes from tone).
  final Border? border;

  /// The message, the glyph and the controls.
  final Color foreground;

  /// The glyph at the start of the strip.
  final IconSpec icon;

  /// Padding inside the strip.
  final EdgeInsetsGeometry padding;

  /// The gap between the glyph, the message and the controls.
  final double gap;

  /// The strip's minimum height.
  final double minHeight;

  /// The message's type role.
  final TextStyle message;

  /// The second line's type role.
  final TextStyle detail;

  /// The least width the message is given before the action moves under it
  /// (11 section 3.3).
  final double messageMin;

  /// Padding inside the one line strip.
  final EdgeInsetsGeometry stripPadding;

  /// The gap between the strip's glyph and its line.
  final double stripGap;

  /// The strip's own height, before the hit box floors it.
  ///
  /// 32 dp, which is what 13 section 2.3 budgets for the band at compact. A
  /// strip opens a sheet, so it is a control, and a control's hit box is 48
  /// in both densities and is never shrunk (10 section 2 clause 2): the tint
  /// fills the taller of the two rather than floating inside it. The band
  /// around a control has always been what gives in this family.
  final double stripMinHeight;

  /// The strip's type role. One `label` line (13 section 2.3).
  final TextStyle stripLabel;

  /// The strip's corner radius, for the state layer and the focus ring.
  final double radius;

  /// The style a banner of [tone] draws with in [ui].
  static UiBannerStyle resolve(UiThemeData ui, UiBannerTone tone) {
    final UiStatusColors status = ui.color.status;
    final (Color fill, Color foreground, IconSpec icon) = switch (tone) {
      // Information carries no status, so it carries no status colour: a
      // solid `paper` strip over the window's ground and its fields.
      UiBannerTone.info => (ui.color.paper, ui.color.ink, UiIcons.info),
      UiBannerTone.synthetic => (
        status.environmentSyntheticFill,
        status.environmentSyntheticOnFill,
        UiIcons.synthetic,
      ),
      UiBannerTone.cleared => (
        status.cleared.fill,
        status.cleared.onFill,
        UiIcons.cleared,
      ),
      UiBannerTone.needsReview => (
        status.needsReview.fill,
        status.needsReview.onFill,
        UiIcons.needsReview,
      ),
      UiBannerTone.deferred => (
        status.deferred.fill,
        status.deferred.onFill,
        UiIcons.deferred,
      ),
      UiBannerTone.processing => (
        status.processing.fill,
        status.processing.onFill,
        UiIcons.processing,
      ),
      UiBannerTone.blocked => (
        status.blocked.fill,
        status.blocked.onFill,
        UiIcons.blocked,
      ),
    };
    final BorderSide hairline = BorderSide(
      color: ui.color.hairline,
      width: ui.shape.stroke.hairline,
    );
    return UiBannerStyle(
      fill: fill,
      border: tone == UiBannerTone.info
          ? Border(top: hairline, bottom: hairline)
          : null,
      foreground: foreground,
      icon: icon,
      padding: EdgeInsetsDirectional.symmetric(
        horizontal: ui.space.s4,
        vertical: ui.space.s2,
      ),
      gap: ui.space.s2,
      // The strip's own height. A band with a control in it is taller,
      // because a control's hit box is 48 in both densities and a band never
      // shrinks one (10 section 2 clause 2).
      minHeight: ui.space.s6,
      message: ui.type.bodySmall,
      detail: ui.type.bodySmall,
      messageMin: ui.space.labelMin,
      stripPadding: EdgeInsetsDirectional.symmetric(
        horizontal: ui.space.s4,
        vertical: ui.space.s1,
      ),
      stripGap: ui.space.s2,
      stripMinHeight: ui.space.s8,
      stripLabel: ui.type.label,
      radius: ui.shape.none,
    );
  }

  /// The most lines a banner may ever occupy, open or closed.
  ///
  /// Not a style preference. It is the guarantee that replaces finding V-15,
  /// where the environment band wrapped to eleven lines at 200 percent text
  /// and took half the window: whatever the text scale, a banner is one line
  /// or two, and the whole sentence stays on its semantics node.
  static const int maxLines = 2;
}

/// A strip stating a condition of the session.
///
/// Full width, square cornered, in the page flow rather than over it. It
/// generalises the v1 `EnvironmentBanner`, which becomes one instance of it
/// (10 section 5).
///
/// It retires nothing: v1 had no Material banner. The rule it carries forward
/// is that a banner states an operational condition and never an input error
/// (02 section 1.3).
class UiBanner extends StatefulWidget {
  /// A strip carrying [message] at [tone].
  const UiBanner({
    super.key,
    required this.message,
    this.tone = UiBannerTone.info,
    this.detail,
    this.icon,
    this.onDismiss,
    this.dismissLabel,
    this.actionLabel,
    this.onAction,
    this.detailLabel = defaultDetailLabel,
    this.form,
    this.contact,
    this.sheetTitle,
    this.onTap,
    this.closeLabel = defaultCloseLabel,
    this.style,
  }) : assert(
         onDismiss == null || dismissLabel != null,
         'a dismiss control has no visible text, so it needs a label '
         '(10 section 11)',
       ),
       assert(
         (actionLabel == null) == (onAction == null),
         'a recovery action needs both a label and a callback',
       );

  /// The one line band: [message] on the tint, everything else behind a tap
  /// (13 section 3.5).
  ///
  /// The environment band at compact. One `label` line, no second line, no
  /// chevron: tapping it opens a sheet carrying the whole sentence, the
  /// administrator [contact] and the recovery the band offers, so nothing the
  /// full form shows is lost, only moved.
  ///
  /// The tint is 32 dp of band. A strip opens a sheet, so it is a control,
  /// and its hit box is the 48 dp this system never shrinks; the tint fills
  /// it rather than floating in it.
  const UiBanner.strip({
    super.key,
    required this.message,
    this.tone = UiBannerTone.synthetic,
    this.detail,
    this.icon,
    this.contact,
    this.sheetTitle,
    this.onTap,
    this.actionLabel,
    this.onAction,
    this.onDismiss,
    this.dismissLabel,
    this.closeLabel = defaultCloseLabel,
    this.style,
  }) : form = UiBannerForm.strip,
       detailLabel = defaultDetailLabel,
       assert(
         onDismiss == null || dismissLabel != null,
         'a dismiss control has no visible text, so it needs a label '
         '(10 section 11)',
       ),
       assert(
         (actionLabel == null) == (onAction == null),
         'a recovery action needs both a label and a callback',
       );

  /// The one line. 90 characters is the target, 120 the maximum
  /// (02 section 7).
  final String message;

  /// What the banner is reporting.
  final UiBannerTone tone;

  /// The second line, revealed by the disclosure control.
  ///
  /// Null for a banner whose message is the whole statement. The visible line
  /// is true on its own either way (02 section 4.15).
  final String? detail;

  /// Overrides the glyph the tone chooses.
  final IconSpec? icon;

  /// What dismissing the banner does. Null for a condition that does not go
  /// away, which is what the environment band is.
  final VoidCallback? onDismiss;

  /// What the dismiss control is called. Required wherever [onDismiss] is set.
  final String? dismissLabel;

  /// The recovery the band offers, in the reviewer's words. Verb first, two
  /// to four words (02 section 4.3).
  ///
  /// 07 section 11 asks every failure class to name its own recovery, and a
  /// band that reports one without offering it leaves the reviewer to find
  /// the way back themselves.
  final String? actionLabel;

  /// What the recovery does. Null for a band that only reports.
  final VoidCallback? onAction;

  /// What the disclosure control is called.
  ///
  /// One name in both states, with `expanded` carrying which state it is in.
  /// A control that renames itself when it is pressed reads as two controls,
  /// which is why the WAI-ARIA disclosure pattern keeps the name and moves
  /// the flag. The caret is what says it visually.
  final String detailLabel;

  /// Which form to draw, or null to take the form the route asked for
  /// through [UiBandForm] and the full band where nothing asked.
  final UiBannerForm? form;

  /// Who to reach when the condition needs a person, shown in the strip's
  /// sheet under the sentence.
  ///
  /// A slot rather than a string, because an administrator is reached by an
  /// address, a row, a copyable identifier or a button depending on the
  /// deployment, and none of those is a banner's decision to make.
  final Widget? contact;

  /// The title of the strip's sheet. Defaults to [message].
  ///
  /// A question or an imperative, 40 characters or fewer, no period
  /// (02 section 4.5). The message is the fallback rather than a sentence
  /// this package invented for a product it does not know.
  final String? sheetTitle;

  /// What tapping the strip does.
  ///
  /// Null shows the package's own sheet: the whole sentence, the [contact],
  /// and the recovery the band offers. A shell that already has a place for
  /// the environment's detail passes its own. Only the strip form is
  /// tappable; the full band carries its own controls.
  final VoidCallback? onTap;

  /// What the control that closes the strip's sheet is called.
  final String closeLabel;

  /// Overrides the resolved style. A code review event (10 section 1.5).
  final UiBannerStyle? style;

  /// The default label of the disclosure control.
  static const String defaultDetailLabel = 'Show more';

  /// The default label of the control that closes the strip's sheet.
  static const String defaultCloseLabel = 'Close';

  @override
  State<UiBanner> createState() => _UiBannerState();
}

class _UiBannerState extends State<UiBanner> {
  bool _open = false;

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final UiBannerStyle style =
        widget.style ?? UiBannerStyle.resolve(ui, widget.tone);
    final UiBannerForm form =
        widget.form ?? UiBandForm.of(context) ?? UiBannerForm.full;
    if (form == UiBannerForm.strip) return _strip(context, style);
    final String? detail = widget.detail;
    final String? actionLabel = widget.actionLabel;
    final UiButton? action = actionLabel == null
        ? null
        : UiButton(
            label: actionLabel,
            variant: UiButtonVariant.ghost,
            size: UiSize.sm,
            onPressed: widget.onAction,
          );

    return DecoratedBox(
      decoration: BoxDecoration(color: style.fill, border: style.border),
      child: Padding(
        padding: style.padding,
        child: ConstrainedBox(
          constraints: BoxConstraints(minHeight: style.minHeight),
          child: _fitted(context, ui, style, detail, action),
        ),
      ),
    );
  }

  /// The one line band (13 section 3.5).
  ///
  /// A glyph, one `label` line on the tint, and nothing else drawn. The whole
  /// band is the control, because there is nothing else on it to press and a
  /// chevron beside a line this short is a second target for the same job.
  /// The semantics label is the line itself, which stands alone, and the tap
  /// hint says where the rest of it went.
  Widget _strip(BuildContext context, UiBannerStyle style) => Pressable(
    semanticsLabel: widget.message,
    onPressed: () => _stripPressed(context),
    radius: style.radius,
    builder: (BuildContext context, Set<WidgetState> states) => DecoratedBox(
      decoration: BoxDecoration(color: style.fill, border: style.border),
      child: ConstrainedBox(
        constraints: BoxConstraints(minHeight: style.stripMinHeight),
        child: Padding(
          padding: style.stripPadding,
          child: Row(
            children: <Widget>[
              UiIcon(
                widget.icon ?? style.icon,
                size: UiIconSize.small,
                color: style.foreground,
              ),
              SizedBox(width: style.stripGap),
              Expanded(
                child: Announcer(
                  child: UiLabel(
                    widget.message,
                    style: style.stripLabel.copyWith(
                      color: style.foreground,
                      // The line is locked to its own box, so a band beside a
                      // top bar keeps its height whatever glyph it carries.
                      leadingDistribution: TextLeadingDistribution.even,
                    ),
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    ),
  );

  /// What the strip keeps behind its tap: the sentence, the contact, and the
  /// recovery the band offers.
  void _stripPressed(BuildContext context) {
    final VoidCallback? own = widget.onTap;
    if (own != null) {
      own();
      return;
    }
    _openStripSheet(context);
  }

  void _openStripSheet(BuildContext context) {
    final UiThemeData ui = context.ui;
    final String? actionLabel = widget.actionLabel;
    unawaited(
      UiSheet.show<void>(
        context: context,
        title: widget.sheetTitle ?? widget.message,
        dismissLabel: widget.closeLabel,
        body: (BuildContext context) => Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            Text(widget.detail ?? widget.message, style: ui.type.body),
            if (widget.contact != null) ...<Widget>[
              SizedBox(height: ui.space.s4),
              widget.contact!,
            ],
          ],
        ),
        primaryAction: actionLabel == null
            ? null
            : (BuildContext sheetContext) => UiButton(
                label: actionLabel,
                onPressed: () {
                  Navigator.of(sheetContext).pop();
                  widget.onAction?.call();
                },
              ),
        secondaryAction: widget.onDismiss == null
            ? null
            : (BuildContext sheetContext) => UiButton(
                label: widget.dismissLabel!,
                variant: UiButtonVariant.ghost,
                onPressed: () {
                  Navigator.of(sheetContext).pop();
                  widget.onDismiss?.call();
                },
              ),
      ),
    );
  }

  /// The band's two arrangements (11 section 3.3).
  ///
  /// A band with no recovery has one: the strip is a glyph, a sentence and
  /// the controls that belong to the band itself. A band that offers a
  /// recovery moves it under the sentence rather than squeezing the words,
  /// because the sentence is content and the recovery is the point of the
  /// band. The disclosure and the dismiss stay on the first line either way:
  /// they act on the band, not on what it reports.
  Widget _fitted(
    BuildContext context,
    UiThemeData ui,
    UiBannerStyle style,
    String? detail,
    UiButton? action,
  ) {
    Widget strip({required bool withAction}) => Row(
      crossAxisAlignment: CrossAxisAlignment.center,
      children: <Widget>[
        UiIcon(
          widget.icon ?? style.icon,
          size: UiIconSize.inline,
          color: style.foreground,
        ),
        SizedBox(width: style.gap),
        Expanded(child: _words(style, detail)),
        if (withAction && action != null) ...<Widget>[
          SizedBox(width: style.gap),
          action,
        ],
        if (detail != null) ...<Widget>[
          SizedBox(width: style.gap),
          _BannerControl(
            label: widget.detailLabel,
            icon: _open ? UiIcons.collapse : UiIcons.expand,
            color: style.foreground,
            expanded: _open,
            onPressed: () => setState(() => _open = !_open),
          ),
        ],
        if (widget.onDismiss != null) ...<Widget>[
          SizedBox(width: style.gap),
          _BannerControl(
            label: widget.dismissLabel!,
            icon: UiIcons.close,
            color: style.foreground,
            onPressed: widget.onDismiss!,
          ),
        ],
      ],
    );

    if (action == null) {
      return FitBuilder(
        variants: <FitVariant>[
          FitVariant(
            intrinsicWidth: _chrome(context, style, detail),
            builder: (BuildContext context, bool _) => strip(withAction: false),
          ),
        ],
      );
    }
    return FitBuilder(
      variants: <FitVariant>[
        FitVariant(
          intrinsicWidth:
              _chrome(context, style, detail) +
              style.gap +
              measureLabel(context, action.label, ui.type.label).width +
              ui.space.s6,
          builder: (BuildContext context, bool _) => strip(withAction: true),
        ),
        FitVariant(
          intrinsicWidth: 0,
          builder: (BuildContext context, bool _) => Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              strip(withAction: false),
              SizedBox(height: style.gap),
              action,
            ],
          ),
        ),
      ],
    );
  }

  /// The width of everything on the strip that is not the sentence, plus the
  /// least width the sentence itself is worth drawing in.
  double _chrome(BuildContext context, UiBannerStyle style, String? detail) =>
      style.padding.resolve(Directionality.of(context)).horizontal +
      UiIconSize.inline.dimension +
      style.gap +
      style.messageMin +
      (detail == null ? 0 : style.gap + UiIconSize.inline.dimension) +
      (widget.onDismiss == null ? 0 : style.gap + UiIconSize.inline.dimension);

  /// The sentence, and the second line when it is open.
  ///
  /// Both are content and both wrap, which is the last resort 11 section 3.3
  /// gives this row. The band is still one line or two whatever the text
  /// scale, which is the guarantee that replaced finding V-15: the sentence
  /// alone may take both lines, and opening the detail gives each of them
  /// one.
  Widget _words(UiBannerStyle style, String? detail) {
    final bool open = detail != null && _open;
    final int lines = open ? 1 : UiBannerStyle.maxLines;
    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        // Only the message is the live region, so opening the second line
        // does not make a screen reader read the whole band again
        // (06 section 3).
        Announcer(
          child: Text(
            widget.message,
            style: style.message.copyWith(color: style.foreground),
            maxLines: lines,
            overflow: TextOverflow.ellipsis,
          ),
        ),
        if (open)
          Text(
            detail,
            style: style.detail.copyWith(color: style.foreground),
            maxLines: lines,
            overflow: TextOverflow.ellipsis,
          ),
      ],
    );
  }
}

/// A glyph control at the end of a banner.
///
/// The band states a condition of the build, so nothing in it animates: a band
/// that moves reads as a band reporting news (04 section 4, row 9). The caret
/// therefore swaps rather than rotating, which is the one place this family
/// departs from `UiDisclosure`.
class _BannerControl extends StatelessWidget {
  const _BannerControl({
    required this.label,
    required this.icon,
    required this.color,
    required this.onPressed,
    this.expanded,
  });

  final String label;
  final IconSpec icon;
  final Color color;
  final VoidCallback onPressed;
  final bool? expanded;

  @override
  Widget build(BuildContext context) {
    final Widget control = Pressable(
      semanticsLabel: label,
      onPressed: onPressed,
      capsule: true,
      excludeFromSemantics: expanded != null,
      builder: (BuildContext context, Set<WidgetState> states) =>
          UiIcon(icon, size: UiIconSize.inline, color: color),
    );
    if (expanded == null) return control;
    // `Pressable` has no enum member for a disclosure, so the control
    // publishes its own node and tells the pressable to publish none.
    return Semantics(
      container: true,
      excludeSemantics: true,
      button: true,
      label: label,
      expanded: expanded,
      onTap: onPressed,
      child: control,
    );
  }
}
