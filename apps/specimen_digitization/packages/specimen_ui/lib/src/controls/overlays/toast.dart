/// The toast (10 section 4.3, `UiToast`).
library;

import 'dart:async';
import 'dart:collection';

import 'package:flutter/widgets.dart';

import '../../foundation/glass.dart';
import '../../foundation/icons.dart';
import '../../foundation/motion.dart';
import '../../foundation/theme.dart';
import '../../primitives/announcer.dart';
import '../../primitives/fit.dart';
import '../../primitives/glass_surface.dart';
import '../../primitives/modal_routes.dart';
import '../actions/button.dart';

/// One transient message.
///
/// A value rather than a widget, because the host owns the queue and has to be
/// able to hold a message that is not on screen yet.
@immutable
class UiToastData {
  /// Binds [message] to its optional glyph and action.
  const UiToastData({
    required this.message,
    this.icon,
    this.actionLabel,
    this.onAction,
  }) : assert(
         (actionLabel == null) == (onAction == null),
         'an action needs both a label and a callback',
       );

  /// The one line. 50 characters is the target, 70 the maximum
  /// (02 section 7).
  final String message;

  /// The glyph at the start of the capsule. Defaults to the information glyph.
  final IconSpec? icon;

  /// The action's label. Verb first, two to four words (02 section 4.3).
  final String? actionLabel;

  /// What the action does. Dismissing is this widget's job; the callback does
  /// only the work.
  final VoidCallback? onAction;

  /// True when the toast carries an action.
  ///
  /// A toast with an action waits for the reviewer rather than expiring, so
  /// the action is never taken away mid reach (10 section 4.3).
  bool get hasAction => onAction != null;
}

/// The resolved paint of one toast.
@immutable
class UiToastStyle {
  /// Binds every token a toast draws with.
  const UiToastStyle({
    required this.padding,
    required this.gap,
    required this.minHeight,
    required this.maxWidth,
    required this.message,
    required this.foreground,
    required this.margin,
    required this.messageMin,
  });

  /// Padding inside the capsule.
  final EdgeInsetsGeometry padding;

  /// The gap between the glyph, the message and the action.
  final double gap;

  /// The capsule's minimum height.
  final double minHeight;

  /// The widest a toast is drawn before its message wraps.
  final double maxWidth;

  /// The message's type role.
  final TextStyle message;

  /// The message and glyph colour.
  final Color foreground;

  /// The gap between the toast and the edges of the window.
  final EdgeInsetsGeometry margin;

  /// The least width the message is given before the action moves under it
  /// (11 section 3.3).
  final double messageMin;

  /// The style a toast draws with in [ui].
  static UiToastStyle resolve(UiThemeData ui) => UiToastStyle(
    padding: EdgeInsetsDirectional.fromSTEB(
      ui.space.s5,
      ui.space.s2,
      ui.space.s2,
      ui.space.s2,
    ),
    gap: ui.space.s3,
    minHeight: ui.density.controlHeight + ui.space.s2,
    maxWidth: ui.space.readingMax,
    message: ui.type.body,
    foreground: ui.color.ink,
    margin: EdgeInsetsDirectional.all(ui.space.s4),
    messageMin: ui.space.labelMin,
  );

  /// How long a toast with no action stays on screen.
  ///
  /// Six seconds, per 10 section 4.3. Long enough to read one line twice,
  /// short enough that a reviewer who looked away is not still being told.
  static const Duration showDuration = Duration(seconds: 6);

  /// How far a toast rises as it arrives. Collapsed under reduced motion.
  static const double entranceRise = 8;
}

/// A transient message in a floating capsule.
///
/// Retires `SnackBar` and `ScaffoldMessenger`. Normally raised through
/// [UiToasts.show] rather than built directly; it is public so a caller can
/// render one in place, which is what the gallery does.
class UiToast extends StatelessWidget {
  /// Draws [data] as a capsule.
  const UiToast({
    super.key,
    required this.data,
    this.onDismissed,
    this.style,
  });

  /// The message, its glyph and its action.
  final UiToastData data;

  /// Called after the action runs, so the host can advance its queue.
  final VoidCallback? onDismissed;

  /// Overrides the resolved style. A code review event (10 section 1.5).
  final UiToastStyle? style;

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final UiToastStyle paint = style ?? UiToastStyle.resolve(ui);
    return DefaultTextStyle(
      // The capsule is a layer over a page and can be raised from anywhere,
      // so it publishes the product's style rather than inheriting the host's
      // (11 section 5).
      style: ui.defaultTextStyle,
      child: _capsule(ui, paint),
    );
  }

  Widget _capsule(UiThemeData ui, UiToastStyle paint) {
    final Widget glyph = UiIcon(
      data.icon ?? UiIcons.info,
      size: UiIconSize.inline,
      color: paint.foreground,
    );
    // Only the message is inside the live region, so a screen reader is told
    // the news once and the action announces itself as the control it is
    // (06 section 3).
    final Widget words = Announcer(
      child: Text(
        data.message,
        style: paint.message.copyWith(color: paint.foreground),
      ),
    );
    final UiButton? action = data.hasAction
        ? UiButton(
            label: data.actionLabel!,
            variant: UiButtonVariant.ghost,
            onPressed: () {
              data.onAction!();
              onDismissed?.call();
            },
          )
        : null;

    return ConstrainedBox(
      constraints: BoxConstraints(maxWidth: paint.maxWidth),
      child: GlassSurface(
        level: GlassLevel.floating,
        capsule: true,
        child: ConstrainedBox(
          constraints: BoxConstraints(minHeight: paint.minHeight),
          child: Padding(
            padding: paint.padding,
            child: _fitted(ui, paint, glyph, words, action),
          ),
        ),
      ),
    );
  }

  /// The capsule's two arrangements (11 section 3.3).
  ///
  /// The action moves under the message rather than the message shrinking:
  /// the message is content and the action is a control with a hit box, and
  /// squeezing either of them is what the row of the table forbids. A toast
  /// with no action has one arrangement and its message simply wraps.
  Widget _fitted(
    UiThemeData ui,
    UiToastStyle paint,
    Widget glyph,
    Widget words,
    UiButton? action,
  ) => Builder(
    builder: (BuildContext context) {
      Widget line({required bool withAction}) => Row(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          glyph,
          SizedBox(width: paint.gap),
          Flexible(child: words),
          if (withAction && action != null) ...<Widget>[
            SizedBox(width: paint.gap),
            action,
          ],
        ],
      );
      if (action == null) {
        return FitBuilder(
          variants: <FitVariant>[
            FitVariant(
              intrinsicWidth: 0,
              builder: (BuildContext context, bool _) =>
                  line(withAction: false),
            ),
          ],
        );
      }
      final double chrome =
          paint.padding.resolve(Directionality.of(context)).horizontal +
          UiIconSize.inline.dimension +
          paint.gap +
          paint.messageMin;
      return FitBuilder(
        variants: <FitVariant>[
          FitVariant(
            intrinsicWidth:
                chrome +
                paint.gap +
                measureLabel(context, action.label, ui.type.label).width +
                ui.space.s8,
            builder: (BuildContext context, bool _) => line(withAction: true),
          ),
          FitVariant(
            intrinsicWidth: 0,
            builder: (BuildContext context, bool _) => Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                line(withAction: false),
                SizedBox(height: paint.gap),
                // Aligned to the end, where the eye finishes the message.
                Align(
                  alignment: AlignmentDirectional.centerEnd,
                  child: action,
                ),
              ],
            ),
          ),
        ],
      );
    },
  );
}

/// The layer every toast in a window appears on.
///
/// One of these sits inside the page frame, above the content and below the
/// navigation. It owns the queue, so a burst of messages is read one at a
/// time rather than stacking up over the record.
class UiToastHost extends StatefulWidget {
  /// Hosts toasts over [child].
  const UiToastHost({
    super.key,
    required this.child,
    this.bottomInset = 0,
  });

  /// The page beneath the toasts.
  final Widget child;

  /// Extra room to leave at the bottom of the window.
  ///
  /// The shell passes the height of the pill navigation plus its gap, so a
  /// toast on a compact window sits above the navigation rather than over it
  /// (10 section 4.4).
  final double bottomInset;

  /// The host above [context], or null where none was installed.
  static UiToastHostState? maybeOf(BuildContext context) =>
      context.findAncestorStateOfType<UiToastHostState>();

  @override
  State<UiToastHost> createState() => UiToastHostState();
}

/// The queue behind a [UiToastHost].
///
/// Public so [UiToasts] can reach it. A caller raises a toast through
/// [UiToasts.show] rather than holding one of these.
class UiToastHostState extends State<UiToastHost> {
  final Queue<UiToastData> _waiting = Queue<UiToastData>();
  UiToastData? _current;
  int _generation = 0;
  Timer? _timer;

  /// The toast on screen, or null when the queue is empty.
  UiToastData? get current => _current;

  /// How many messages are waiting behind [current].
  int get waiting => _waiting.length;

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  /// Queues [data], showing it as soon as the layer is free.
  void show(UiToastData data) {
    if (_current == null) {
      _present(data);
    } else {
      _waiting.add(data);
    }
  }

  /// Dismisses the toast on screen and shows the next one.
  void dismiss() {
    _timer?.cancel();
    _timer = null;
    if (_waiting.isEmpty) {
      if (_current == null) return;
      setState(() => _current = null);
      return;
    }
    _present(_waiting.removeFirst());
  }

  void _present(UiToastData data) {
    _timer?.cancel();
    setState(() {
      _current = data;
      _generation++;
    });
    // A toast with an action waits for the reviewer. Taking the action away
    // after six seconds would be taking it away as they reach for it.
    if (!data.hasAction) {
      _timer = Timer(UiToastStyle.showDuration, dismiss);
    }
  }

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final UiToastStyle style = UiToastStyle.resolve(ui);
    final UiToastData? data = _current;
    return Stack(
      // Passthrough rather than the default loose fit: the host is a layer
      // over a page, so the page has to be laid out against the constraints
      // the host was given. A loose stack hands a tight caller's child loose
      // constraints and aligns it top start, which shrinks a page that
      // shrink wraps.
      fit: StackFit.passthrough,
      children: <Widget>[
        widget.child,
        if (data != null)
          // Nothing in the layer hit tests except the capsule itself, so the
          // page beneath keeps every tap that is not on a toast.
          Positioned.fill(
            child: SafeArea(
              child: Padding(
                padding: style.margin.add(
                  EdgeInsetsDirectional.only(bottom: widget.bottomInset),
                ),
                child: Align(
                  // Compact windows centre the capsule above the pill
                  // navigation; wider ones anchor it to the bottom start
                  // corner, away from the action bar (10 section 4.3).
                  alignment: isCompactWindow(context)
                      ? AlignmentDirectional.bottomCenter
                      : AlignmentDirectional.bottomStart,
                  child: _ToastEntrance(
                    key: ValueKey<int>(_generation),
                    child: UiToast(
                      data: data,
                      onDismissed: dismiss,
                      style: style,
                    ),
                  ),
                ),
              ),
            ),
          ),
      ],
    );
  }
}

/// Raising a toast.
///
/// The entry point a screen calls. It replaces
/// `ScaffoldMessenger.of(context).showSnackBar`.
abstract final class UiToasts {
  /// Queues a toast on the nearest [UiToastHost].
  ///
  /// Silently does nothing where no host is installed, which is what a test
  /// or a preview that pumps a control on its own wants: a missing toast layer
  /// is not a reason to fail a review.
  static void show(
    BuildContext context, {
    required String message,
    IconSpec? icon,
    String? actionLabel,
    VoidCallback? onAction,
  }) => UiToastHost.maybeOf(context)?.show(
    UiToastData(
      message: message,
      icon: icon,
      actionLabel: actionLabel,
      onAction: onAction,
    ),
  );

  /// Dismisses the toast on screen and shows the next one.
  static void dismiss(BuildContext context) =>
      UiToastHost.maybeOf(context)?.dismiss();
}

/// The arrival: a rise and a fade, collapsed to nothing under reduced motion.
class _ToastEntrance extends StatelessWidget {
  const _ToastEntrance({super.key, required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    return TweenAnimationBuilder<double>(
      tween: Tween<double>(begin: 0, end: 1),
      duration: ui.motion.standard,
      curve: MotionTokens.enterCurve,
      builder: (BuildContext context, double t, Widget? capsule) => Opacity(
        opacity: t,
        child: Transform.translate(
          offset: Offset(0, (1 - t) * UiToastStyle.entranceRise),
          child: capsule,
        ),
      ),
      child: child,
    );
  }
}
