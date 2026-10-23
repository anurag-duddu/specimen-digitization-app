/// Inspectable source text with an explicit clipboard action.
library;

import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import '../../foundation/theme.dart';
import '../../primitives/field_core.dart';
import '../../primitives/surface.dart';
import '../actions/button.dart';

/// Optional code-surface appearance independent of the surrounding page.
enum UiCodeTheme {
  /// The surrounding page appearance.
  inherit,

  /// An explicit light surface.
  light,

  /// An explicit dark surface.
  dark,
}

/// Neutral or subtle Iris frame treatment.
enum UiCodeTone {
  /// Neutral surface styling.
  neutral,

  /// Accessible Iris emphasis.
  brand,
}

/// A plain code sample. It never evaluates its contents.
class UiCodeSnippet extends StatefulWidget {
  /// Shows [code] under [label].
  const UiCodeSnippet({
    super.key,
    required this.code,
    required this.label,
    this.onCopy,
    this.theme = UiCodeTheme.inherit,
    this.tone = UiCodeTone.neutral,
    this.lineNumbers = false,
  });

  /// Literal content to display and copy.
  final String code;

  /// Accessible description, such as "Occurrence JSON".
  final String label;

  /// Optional clipboard adapter. By default uses the system clipboard.
  final Future<void> Function(String code)? onCopy;

  /// The panel's explicit theme, preserving host density and motion.
  final UiCodeTheme theme;

  /// The frame emphasis, independent of source-text meaning.
  final UiCodeTone tone;

  /// Whether a decorative line-number gutter accompanies each source line.
  final bool lineNumbers;

  @override
  State<UiCodeSnippet> createState() => _UiCodeSnippetState();
}

class _UiCodeSnippetState extends State<UiCodeSnippet> {
  bool _busy = false;
  String _status = '';
  int _revision = 0;

  @override
  void didUpdateWidget(UiCodeSnippet oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.code != widget.code) {
      _revision++;
      _status = '';
      _busy = false;
    }
  }

  Future<void> _copy() async {
    if (_busy) return;
    final revision = _revision;
    setState(() {
      _busy = true;
      _status = '';
    });
    try {
      await (widget.onCopy?.call(widget.code) ??
          Clipboard.setData(ClipboardData(text: widget.code)));
      if (mounted && revision == _revision) setState(() => _status = 'Copied');
    } catch (_) {
      if (mounted && revision == _revision) {
        setState(() => _status = 'Could not copy. Try again.');
      }
    } finally {
      if (mounted && revision == _revision) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final inherited = context.ui;
    if (widget.theme != UiCodeTheme.inherit) {
      final data =
          (widget.theme == UiCodeTheme.dark
                  ? UiThemeData.dark()
                  : UiThemeData.light())
              .copyWith(density: inherited.density, motion: inherited.motion);
      return UiTheme(
        data: data,
        child: Builder(builder: _build),
      );
    }
    return _build(context);
  }

  Widget _build(BuildContext context) {
    final ui = context.ui;
    return DecoratedBox(
      decoration: BoxDecoration(
        border: widget.tone == UiCodeTone.brand
            ? BorderDirectional(
                start: BorderSide(
                  color: ui.brand.secondary.content,
                  width: ui.shape.stroke.emphasis,
                ),
              )
            : null,
      ),
      child: Surface(
        radius: ui.shape.tile,
        hairline: true,
        padding: EdgeInsets.all(ui.space.s4),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Wrap(
              spacing: ui.space.s4,
              runSpacing: ui.space.s2,
              crossAxisAlignment: WrapCrossAlignment.center,
              children: [
                Text(
                  widget.label,
                  style: ui.type.label.copyWith(color: ui.color.ink),
                ),
                UiButton(
                  label: 'Copy code',
                  busyLabel: 'Copying code',
                  loading: _busy,
                  semanticsLabel: 'Copy ${widget.label}',
                  variant: UiButtonVariant.secondary,
                  size: UiSize.sm,
                  onPressed: _copy,
                ),
              ],
            ),
            SizedBox(height: ui.space.s3),
            ConstrainedBox(
              constraints: BoxConstraints(maxHeight: ui.space.paneDetailMin),
              child: SingleChildScrollView(
                child: widget.lineNumbers
                    ? Column(
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: [
                          for (final (i, line)
                              in widget.code.split('\n').indexed)
                            Row(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                ExcludeSemantics(
                                  child: Padding(
                                    padding: EdgeInsetsDirectional.only(
                                      end: ui.space.s3,
                                    ),
                                    child: Text(
                                      '${i + 1}',
                                      style: ui.type.mono.code.copyWith(
                                        color: ui.color.inkSecondary,
                                      ),
                                    ),
                                  ),
                                ),
                                Expanded(
                                  child: UiSelectableText(
                                    line,
                                    style: ui.type.mono.code.copyWith(
                                      color: ui.color.ink,
                                    ),
                                  ),
                                ),
                              ],
                            ),
                        ],
                      )
                    : UiSelectableText(
                        widget.code,
                        semanticsLabel: '${widget.label}: ${widget.code}',
                        style: ui.type.mono.code.copyWith(color: ui.color.ink),
                      ),
              ),
            ),
            if (_status.isNotEmpty) ...[
              SizedBox(height: ui.space.s2),
              Semantics(
                liveRegion: true,
                child: Text(
                  _status,
                  style: ui.type.bodySmall.copyWith(
                    color: ui.color.inkSecondary,
                  ),
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}
