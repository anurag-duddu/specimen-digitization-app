/// The composition patterns (13 section 3).
///
/// The record screen's compact composition, built from the patterns the
/// package now provides and filled with placeholder evidence, beside the
/// pieces it is made of. It exists so the matrix pictures the arrangement
/// before any screen adopts it: what 13 section 0 read as one defect was a
/// screen nobody had drawn whole.
///
/// The frame is a phone. Everything 13 section 2.3 budgets is in it: a top
/// bar, a one line band, a collapsing header pinned at 40 percent, a status
/// strip and segments that scroll, the evidence, and a decision bar the
/// screen itself puts in the scaffold's action bar. The navigation pill is
/// hidden, because the way out of a record is the top bar's back.
library;

import 'dart:math' as math;

import 'package:flutter/widgets.dart';

import '../../../specimen_ui.dart';
import '../gallery_shell.dart';

/// Builds the composition page.
Widget buildCompositionPage(BuildContext context) => const _CompositionPage();

/// The composition page, as the gallery's page list carries it.
const GalleryPage compositionPage = GalleryPage(
  id: 'composition',
  title: 'Composition',
  summary:
      'The record screen at compact, and the patterns 13 section 3 builds it '
      'from.',
  builder: buildCompositionPage,
  // Three, counted rather than guessed: each of the two page frames is a
  // compact window and spends the one pane 13 section 2.2 gives it, on the
  // action bar it floats, and the shell's page list is the third wherever
  // the sidebar is drawn. Every other pinned region in a frame, the top bar,
  // the collapsed header's chrome and the hidden pill, draws the solid form
  // of the same surface.
  maxGlassPanes: 3,
);

const String _identifier = 'CAS 118402';
const String _band = 'Test environment. Not approved museum records.';
const String _bandDetail =
    'Nothing cleared here reaches the collection. Each reading names the '
    'model and the run that produced it.';
const String _summary = '2 things block clearance';
const String _clear = 'Clear record';
const String _defer = 'Defer record';

const List<String> _readings = <String>[
  'Aristolochia gigantea Mart.',
  'Collected 14 March 1946, Serra do Mar',
  'Leg. J. Barbosa, no. 2211',
  'Alt. 820 m, mata atlantica, flowering',
];

/// The two triples this page draws, named so a specimen stays `const`.
UiStatusTriple _cleared(UiStatusColors status) => status.cleared;

/// The triple the record on this page carries.
UiStatusTriple _needsReview(UiStatusColors status) => status.needsReview;

/// The blockers the strip keeps behind its summary.
UiBlockers get _blockers => UiBlockers(
  summary: _summary,
  sheetTitle: 'What blocks clearance',
  items: <UiBlocker>[
    UiBlocker(
      label: 'Label coverage is not confirmed',
      detail: 'Three regions cover 40 percent of the label',
      actionLabel: 'Correct label regions',
      onAction: () {},
    ),
    const UiBlocker(label: 'The classification has no authority'),
  ],
);

class _CompositionPage extends StatelessWidget {
  const _CompositionPage();

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        GallerySection(
          title: 'The record screen at compact (13 section 4.1)',
          child: Wrap(
            spacing: ui.space.s4,
            runSpacing: ui.space.s4,
            children: const <Widget>[
              GallerySpecimen(
                label: 'at rest',
                note: 'the source header holds 55 percent of the viewport',
                child: _Frame(child: _Record()),
              ),
              GallerySpecimen(
                label: 'scrolled',
                note: 'pinned at 40 percent, chrome shrunk to its last row',
                child: _Frame(child: _Record(scrolled: true)),
              ),
            ],
          ),
        ),
        GallerySection(
          title: 'UiStatusStrip (13 section 3.2)',
          child: Wrap(
            spacing: ui.space.s4,
            runSpacing: ui.space.s4,
            children: <Widget>[
              const GallerySpecimen(
                label: 'with its words',
                note: 'the line holds the summary',
                child: _Column(width: 480, child: _Strip()),
              ),
              const GallerySpecimen(
                label: 'glyph rung',
                note: 'the words move to the tooltip and the semantics label',
                child: _Column(width: 280, child: _Strip()),
              ),
              const GallerySpecimen(
                label: 'nothing blocking',
                note: '40 dp with no control on it',
                child: _Column(
                  width: 280,
                  child: UiStatusStrip(
                    disposition: _Disposition(
                      label: 'Cleared',
                      triple: _cleared,
                      icon: UiIcons.cleared,
                    ),
                    facts: <String>['Run 42', 'Version 3'],
                  ),
                ),
              ),
            ],
          ),
        ),
        GallerySection(
          title: 'UiDecisionBar (13 section 3.3)',
          child: Wrap(
            spacing: ui.space.s4,
            runSpacing: ui.space.s4,
            children: const <Widget>[
              GallerySpecimen(
                label: 'compact',
                note: 'previous and next are a swipe, not a control',
                child: _Column(width: 360, child: _Bar()),
              ),
              GallerySpecimen(
                label: 'secondary in the overflow',
                note: 'a decision is moved, never dropped',
                child: _Column(width: 240, child: _Bar()),
              ),
              GallerySpecimen(
                label: 'medium and above',
                note: '620 dp; a column the page has narrowed is compact again',
                child: _Column(width: 620, child: _Bar(edges: true)),
              ),
            ],
          ),
        ),
        GallerySection(
          title: 'UiBanner.strip (13 section 3.5)',
          child: Wrap(
            spacing: ui.space.s4,
            runSpacing: ui.space.s4,
            children: const <Widget>[
              GallerySpecimen(
                label: 'strip',
                note: 'one label line on the tint, the sentence behind a tap',
                child: _Column(
                  width: 360,
                  child: UiBanner.strip(
                    message: _band,
                    detail: _bandDetail,
                    sheetTitle: 'About this build',
                  ),
                ),
              ),
              GallerySpecimen(
                label: 'the band it replaces at compact',
                note: 'two lines and a chevron, which 13 section 2.3 retires',
                child: _Column(
                  width: 360,
                  child: UiBanner(
                    message: _band,
                    tone: UiBannerTone.synthetic,
                    detail: _bandDetail,
                  ),
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }
}

/// A specimen column that never asks for more room than the page has.
///
/// It publishes its own width as the window the specimen is painted into, so
/// a pattern that chooses its arrangement by window class pictures the
/// arrangement the column asks for rather than the gallery's
/// (11 section 3.1). A 240 dp specimen of a compact decision bar is a
/// compact window, whatever the reviewer's screen is.
class _Column extends StatelessWidget {
  const _Column({required this.width, required this.child});

  final double width;
  final Widget child;

  @override
  Widget build(BuildContext context) => LayoutBuilder(
    builder: (BuildContext context, BoxConstraints constraints) {
      final double drawn = math.min(width, constraints.maxWidth);
      return SizedBox(
        width: drawn,
        child: MediaQuery(
          data: MediaQuery.of(
            context,
          ).copyWith(size: Size(drawn, MediaQuery.sizeOf(context).height)),
          child: child,
        ),
      );
    },
  );
}

/// A phone shaped window with a page frame inside it.
class _Frame extends StatelessWidget {
  const _Frame({required this.child});

  /// The phone 13 section 0 measured the defect on, at the height a gallery
  /// window has room for. The width caps to the page's own column, so the
  /// matrix draws a compact window at every class rather than overflowing at
  /// the narrow ones.
  static const Size size = Size(390, 640);

  final Widget child;

  @override
  Widget build(BuildContext context) => LayoutBuilder(
    builder: (BuildContext context, BoxConstraints constraints) {
      final double width = math.min(size.width, constraints.maxWidth);
      return SizedBox(
        width: width,
        height: size.height,
        child: MediaQuery(
          data: MediaQuery.of(context).copyWith(size: Size(width, size.height)),
          child: ClipRect(child: child),
        ),
      );
    },
  );
}

/// The whole composition, as one screen.
class _Record extends StatefulWidget {
  const _Record({this.scrolled = false});

  /// True to draw the header collapsed, which is where the flat pane and the
  /// one row of chrome appear.
  final bool scrolled;

  @override
  State<_Record> createState() => _RecordState();
}

class _RecordState extends State<_Record> {
  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    return UiScaffold(
      sky: SkyPreset.work,
      topBar: UiTopBar(
        leading: UiIconButton(
          icon: UiIcons.back,
          semanticsLabel: 'Back to queue',
          onPressed: () {},
        ),
        title: _identifier,
        actions: <Widget>[
          UiIconButton(
            icon: UiIcons.more,
            semanticsLabel: 'More record commands',
            onPressed: () {},
          ),
        ],
      ),
      banner: const UiBanner.strip(
        message: _band,
        detail: _bandDetail,
        sheetTitle: 'About this build',
      ),
      nav: UiPillNav(
        destinations: const <UiNavDestination>[
          UiNavDestination(label: 'Queue', icon: UiIcons.queue),
          UiNavDestination(label: 'Intake', icon: UiIcons.intake),
          UiNavDestination(label: 'Sources', icon: UiIcons.sources),
        ],
        currentIndex: 0,
        onSelect: (int _) {},
      ),
      body: _RecordBody(scrolled: widget.scrolled, ui: ui),
    );
  }
}

/// The body, and what it asks of the frame around it (13 section 3.4).
class _RecordBody extends StatefulWidget {
  const _RecordBody({required this.scrolled, required this.ui});

  final bool scrolled;
  final UiThemeData ui;

  @override
  State<_RecordBody> createState() => _RecordBodyState();
}

class _RecordBodyState extends State<_RecordBody> {
  final ScrollController _controller = ScrollController();
  UiScaffoldSlots? _slots;

  @override
  void initState() {
    super.initState();
    if (!widget.scrolled) return;
    // Drawn where a reviewer's thumb would have left it, so the picture shows
    // the collapsed state rather than describing it.
    WidgetsBinding.instance.addPostFrameCallback((Duration _) {
      if (!_controller.hasClients) return;
      _controller.jumpTo(_controller.position.maxScrollExtent);
    });
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    // A routed screen fills the action bar, hides the pill and asks for the
    // one line band. The frame reads all three.
    _slots = UiScaffoldSlots.of(context)
      ?..setActionBar(
        UiDecisionBar(
          primary: UiButton(label: _clear, onPressed: () {}),
          secondary: UiButton(label: _defer, onPressed: () {}),
          count: '1 of 4',
        ),
        owner: this,
      )
      ..setNavVisible(false, owner: this)
      ..setBandCompact(true, owner: this);
  }

  @override
  void dispose() {
    _slots?.release(this);
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = widget.ui;
    return UiDecisionSwipe(
      onPrevious: () {},
      onNext: () {},
      // One scroll for the whole screen, and the only one: the evidence, the
      // strip and the segments are slivers of it rather than lists inside it
      // (13 section 2.1).
      child: CustomScrollView(
        controller: _controller,
        slivers: <Widget>[
          UiCollapsingHeader(
            primary: true,
            content: const _Photograph(),
            chrome: <Widget>[
              _ChromeRow(
                children: <Widget>[
                  UiIconButton(
                    icon: UiIcons.zoomOut,
                    semanticsLabel: 'Zoom out',
                    onPressed: () {},
                  ),
                  UiIconButton(
                    icon: UiIcons.fitToView,
                    semanticsLabel: 'Fit the photograph',
                    onPressed: () {},
                  ),
                  UiIconButton(
                    icon: UiIcons.zoomIn,
                    semanticsLabel: 'Zoom in',
                    onPressed: () {},
                  ),
                ],
              ),
              const _ChromeRow(
                children: <Widget>[
                  UiChip(label: 'Label', selected: true),
                  UiChip(label: 'Determination'),
                  UiChip(label: 'Barcode'),
                ],
              ),
            ],
          ),
          SliverPadding(
            padding: EdgeInsetsDirectional.fromSTEB(
              ui.space.s4,
              ui.space.s4,
              ui.space.s4,
              0,
            ),
            sliver: const SliverToBoxAdapter(child: _Strip()),
          ),
          SliverPadding(
            padding: EdgeInsetsDirectional.symmetric(
              horizontal: ui.space.s4,
              vertical: ui.space.s4,
            ),
            sliver: SliverToBoxAdapter(
              child: UiSegmented<int>(
                value: 0,
                onChanged: (int _) {},
                segments: const <UiSegment<int>>[
                  UiSegment<int>(value: 0, label: 'Readings'),
                  UiSegment<int>(value: 1, label: 'Fields'),
                  UiSegment<int>(value: 2, label: 'History'),
                ],
              ),
            ),
          ),
          SliverPadding(
            padding: EdgeInsetsDirectional.fromSTEB(
              ui.space.s4,
              0,
              ui.space.s4,
              UiScaffold.of(context).bottomInset,
            ),
            sliver: SliverList.builder(
              itemCount: _readings.length,
              itemBuilder: (BuildContext context, int index) => UiListRow(
                title: _readings[index],
                subtitle: 'Model reading, not reviewed',
                onPressed: () {},
              ),
            ),
          ),
        ],
      ),
    );
  }
}

/// One row of the header's chrome band.
///
/// A horizontal strip inside the one vertical scroll, which is the single
/// exception 13 section 2.1 allows, so a band of controls narrower than the
/// window it is drawn in scrolls rather than overflowing.
class _ChromeRow extends StatelessWidget {
  const _ChromeRow({required this.children});

  final List<Widget> children;

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    return EdgeFadedRow(
      index: 0,
      length: children.length,
      fadeExtent: ui.space.s6,
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          for (int i = 0; i < children.length; i++) ...<Widget>[
            if (i != 0) SizedBox(width: ui.space.s2),
            children[i],
          ],
        ],
      ),
    );
  }
}

/// The status chip the record's disposition is, resolved from the tokens.
///
/// `StatusChip` is a pattern in the application (10 section 5) and the
/// gallery cannot import it, so the page composes the same two tokens the
/// pattern does: the status triple and its registry glyph.
class _Disposition extends StatelessWidget {
  const _Disposition({
    required this.label,
    required this.triple,
    required this.icon,
  });

  final String label;
  final UiStatusTriple Function(UiStatusColors status) triple;
  final IconSpec icon;

  @override
  Widget build(BuildContext context) =>
      UiChip(label: label, status: triple(context.ui.color.status), icon: icon);
}

/// A stand in for the photograph on its matte.
class _Photograph extends StatelessWidget {
  const _Photograph();

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    return ColoredBox(
      color: ui.color.matte,
      child: Center(
        child: UiIcon(
          UiIcons.image,
          size: UiIconSize.display,
          color: ui.color.inkTertiary,
        ),
      ),
    );
  }
}

/// The strip both the frame and its own section draw.
class _Strip extends StatelessWidget {
  const _Strip();

  @override
  Widget build(BuildContext context) => UiStatusStrip(
    disposition: const _Disposition(
      label: 'Needs review',
      triple: _needsReview,
      icon: UiIcons.needsReview,
    ),
    facts: const <String>['Run 42', 'Version 3'],
    blockers: _blockers,
  );
}

/// The decision bar both the frame and its own section draw.
class _Bar extends StatelessWidget {
  const _Bar({this.edges = false});

  /// True where the specimen has a previous and a next to give the bar.
  final bool edges;

  @override
  Widget build(BuildContext context) => UiDecisionBar(
    primary: UiButton(label: _clear, onPressed: () {}),
    secondary: UiButton(label: _defer, onPressed: () {}),
    count: '1 of 4',
    onPrevious: edges ? () {} : null,
    onNext: edges ? () {} : null,
  );
}
