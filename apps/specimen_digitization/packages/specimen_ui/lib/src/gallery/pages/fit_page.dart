/// The fit matrix (11 section 3.5).
///
/// One section per row of the fit table in 11 section 3.3, in the order that
/// table lists them, each drawn in a 480, 360, 280 and 200 dp column. 480 is a
/// comfortable column, 360 a phone, 280 a narrow pane beside a source image,
/// and 200 the width the gallery shell used to leave for its content when it
/// kept a 220 dp sidebar at phone width, which is where the wrapping labels of
/// 11 section 0 were first seen.
///
/// What each column is evidence of: given at least its intrinsic width a
/// control lays out as its family page draws it, and given less it switches to
/// the compact variant it declares, ending in an ellipsis when none fits. A
/// label never wraps and a control never shrinks below its intrinsic width.
/// The section note names the variants the table gives that control, so a
/// reader can compare the picture with the rule without leaving the page.
library;

import 'package:flutter/widgets.dart';

import '../../../specimen_ui.dart';
import '../gallery_shell.dart';

/// Builds the fit page.
Widget buildFitPage(BuildContext context) => const _FitPage();

/// The fit page, as the gallery's page list carries it.
const GalleryPage fitPage = GalleryPage(
  id: 'fit',
  title: 'Fit',
  summary:
      'Every control of the fit table at 480, 360, 280 and 200 dp, at rest '
      'and focused.',
  builder: buildFitPage,
  // Three of the ten controls are frosted panes of their own: the top bar,
  // the navigation row and the toast. This page draws each of them once per
  // column, so four columns cost twelve panes, and the shell's page list is
  // the thirteenth wherever the sidebar is drawn. A product window would
  // never do this; a specimen sheet exists to, and it states its number out
  // loud rather than letting the golden skip the check (10 section 6).
  maxGlassPanes: 13,
);

/// The widths every section draws its control at (11 section 3.3).
///
/// The same four the control contract's clause 13 pumps a control at, so a
/// column here and a harness failure there name the same number.
///
/// Narrowest first. The four columns and their gutters come to 1380 dp and no
/// window in the system leaves a page that much, so one end of the row is
/// always off screen; the end worth losing is the wide one, which is the case
/// every family page already reviews. Read left to right this is a control
/// recovering as it is given room rather than degrading as it is starved,
/// which says the same thing in the other direction.
const List<double> fitColumns = <double>[200, 280, 360, 480];

/// The panes a segmented track and a tab strip switch between.
enum _Pane {
  /// The readings pane.
  readings,

  /// The fields pane.
  fields,

  /// The history pane.
  history,

  /// The regions pane.
  regions,

  /// The evidence pane.
  evidence,
}

/// What each pane is called, in the order a reviewer reads them.
const Map<_Pane, String> _paneLabels = <_Pane, String>{
  _Pane.readings: 'Readings',
  _Pane.fields: 'Fields',
  _Pane.history: 'History',
  _Pane.regions: 'Regions',
  _Pane.evidence: 'Evidence',
};

class _FitPage extends StatefulWidget {
  const _FitPage();

  @override
  State<_FitPage> createState() => _FitPageState();
}

class _FitPageState extends State<_FitPage> {
  final ValueNotifier<int> _tab = ValueNotifier<int>(1);
  final TextEditingController _collector = TextEditingController();
  _Pane _pane = _Pane.fields;
  int _destination = 0;
  bool _filter = true;

  @override
  void dispose() {
    _tab.dispose();
    _collector.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        _Preamble(ui: ui),
        SizedBox(height: ui.space.s6),
        _Section(
          title: 'UiSegmented',
          variants:
              'Equal segments at the widest label, then glyph only segments '
              'with tooltips, then a UiSelect on the same options. An '
              'ellipsis in each segment when none of the three fits.',
          rest: (BuildContext context) => UiSegmented<_Pane>(
            value: _pane,
            segments: <UiSegment<_Pane>>[
              for (final _Pane pane in _Pane.values)
                UiSegment<_Pane>(value: pane, label: _paneLabels[pane]!),
            ],
            onChanged: (_Pane pane) => setState(() => _pane = pane),
          ),
          focusNote:
              'The ring is drawn on the segment that holds focus, inside the '
              'track. The actions page reviews it.',
        ),
        _Section(
          title: 'UiButton',
          variants:
              'None. A button keeps its width and the parent arranges. Given '
              'less, the label ends in an ellipsis and the tooltip carries '
              'it whole.',
          // Long enough to need more than 200 dp. A specimen whose label
          // happens to fit every column is evidence of nothing.
          rest: (BuildContext context) => const UiButton(
            label: 'Send for another reading',
            leading: UiIcons.check,
            onPressed: _noop,
          ),
          ring: const _Ring(shape: FocusRingShape.stadium),
        ),
        _Section(
          title: 'UiChip',
          variants:
              'None. Given less, the label ends in an ellipsis and the '
              'tooltip carries it whole.',
          rest: (BuildContext context) => UiChip(
            label: 'Two readings disagree on the collector',
            variant: UiChipVariant.filter,
            icon: UiIcons.needsReview,
            selected: _filter,
            onPressed: () => setState(() => _filter = !_filter),
          ),
          ring: const _Ring(shape: FocusRingShape.stadium),
        ),
        _Section(
          title: 'UiTabs and the navigation row',
          variants:
              'A row that scrolls, with a fade at each edge. An ellipsis in '
              'each tab when even that does not fit.',
          rest: (BuildContext context) => Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              UiTabs(
                tabs: <UiTab>[
                  for (final _Pane pane in _Pane.values.take(4))
                    UiTab(label: _paneLabels[pane]!),
                ],
                selected: _tab,
                semanticsLabel: 'Record panels',
              ),
              SizedBox(height: ui.space.s3),
              UiPillNav(
                destinations: const <UiNavDestination>[
                  UiNavDestination(label: 'Queue', icon: UiIcons.queue),
                  UiNavDestination(label: 'Intake', icon: UiIcons.intake),
                  UiNavDestination(label: 'Sources', icon: UiIcons.sources),
                ],
                currentIndex: _destination,
                onSelect: (int index) => setState(() => _destination = index),
              ),
            ],
          ),
          focusNote:
              'The ring is drawn on the tab or the destination that holds '
              'focus. The overlays and navigation pages review it.',
        ),
        _Section(
          title: 'UiTopBar',
          variants:
              'The title takes the ellipsis first. Actions beyond two '
              'collapse into an overflow menu.',
          rest: (BuildContext context) => const UiTopBar(
            title: 'Specimen SPEC 2026 0041',
            scrolledUnder: false,
            leading: UiIconButton(
              icon: UiIcons.back,
              semanticsLabel: 'Back to the queue',
              onPressed: _noop,
            ),
            actions: <Widget>[
              UiIconButton(
                icon: UiIcons.reload,
                semanticsLabel: 'Reload this record',
                onPressed: _noop,
              ),
              UiIconButton(
                icon: UiIcons.filter,
                semanticsLabel: 'Filter the readings',
                onPressed: _noop,
              ),
            ],
          ),
          focused: (BuildContext context) => const UiTopBar(
            title: 'Specimen SPEC 2026 0041',
            scrolledUnder: false,
            leading: UiIconButton(
              icon: UiIcons.back,
              semanticsLabel: 'Back to the queue',
              onPressed: _noop,
            ),
            actions: <Widget>[
              // The bar's ring belongs to an action, and actions is a slot, so
              // this is the ring the product draws rather than one around the
              // whole bar.
              _Ringed(
                ring: _Ring(shape: FocusRingShape.stadium),
                child: UiIconButton(
                  icon: UiIcons.reload,
                  semanticsLabel: 'Reload this record',
                  onPressed: _noop,
                ),
              ),
              UiIconButton(
                icon: UiIcons.filter,
                semanticsLabel: 'Filter the readings',
                onPressed: _noop,
              ),
            ],
          ),
        ),
        _Section(
          title: 'UiDataTile',
          variants:
              'The numeral steps down one display role at a time, as far as '
              'display.medium, and then a FittedBox holds it.',
          // A four figure numeral beside its unit, which is what a tile in
          // this product carries once a collection is past its first day.
          rest: (BuildContext context) => const UiDataTile(
            label: 'Cleared this week',
            value: '1,284',
            unit: 'OF 2,400',
            footer: 'Up 214 on last week',
          ),
          focusNote:
              'A tile has nothing to focus. 10 section 2 scopes it out of the '
              'control contract for that reason.',
        ),
        _Section(
          title: 'UiListRow',
          variants:
              'The trailing control drops its label and keeps its glyph; the '
              'title takes two lines, because a row title is content. The '
              'title ellipsises last.',
          rest: (BuildContext context) => UiListRow(
            title: 'SPEC 2026 0041',
            subtitle: 'Two readings disagree on the collector',
            leading: const UiIcon(UiIcons.record, size: UiIconSize.action),
            trailing: UiChip(
              label: 'Needs human review',
              icon: UiIcons.needsReview,
              status: ui.color.status.needsReview,
            ),
            semanticsLabel:
                'SPEC 2026 0041, needs human review, two readings disagree '
                'on the collector',
            onPressed: _noop,
          ),
          // A row tiles against its neighbours and the pane around it owns the
          // shape, so its ring is a superellipse at radius none.
          ring: _Ring(radius: ui.shape.none),
        ),
        _Section(
          title: 'UiDialog and UiSheet actions',
          variants:
              'The actions stack, primary on top. Each label ends in an '
              'ellipsis when even the stack is too narrow.',
          rest: (BuildContext context) => const UiModalActions(
            primary: UiButton(
              label: 'Approve this record',
              onPressed: _noop,
            ),
            secondary: UiButton(
              label: 'Keep it for later',
              variant: UiButtonVariant.secondary,
              onPressed: _noop,
            ),
          ),
          focusNote:
              'The ring is drawn on whichever button holds focus, and the '
              'UiButton section above shows it.',
        ),
        _Section(
          title: 'UiBanner and UiToast',
          variants:
              'The action moves under the text. The text itself wraps, '
              'because a sentence is content rather than a label.',
          rest: (BuildContext context) => Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              const UiBanner(
                message: 'Readings refresh every twenty seconds.',
                tone: UiBannerTone.info,
                onDismiss: _noop,
                dismissLabel: 'Hide this banner',
              ),
              SizedBox(height: ui.space.s3),
              const UiToast(
                data: UiToastData(
                  message: 'Upload paused. The network dropped.',
                  icon: UiIcons.syncProblem,
                  actionLabel: 'Retry the upload',
                  onAction: _noop,
                ),
              ),
            ],
          ),
          focusNote:
              'The ring is drawn on the dismiss control or the toast action, '
              'and the UiButton section above shows it.',
        ),
        _Section(
          title: 'UiField',
          variants:
              'None. The box stretches to the width it is given, and the '
              'label and the footer wrap, because both are content.',
          rest: (BuildContext context) => UiField(
            label: 'Collector as written on the label',
            controller: _collector,
            hintText: 'Say what you saw on the label',
            helpText: 'Copy the words exactly, including the abbreviations.',
            leading: UiIcons.edit,
          ),
          focusNote:
              'The box rings itself, for any focus, pointer or keyboard, '
              'because a focused field is being edited (09 section 3.6, fit '
              'amendment). The inputs page reviews it in every shape.',
        ),
      ],
    );
  }
}

/// What the page is evidence of, said once at the top of it.
class _Preamble extends StatelessWidget {
  const _Preamble({required this.ui});

  final UiThemeData ui;

  @override
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: <Widget>[
      Text(
        'Each section draws one row of the fit table at the four widths, at '
        'rest above and focused below. A label never wraps, a control never '
        'shrinks below its intrinsic width, and given less it switches to '
        'the compact variant it declares before anything ends in an '
        'ellipsis.',
        style: ui.type.body.copyWith(color: ui.color.inkSecondary),
      ),
      SizedBox(height: ui.space.s2),
      Text(
        'A focused cell is drawn with the FocusRing primitive on the box the '
        'control rings itself, because one control on a page can hold '
        'primary focus and forty cannot. Where the ring belongs to a member '
        'the control builds for itself, the section says where it lives '
        'rather than drawing a ring the product never draws.',
        style: ui.type.bodySmall.copyWith(color: ui.color.inkTertiary),
      ),
    ],
  );
}

/// How a section draws the ring its control carries under focus.
@immutable
class _Ring {
  const _Ring({this.radius, this.shape = FocusRingShape.superellipse});

  /// The control's own corner radius, or null for the primitive's default.
  final double? radius;

  /// The shape the control is drawn in, which is the shape of its ring.
  final FocusRingShape shape;
}

/// Draws [child] carrying the ring it takes under focus.
///
/// `FocusableActionDetector` raises the real ring from primary focus alone, so
/// a page that acted focus out would review one cell of this matrix and leave
/// the other thirty nine at rest. The ring is the whole focus treatment
/// (09 section 3.6, fit amendment) and it is painted outside the component, on
/// the component's own box, so drawing it here with the primitive on that same
/// box is the picture the product draws rather than an impression of it.
class _Ringed extends StatelessWidget {
  const _Ringed({required this.ring, required this.child});

  final _Ring ring;
  final Widget child;

  @override
  Widget build(BuildContext context) => FocusRing(
    visible: true,
    radius: ring.radius,
    shape: ring.shape,
    child: child,
  );
}

/// One row of the fit table, drawn at each of [fitColumns].
class _Section extends StatelessWidget {
  const _Section({
    required this.title,
    required this.variants,
    required this.rest,
    this.ring,
    this.focused,
    this.focusNote,
  }) : assert(
         ring == null || focused == null,
         'a section rings its control or builds its own focused specimen, '
         'never both',
       ),
       assert(
         ring != null || focused != null || focusNote != null,
         'a section without a focused specimen says where the ring lives',
       );

  /// The control's name, as 10 section 4 writes it.
  final String title;

  /// The compact variants the fit table gives this control, in its order.
  final String variants;

  /// Draws the control at rest.
  final WidgetBuilder rest;

  /// The ring the control carries under focus, where the control is its own
  /// focus target.
  final _Ring? ring;

  /// Draws the control focused, where the ring belongs to a member the
  /// control takes as a slot.
  final WidgetBuilder? focused;

  /// Where the ring lives, for a control that builds its own focus target.
  final String? focusNote;

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final WidgetBuilder? focusedCell =
        focused ??
        (ring == null
            ? null
            : (BuildContext context) =>
                  _Ringed(ring: ring!, child: rest(context)));
    return GallerySection(
      title: title,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Text(
            variants,
            style: ui.type.bodySmall.copyWith(color: ui.color.inkSecondary),
          ),
          if (focusedCell == null && focusNote != null) ...<Widget>[
            SizedBox(height: ui.space.s1),
            Text(
              focusNote!,
              style: ui.type.bodySmall.copyWith(color: ui.color.inkTertiary),
            ),
          ],
          SizedBox(height: ui.space.s4),
          // Horizontal, so a 480 dp column stays 480 dp in a 360 dp window
          // instead of being squeezed into it. A specimen the window cannot
          // hold is scrolled past rather than redrawn at a width the section
          // is not about.
          SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                for (final double width in fitColumns) ...<Widget>[
                  _Cell(width: width, rest: rest, focused: focusedCell),
                  if (width != fitColumns.last) SizedBox(width: ui.space.s5),
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }
}

/// One control at one width, at rest above and focused below.
class _Cell extends StatelessWidget {
  const _Cell({required this.width, required this.rest, this.focused});

  final double width;
  final WidgetBuilder rest;
  final WidgetBuilder? focused;

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final WidgetBuilder? below = focused;
    return SizedBox(
      width: width,
      child: Column(
        // Start, not stretch: a control given 480 dp takes the width it needs
        // and no more, which is the first half of what the table promises.
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          Text(
            '${width.toStringAsFixed(0)} dp',
            style: ui.type.mono.identifier.copyWith(
              color: ui.color.inkSecondary,
            ),
          ),
          SizedBox(height: ui.space.s2),
          rest(context),
          if (below != null) ...<Widget>[
            // Room for the ring, which is drawn outside the control and would
            // otherwise run into the specimen above it.
            SizedBox(height: ui.space.s4),
            below(context),
          ],
        ],
      ),
    );
  }
}

/// A specimen's action, which does nothing but exist.
void _noop() {}
