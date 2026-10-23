/// Controlled pagination, including empty and pending result sets.
library;

import 'package:flutter/widgets.dart';
import 'package:flutter/services.dart';

import '../../foundation/icons.dart';
import '../../foundation/theme.dart';
import '../../primitives/fit.dart';
import '../../primitives/pressable.dart';
import '../actions/button.dart';
import '../actions/icon_button.dart';

/// Pagination command placement and visible page-number treatment.
enum UiPaginationVariant {
  /// Page numbers between previous and next commands.
  numbered,

  /// Page status between previous and next text commands.
  minimal,

  /// Compact directional commands surrounding page status.
  buttonGroup,
}

/// The available presentation choices for this component.
enum UiPaginationShape {
  /// Rounded square page-number buttons.
  square,

  /// Circular page-number buttons.
  circle,
}

/// Token-derived pagination measures.
@immutable
class UiPaginationStyle {
  /// Resolves layout and text from the shared theme.
  UiPaginationStyle.resolve(UiThemeData ui)
    : gap = ui.space.s2,
      target = ui.space.targetMin,
      radius = ui.shape.inner,
      label = ui.type.label.copyWith(color: ui.color.inkSecondary);

  /// Spacing between controls.
  final double gap;

  /// Minimum interactive extent.
  final double target;

  /// Page-number corner radius.
  final double radius;

  /// Summary text.
  final TextStyle label;
}

/// A caller-controlled, one-based page chooser.
///
/// Empty results use [pageCount] and [page] both zero. A page change requests
/// new data; it does not update the current page until the host supplies it.
/// [busy] blocks all requests while an existing request is pending.
class UiPagination extends StatelessWidget {
  /// Builds pagination for a known page count.
  const UiPagination({
    super.key,
    required this.page,
    required this.pageCount,
    this.onChanged,
    this.busy = false,
    this.semanticsLabel = 'Pagination',
    this.variant = UiPaginationVariant.numbered,
    this.shape = UiPaginationShape.square,
    this.alignment = WrapAlignment.spaceBetween,
  }) : assert(pageCount >= 0),
       assert(pageCount == 0 ? page == 0 : page >= 1 && page <= pageCount);

  /// Current page, one-based, or zero when there are no pages.
  final int page;

  /// Total pages. The host owns page-size and total-count calculation.
  final int pageCount;

  /// Requests a valid different page. Null disables all navigation.
  final ValueChanged<int>? onChanged;

  /// True while the host is fetching a requested page.
  final bool busy;

  /// Names this pagination region when several occur on one page.
  final String semanticsLabel;

  /// The visible pagination command arrangement.
  final UiPaginationVariant variant;

  /// The page-number shape treatment.
  final UiPaginationShape shape;

  /// The wrap alignment of minimal or grouped commands.
  final WrapAlignment alignment;

  bool get _enabled => !busy && onChanged != null;

  void _request(int next) {
    if (_enabled && next >= 1 && next <= pageCount && next != page) {
      onChanged!(next);
    }
  }

  List<int?> get _pages {
    if (pageCount <= 7) return <int>[for (int p = 1; p <= pageCount; p++) p];
    final Set<int> visible = <int>{1, pageCount};
    final int start = page <= 4
        ? 2
        : page >= pageCount - 3
        ? pageCount - 4
        : page - 1;
    final int end = page <= 4
        ? 5
        : page >= pageCount - 3
        ? pageCount - 1
        : page + 1;
    for (int p = start; p <= end; p++) {
      visible.add(p);
    }
    final List<int> ordered = visible.toList()..sort();
    return <int?>[
      for (int i = 0; i < ordered.length; i++) ...<int?>[
        if (i > 0 && ordered[i] - ordered[i - 1] > 1) null,
        ordered[i],
      ],
    ];
  }

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final UiPaginationStyle style = UiPaginationStyle.resolve(ui);
    final bool rtl = Directionality.of(context) == TextDirection.rtl;
    final String summary = pageCount == 0
        ? 'No pages'
        : 'Page $page of $pageCount';
    final Widget status = Semantics(
      liveRegion: true,
      child: Text(busy ? '$summary · Loading' : summary, style: style.label),
    );
    Widget previous({required bool compact}) => compact
        ? UiIconButton(
            icon: rtl ? UiIcons.next : UiIcons.previous,
            semanticsLabel: 'Previous page',
            onPressed: _enabled && page > 1 ? () => _request(page - 1) : null,
          )
        : UiButton(
            label: 'Previous',
            semanticsLabel: 'Previous page',
            leading: rtl ? UiIcons.next : UiIcons.previous,
            variant: UiButtonVariant.secondary,
            onPressed: _enabled && page > 1 ? () => _request(page - 1) : null,
          );
    Widget next({required bool compact}) => compact
        ? UiIconButton(
            icon: rtl ? UiIcons.previous : UiIcons.next,
            semanticsLabel: 'Next page',
            onPressed: _enabled && page < pageCount
                ? () => _request(page + 1)
                : null,
          )
        : UiButton(
            label: 'Next',
            semanticsLabel: 'Next page',
            trailing: rtl ? UiIcons.previous : UiIcons.next,
            variant: UiButtonVariant.secondary,
            onPressed: _enabled && page < pageCount
                ? () => _request(page + 1)
                : null,
          );
    if (variant != UiPaginationVariant.numbered) {
      return Semantics(
        container: true,
        label: semanticsLabel,
        child: Wrap(
          alignment: alignment,
          spacing: style.gap,
          runSpacing: style.gap,
          crossAxisAlignment: WrapCrossAlignment.center,
          children: [
            previous(compact: variant == UiPaginationVariant.buttonGroup),
            status,
            next(compact: variant == UiPaginationVariant.buttonGroup),
          ],
        ),
      );
    }
    return Semantics(
      container: true,
      label: semanticsLabel,
      child: LayoutBuilder(
        builder: (BuildContext context, BoxConstraints constraints) {
          final List<int?> pages = _pages;
          final double numberWidth = pages.fold<double>(0, (
            double width,
            int? p,
          ) {
            final double measured =
                measureLabel(context, '${p ?? '…'}', style.label).width +
                style.gap * 2;
            return width +
                (measured > style.target ? measured : style.target) +
                style.gap;
          });
          final UiButtonStyle button = UiButtonStyle.resolve(
            ui,
            UiButtonVariant.secondary,
            UiSize.md,
          );
          final double commandWidth = <String>['Previous', 'Next'].fold<double>(
            0,
            (double width, String text) =>
                width +
                measureLabel(context, text, button.label).width +
                button.padding.resolve(Directionality.of(context)).horizontal +
                ui.space.iconInline +
                button.gap,
          );
          final bool expanded =
              constraints.hasBoundedWidth &&
              constraints.maxWidth >=
                  numberWidth + commandWidth + style.gap * 2;
          if (!expanded) {
            return Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: <Widget>[
                previous(compact: true),
                SizedBox(width: style.gap),
                Flexible(child: status),
                SizedBox(width: style.gap),
                next(compact: true),
              ],
            );
          }
          return Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: <Widget>[
                  previous(compact: false),
                  Row(
                    mainAxisSize: MainAxisSize.min,
                    children: <Widget>[
                      for (final int? p in pages)
                        if (p == null)
                          SizedBox(
                            width: style.target,
                            child: Center(child: Text('…', style: style.label)),
                          )
                        else
                          Pressable(
                            semanticsLabel: 'Page $p',
                            semanticsValue: p == page ? 'Current page' : null,
                            selected: p == page,
                            onPressed: _enabled && p != page
                                ? () => _request(p)
                                : null,
                            builder:
                                (
                                  BuildContext context,
                                  Set<WidgetState> states,
                                ) => DecoratedBox(
                                  decoration: BoxDecoration(
                                    color: p == page
                                        ? ui.color.disabledFill
                                        : ui.color.paper,
                                    borderRadius: BorderRadius.circular(
                                      shape == UiPaginationShape.circle
                                          ? style.target
                                          : style.radius,
                                    ),
                                  ),
                                  child: ConstrainedBox(
                                    constraints: BoxConstraints(
                                      minWidth: style.target,
                                      minHeight: style.target,
                                    ),
                                    child: Padding(
                                      padding: EdgeInsets.all(style.gap),
                                      child: Center(
                                        child: Text(
                                          '$p',
                                          style: style.label.copyWith(
                                            color: p == page
                                                ? ui.color.ink
                                                : ui.color.inkSecondary,
                                          ),
                                        ),
                                      ),
                                    ),
                                  ),
                                ),
                          ),
                    ],
                  ),
                  next(compact: false),
                ],
              ),
              SizedBox(height: style.gap),
              status,
            ],
          );
        },
      ),
    );
  }
}

/// Shape used by a controlled carousel/page indicator.
enum UiPageIndicatorStyle {
  /// Circular indicator marks.
  dots,

  /// Horizontal indicator marks.
  lines,
}

/// Touch-sized dots/lines with a spoken position and controlled selection.
class UiPageIndicator extends StatelessWidget {
  /// Creates the component with explicit content and caller-owned state.
  const UiPageIndicator({
    super.key,
    required this.index,
    required this.count,
    this.onChanged,
    this.style = UiPageIndicatorStyle.dots,
    this.framed = false,
  }) : assert(count >= 0),
       assert(count == 0 ? index == 0 : index >= 0 && index < count);

  /// The current zero-based page position.
  final int index;

  /// Number of pages. Zero names an empty result.
  final int count;

  /// The callback requesting a new controlled value; null disables requests.
  final ValueChanged<int>? onChanged;

  /// The visual treatment, independent of the content or controlled state.
  final UiPageIndicatorStyle style;

  /// Whether the indicator group sits on a neutral rounded surface.
  final bool framed;
  @override
  Widget build(BuildContext context) {
    final ui = context.ui;
    return DecoratedBox(
      decoration: BoxDecoration(
        color: framed ? ui.color.ground : null,
        borderRadius: BorderRadius.circular(ui.space.targetMin),
      ),
      child: Wrap(
        alignment: WrapAlignment.center,
        children: [
          for (var i = 0; i < count; i++)
            Pressable(
              semanticsLabel: 'Page ${i + 1} of $count',
              selected: index == i,
              onPressed: onChanged != null && i != index
                  ? () => onChanged!(i)
                  : null,
              builder: (_, _) => SizedBox(
                width: ui.space.targetMin,
                height: ui.space.targetMin,
                child: Center(
                  child: Container(
                    width: style == UiPageIndicatorStyle.lines
                        ? ui.space.s6
                        : ui.space.s2,
                    height: ui.space.s2,
                    decoration: BoxDecoration(
                      color: index == i
                          ? ui.brand.secondary.content
                          : ui.color.boundary,
                      borderRadius: BorderRadius.circular(ui.space.targetMin),
                    ),
                  ),
                ),
              ),
            ),
        ],
      ),
    );
  }
}

/// Controlled non-autoplay carousel supporting touch and directional keyboard.
/// All content is supplied by the host; media must supply its own description.
class UiCarousel extends StatelessWidget {
  /// Creates the component with explicit content and caller-owned state.
  const UiCarousel({
    super.key,
    required this.children,
    required this.index,
    this.onChanged,
    this.aspectRatio = 4 / 3,
    this.label = 'Gallery',
    this.indicatorStyle = UiPageIndicatorStyle.dots,
  }) : assert(aspectRatio > 0),
       assert(index >= 0);

  /// The ordered host content for the carousel.
  final List<Widget> children;

  /// The current zero-based position.
  final int index;

  /// The callback requesting a new controlled value; null disables requests.
  final ValueChanged<int>? onChanged;

  /// The preferred media width divided by height, constrained by available space.
  final double aspectRatio;

  /// The visible accessible name supplied by the host.
  final String label;

  /// The indicator mark style.
  final UiPageIndicatorStyle indicatorStyle;
  void _request(int value) {
    if (onChanged != null &&
        value >= 0 &&
        value < children.length &&
        value != index) {
      onChanged!(value);
    }
  }

  @override
  Widget build(BuildContext context) {
    final rtl = Directionality.of(context) == TextDirection.rtl;
    assert(children.isEmpty ? index == 0 : index < children.length);
    if (children.isEmpty) {
      return Text(
        'No items',
        style: context.ui.type.body.copyWith(
          color: context.ui.color.inkSecondary,
        ),
      );
    }
    return CallbackShortcuts(
      bindings: {
        const SingleActivator(LogicalKeyboardKey.arrowRight): () =>
            _request(index + (rtl ? -1 : 1)),
        const SingleActivator(LogicalKeyboardKey.arrowLeft): () =>
            _request(index + (rtl ? 1 : -1)),
        const SingleActivator(LogicalKeyboardKey.home): () => _request(0),
        const SingleActivator(LogicalKeyboardKey.end): () =>
            _request(children.length - 1),
      },
      child: Focus(
        child: Semantics(
          container: true,
          label: label,
          child: LayoutBuilder(
            builder: (context, constraints) {
              final media = GestureDetector(
                onHorizontalDragEnd: (details) {
                  final velocity = details.primaryVelocity ?? 0;
                  if (velocity != 0) {
                    _request(index + ((velocity < 0) != rtl ? 1 : -1));
                  }
                },
                child: AspectRatio(
                  aspectRatio: aspectRatio,
                  child: ClipRect(child: children[index]),
                ),
              );
              return Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  if (constraints.hasBoundedHeight)
                    Flexible(child: media)
                  else
                    media,
                  UiPagination(
                    page: index + 1,
                    pageCount: children.length,
                    variant: UiPaginationVariant.buttonGroup,
                    onChanged: onChanged == null
                        ? null
                        : (p) => _request(p - 1),
                    semanticsLabel: '$label pages',
                  ),
                  UiPageIndicator(
                    index: index,
                    count: children.length,
                    onChanged: onChanged,
                    style: indicatorStyle,
                  ),
                ],
              );
            },
          ),
        ),
      ),
    );
  }
}
