/// The gallery shell (10 section 6).
///
/// One page per family plus the foundation pages, every token and every state
/// on screen at once. It is how the direction is reviewed by eye, and its
/// goldens are the taste review: a change to a token shows as a diff on a page
/// here before it shows on a screen.
///
/// Built from `widgets.dart` and this package only. A Material component
/// inside the gallery would be a Material component the gates do not see.
library;

import 'package:flutter/widgets.dart';

import '../../specimen_ui.dart';
import 'pages/actions_page.dart';
import 'pages/colour_page.dart';
import 'pages/data_page.dart';
import 'pages/fields_page.dart';
import 'pages/fit_page.dart';
import 'pages/icons_page.dart';
import 'pages/overlays_page.dart';
import 'pages/inputs_page.dart';
import 'pages/navigation_page.dart';
import 'pages/primitives_page.dart';
import 'pages/shape_page.dart';
import 'pages/type_page.dart';

/// One page of the gallery.
@immutable
class GalleryPage {
  /// Names [builder] so the page list and the golden agree on one identifier.
  const GalleryPage({
    required this.id,
    required this.title,
    required this.summary,
    required this.builder,
    this.maxGlassPanes = UiGlass.maxPanesPerWindow,
  });

  /// The identifier the golden file is named with.
  final String id;

  /// The heading, generated from the class names the page renders.
  final String title;

  /// One line saying what the page is evidence of.
  final String summary;

  /// Renders the page body.
  final WidgetBuilder builder;

  /// How many frosted panes this page may draw.
  ///
  /// The budget in 09 section 3.3 is four per window, and every page is held
  /// to it. A specimen sheet whose whole purpose is to show every level over
  /// every preset at once is the one exception, and it states its own number
  /// rather than the golden quietly skipping the check.
  final int maxGlassPanes;
}

/// Every foundation page, in the order 10 section 6 lists them.
const List<GalleryPage> foundationPages = <GalleryPage>[
  GalleryPage(
    id: 'type',
    title: 'Type',
    summary: 'Every role at its own size and weight, and the mono specimen.',
    builder: buildTypePage,
  ),
  GalleryPage(
    id: 'colour',
    title: 'Colour',
    summary: 'Every role on ground, paper, matte and each glass level.',
    builder: buildColourPage,
  ),
  GalleryPage(
    id: 'fields',
    title: 'Fields and glass',
    summary: 'The three sky presets, each under the three glass levels.',
    builder: buildFieldsPage,
    // Three presets times three levels, plus the page list. A product window
    // would never do this; a specimen sheet exists to.
    maxGlassPanes: 10,
  ),
  GalleryPage(
    id: 'shape',
    title: 'Shape',
    summary: 'Every radius and every stroke width.',
    builder: buildShapePage,
  ),
  GalleryPage(
    id: 'icons',
    title: 'Icons',
    summary: 'Every registry key, in regular and in fill.',
    builder: buildIconsPage,
  ),
  GalleryPage(
    id: 'primitives',
    title: 'Primitives',
    summary: 'Pressable in every state, the glass levels and the overlays.',
    builder: buildPrimitivesPage,
  ),
];

/// Every family page, in the order 10 section 4 lists the families: actions,
/// inputs, overlays, navigation, data.
///
/// One line per family, added by the slot that owns that page. Separate from
/// [foundationPages] because the foundation goldens render the whole shell,
/// page list included: sharing one list would move all twenty four of them
/// every time a family landed, and five slots regenerating the same binaries
/// in parallel is how two branches silently revert one another.
const List<GalleryPage> familyPages = <GalleryPage>[
  actionsPage,
  inputsPage,
  overlaysPage,
  navigationPage,
  dataPage,
];

/// Every page the gallery shows.
///
/// The Fit page is neither foundation nor family: it is the evidence for 11
/// section 3.3, one control to a section at four column widths, and it belongs
/// to no family because it draws every family's controls. So it is listed here
/// rather than pushed into [familyPages], where it would sit under a heading
/// that is not true of it.
const List<GalleryPage> galleryPages = <GalleryPage>[
  ...foundationPages,
  ...familyPages,
  fitPage,
];

/// Which arrangement the shell draws, by window class (11 section 3.5).
///
/// Below `medium` the page list is a [UiSelect] above the content and the
/// content takes the full width; from `medium` up the sidebar stays. Declared
/// as an [Adaptive] rather than as a comparison on the width because that is
/// what the foundation gives a scaffold for declaring an arrangement with, and
/// this shell is its first consumer.
const Adaptive<bool> _sidebarArrangement = Adaptive<bool>(
  compact: false,
  medium: true,
);

/// The gallery: a page list beside the page, or above it when the window is
/// too narrow to hold both.
class UiGallery extends StatefulWidget {
  /// Opens the gallery at [initialPage].
  const UiGallery({super.key, this.initialPage = 0, this.pages});

  /// Which page to open on.
  final int initialPage;

  /// The pages to show. Defaults to [galleryPages]; a golden passes its own
  /// list so that its page list holds still as other slots land.
  final List<GalleryPage>? pages;

  @override
  State<UiGallery> createState() => _UiGalleryState();
}

class _UiGalleryState extends State<UiGallery> {
  late int _selected = widget.initialPage;

  List<GalleryPage> get _pages => widget.pages ?? galleryPages;

  void _select(int index) => setState(() => _selected = index);

  @override
  Widget build(BuildContext context) {
    final int selected = _selected.clamp(0, _pages.length - 1);
    final GalleryPage page = _pages[selected];
    // Never null: `compact` is set, and every class resolves down to it.
    final bool sidebar = _sidebarArrangement.of(context)!;
    // No `DefaultTextStyle` here. `UiTheme` publishes the product's ambient
    // style (11 section 5), so the shell publishing its own would be a second
    // source for the one thing that document gives one source.
    return FieldLayer(
      preset: SkyPreset.home,
      child: sidebar
          ? Row(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: <Widget>[
                _PageList(pages: _pages, selected: selected, onSelect: _select),
                Expanded(child: _PageView(page: page)),
              ],
            )
          : Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: <Widget>[
                _PageSelect(
                  pages: _pages,
                  selected: selected,
                  onSelect: _select,
                ),
                Expanded(child: _PageView(page: page, compact: true)),
              ],
            ),
    );
  }
}

/// The page list below `medium`: one select above the content.
///
/// A 220 dp sidebar beside a 360 dp window leaves 130 dp for the page, which
/// is where the wrapping labels of 11 section 0 were first seen. The select
/// carries the same page titles in the same order and answers the same keys,
/// so nothing about reviewing the gallery changes with the arrangement.
class _PageSelect extends StatelessWidget {
  const _PageSelect({
    required this.pages,
    required this.selected,
    required this.onSelect,
  });

  final List<GalleryPage> pages;
  final int selected;
  final ValueChanged<int> onSelect;

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    return Padding(
      padding: EdgeInsetsDirectional.fromSTEB(
        ui.space.s4,
        ui.space.s4,
        ui.space.s4,
        ui.space.s3,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          Text('specimen_ui', style: ui.type.titleLarge),
          SizedBox(height: ui.space.s2),
          UiSelect<int>(
            label: 'Gallery page',
            // The heading above it already names the gallery, and the select
            // holds the only list of pages on screen.
            showLabel: false,
            options: <UiSelectOption<int>>[
              for (int i = 0; i < pages.length; i++)
                UiSelectOption<int>(value: i, label: pages[i].title),
            ],
            value: selected,
            placeholder: 'Choose a page',
            onChanged: onSelect,
          ),
        ],
      ),
    );
  }
}

class _PageList extends StatelessWidget {
  const _PageList({
    required this.pages,
    required this.selected,
    required this.onSelect,
  });

  final List<GalleryPage> pages;
  final int selected;
  final ValueChanged<int> onSelect;

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    return SizedBox(
      width: 220,
      child: Padding(
        padding: EdgeInsetsDirectional.all(ui.space.s4),
        child: GlassSurface(
          level: GlassLevel.flat,
          radius: ui.shape.tile,
          padding: EdgeInsetsDirectional.all(ui.space.s2),
          // The pane is stretched to the window by the shell's row, so the
          // list inside it can scroll when the window is shorter than the
          // page count needs. Ten pages overflow a 600 px window otherwise.
          child: SingleChildScrollView(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              mainAxisSize: MainAxisSize.min,
              children: <Widget>[
                Padding(
                  padding: EdgeInsetsDirectional.fromSTEB(
                    ui.space.s3,
                    ui.space.s3,
                    ui.space.s3,
                    ui.space.s2,
                  ),
                  child: Text('specimen_ui', style: ui.type.titleLarge),
                ),
                for (int i = 0; i < pages.length; i++)
                  _PageListRow(
                    page: pages[i],
                    selected: i == selected,
                    onSelect: () => onSelect(i),
                  ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _PageListRow extends StatelessWidget {
  const _PageListRow({
    required this.page,
    required this.selected,
    required this.onSelect,
  });

  final GalleryPage page;
  final bool selected;
  final VoidCallback onSelect;

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    return Pressable(
      semanticsLabel: page.title,
      onPressed: onSelect,
      selected: selected,
      radius: ui.shape.inner,
      minHitBox: 0,
      builder: (BuildContext context, Set<WidgetState> states) => SizedBox(
        height: ui.density.rowHeight,
        child: Align(
          alignment: AlignmentDirectional.centerStart,
          child: Padding(
            padding: EdgeInsetsDirectional.symmetric(horizontal: ui.space.s3),
            child: Text(
              page.title,
              style: ui.type.label.copyWith(
                color: selected ? ui.color.ink : ui.color.inkSecondary,
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _PageView extends StatelessWidget {
  const _PageView({required this.page, this.compact = false});

  final GalleryPage page;

  /// True when the page list is above the content rather than beside it.
  ///
  /// Only the start edge changes: beside a sidebar the list has already paid
  /// for that gutter, and under a select nothing has.
  final bool compact;

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    return Padding(
      padding: EdgeInsetsDirectional.fromSTEB(
        compact ? ui.space.s4 : 0,
        compact ? 0 : ui.space.s4,
        ui.space.s4,
        ui.space.s4,
      ),
      child: Surface(
        radius: ui.shape.sheet,
        hairline: true,
        clip: true,
        child: SingleChildScrollView(
          padding: EdgeInsetsDirectional.all(ui.space.s6),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Text(page.title, style: ui.type.headline),
              SizedBox(height: ui.space.s1),
              Text(
                page.summary,
                style: ui.type.bodySmall.copyWith(color: ui.color.inkSecondary),
              ),
              SizedBox(height: ui.space.s6),
              page.builder(context),
            ],
          ),
        ),
      ),
    );
  }
}

/// Columns of specimens that sit side by side where the page is wide enough
/// and stack where it is not. This is the gallery's own arrangement: a phone
/// wide window shows every specimen at its intrinsic width instead of
/// squeezing two columns into it (11 section 3.5), so what the matrix pictures
/// at 360 dp is the control's fit policy and not the page's.
class GalleryColumns extends StatelessWidget {
  /// Lays [children] out as columns with [gap] between them.
  const GalleryColumns({
    super.key,
    required this.children,
    required this.gap,
    this.flexes,
    this.minColumnWidth = 320,
  });

  /// One widget per column, each usually a `Column` of specimens.
  final List<Widget> children;

  /// The share of the width each column takes side by side; equal when null.
  final List<int>? flexes;

  /// The space between columns, and between stacked children.
  final double gap;

  /// The narrowest a column may be before the columns stack.
  final double minColumnWidth;

  @override
  Widget build(BuildContext context) => LayoutBuilder(
    builder: (BuildContext context, BoxConstraints constraints) {
      final double needed =
          children.length * minColumnWidth + gap * (children.length - 1);
      if (constraints.maxWidth < needed) {
        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            for (int i = 0; i < children.length; i++) ...<Widget>[
              if (i > 0) SizedBox(height: gap),
              children[i],
            ],
          ],
        );
      }
      return Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          for (int i = 0; i < children.length; i++) ...<Widget>[
            if (i > 0) SizedBox(width: gap),
            Expanded(flex: flexes?[i] ?? 1, child: children[i]),
          ],
        ],
      );
    },
  );
}

/// A titled block on a gallery page.
class GallerySection extends StatelessWidget {
  /// Titles [child] with [title].
  const GallerySection({super.key, required this.title, required this.child});

  /// What the block is evidence of.
  final String title;

  /// The specimens themselves.
  final Widget child;

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    return Padding(
      padding: EdgeInsetsDirectional.only(bottom: ui.space.s8),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Text(
            title,
            style: ui.type.label.copyWith(color: ui.color.inkSecondary),
          ),
          SizedBox(height: ui.space.s3),
          child,
        ],
      ),
    );
  }
}

/// One labelled specimen inside a section.
class GallerySpecimen extends StatelessWidget {
  /// Labels [child] with [label], and with [note] beneath it where there is
  /// something a reader cannot see.
  const GallerySpecimen({
    super.key,
    required this.label,
    required this.child,
    this.note,
  });

  /// The token's name, as 09 writes it.
  final String label;

  /// What the token draws.
  final Widget child;

  /// A measurement or a rule the drawing does not show.
  final String? note;

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        child,
        SizedBox(height: ui.space.s1),
        Text(
          label,
          style: ui.type.mono.identifier.copyWith(color: ui.color.inkSecondary),
        ),
        if (note != null)
          Text(
            note!,
            style: ui.type.bodySmall.copyWith(color: ui.color.inkTertiary),
          ),
      ],
    );
  }
}
