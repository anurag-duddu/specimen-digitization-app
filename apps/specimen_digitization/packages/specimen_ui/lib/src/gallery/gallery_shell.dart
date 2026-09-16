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
import 'pages/fields_page.dart';
import 'pages/icons_page.dart';
import 'pages/overlays_page.dart';
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
  overlaysPage,
];

/// Every page the gallery shows.
const List<GalleryPage> galleryPages = <GalleryPage>[
  ...foundationPages,
  ...familyPages,
];

/// The gallery: a page list beside the page.
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

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final GalleryPage page = _pages[_selected.clamp(0, _pages.length - 1)];
    return DefaultTextStyle(
      style: ui.type.body.copyWith(color: ui.color.ink),
      child: FieldLayer(
        preset: SkyPreset.home,
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: <Widget>[
            _PageList(
              pages: _pages,
              selected: _selected,
              onSelect: (int index) => setState(() => _selected = index),
            ),
            Expanded(child: _PageView(page: page)),
          ],
        ),
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
  const _PageView({required this.page});

  final GalleryPage page;

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    return Padding(
      padding: EdgeInsetsDirectional.fromSTEB(
        0,
        ui.space.s4,
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
