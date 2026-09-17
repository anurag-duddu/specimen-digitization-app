/// The actions family in every variant, size and state (10 section 6).
///
/// Every control of 10 section 4.1 at once: the four button variants at three
/// sizes with the states a gesture would otherwise be needed for held open, an
/// icon button in both variants, a capsule toggle in both selection modes,
/// the three chip variants, a segmented track at two, three and five segments,
/// badges and key caps. The page is the taste review for the family, and its
/// golden is the diff a change to any of them shows up in first.
///
/// The Fit block at the foot of the page is the other half of the review
/// (11 section 3.5): the controls that declare a fit policy, each in a 480,
/// 360, 280 and 200 dp column, so the ladder of 11 section 3.3 is a picture
/// rather than a paragraph. The page's one focused specimen lives there, at
/// 200 dp, because a page has one primary focus and the narrowest column is
/// where a ring drawn outside the control would first run into something.
library;

import 'package:flutter/widgets.dart';

import '../../../specimen_ui.dart';
import '../gallery_shell.dart';

/// Builds the actions page.
Widget buildActionsPage(BuildContext context) => const _ActionsPage();

/// The actions page, as the gallery's page list carries it.
///
/// Declared here rather than inline in the shell so that registering a family
/// is one line in one shared list, which is the smallest thing five family
/// slots can each add without colliding.
const GalleryPage actionsPage = GalleryPage(
  id: 'actions',
  title: 'Actions',
  summary:
      'Buttons, icon buttons, capsule toggles, chips, segmented tracks, '
      'badges and key caps, in every variant, size and state.',
  builder: buildActionsPage,
);

/// The fields a capsule toggle filters on, as a gallery specimen.
enum _Reading { model, reviewer, authority }

/// The panes a segmented track switches between, as a gallery specimen.
enum _Pane { readings, fields, history, regions, evidence }

class _ActionsPage extends StatefulWidget {
  const _ActionsPage();

  @override
  State<_ActionsPage> createState() => _ActionsPageState();
}

class _ActionsPageState extends State<_ActionsPage> {
  final Map<WidgetState, WidgetStatesController> _forced =
      <WidgetState, WidgetStatesController>{
        for (final WidgetState state in <WidgetState>[
          WidgetState.hovered,
          WidgetState.pressed,
        ])
          state: WidgetStatesController(<WidgetState>{state}),
      };

  Set<_Reading> _sources = <_Reading>{_Reading.model};
  Set<_Reading> _oneSource = <_Reading>{_Reading.reviewer};
  _Pane _pane = _Pane.fields;
  _Pane _threePane = _Pane.readings;
  _Pane _fivePane = _Pane.history;
  bool _filterOn = true;
  final List<String> _entered = <String>['Coleoptera', 'Illinois'];
  _Pane _fitPane = _Pane.fields;
  _Pane _fitPlainPane = _Pane.readings;

  @override
  void dispose() {
    for (final WidgetStatesController controller in _forced.values) {
      controller.dispose();
    }
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    // Two columns rather than one long scroll, and the Fit block under both
    // at the full width, because its widest specimen is 480 dp and a column
    // of the pair is not that wide. The buttons and the segmented tracks take
    // the wider column because their labels are sentences and a five segment
    // track at `lg` needs 403 dp to draw its words whole; in the narrow
    // column it drew its own last resort, which is a specimen of the fit
    // policy rather than of the control. Everything else is narrow by nature.
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        GalleryColumns(
          gap: ui.space.s6,
          flexes: const <int>[3, 2],
          children: <Widget>[
            Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                _Section(
                  title: 'UiButton, variants',
                  child: _Row(
                    ui: ui,
                    children: <Widget>[
                      for (final UiButtonVariant variant
                          in UiButtonVariant.values)
                        GallerySpecimen(
                          label: variant.name,
                          child: UiButton(
                            label: _variantLabel(variant),
                            variant: variant,
                            onPressed: _noop,
                          ),
                        ),
                    ],
                  ),
                ),
                _Section(
                  title: 'UiButton, sizes',
                  child: _Row(
                    ui: ui,
                    children: <Widget>[
                      for (final UiSize size in UiSize.values)
                        GallerySpecimen(
                          label: size.name,
                          note: size == UiSize.md
                              ? 'height follows the density'
                              : null,
                          child: UiButton(
                            label: 'Approve record',
                            size: size,
                            onPressed: _noop,
                          ),
                        ),
                    ],
                  ),
                ),
                _Section(
                  title: 'UiButton, states',
                  child: _Row(
                    ui: ui,
                    children: <Widget>[
                      const GallerySpecimen(
                        label: 'rest',
                        child: UiButton(
                          label: 'Approve record',
                          onPressed: _noop,
                        ),
                      ),
                      GallerySpecimen(
                        label: 'hovered',
                        child: UiButton(
                          label: 'Approve record',
                          onPressed: _noop,
                          statesController: _forced[WidgetState.hovered],
                        ),
                      ),
                      GallerySpecimen(
                        label: 'pressed',
                        child: UiButton(
                          label: 'Approve record',
                          onPressed: _noop,
                          statesController: _forced[WidgetState.pressed],
                        ),
                      ),
                      const GallerySpecimen(
                        label: 'disabled',
                        note: 'the reason is on the semantics hint',
                        child: UiButton(
                          label: 'Approve record',
                          disabledReason:
                              'Confirm label coverage before you approve this record.',
                        ),
                      ),
                      const GallerySpecimen(
                        label: 'loading',
                        note: 'the ring is held still for the golden',
                        child: TickerMode(
                          enabled: false,
                          child: UiButton(
                            label: 'Saving',
                            loading: true,
                            onPressed: _noop,
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
                _Section(
                  title: 'UiButton, slots',
                  child: _Row(
                    ui: ui,
                    children: <Widget>[
                      const GallerySpecimen(
                        label: 'leading',
                        child: UiButton(
                          label: 'Retry processing',
                          leading: UiIcons.retry,
                          variant: UiButtonVariant.secondary,
                          onPressed: _noop,
                        ),
                      ),
                      const GallerySpecimen(
                        label: 'trailing',
                        child: UiButton(
                          label: 'Open the next record',
                          trailing: UiIcons.next,
                          variant: UiButtonVariant.ghost,
                          onPressed: _noop,
                        ),
                      ),
                      const GallerySpecimen(
                        label: 'leading and trailing',
                        child: UiButton(
                          label: 'Start new run',
                          leading: UiIcons.processing,
                          trailing: UiIcons.next,
                          variant: UiButtonVariant.secondary,
                          onPressed: _noop,
                        ),
                      ),
                      const GallerySpecimen(
                        label: 'loading, width held',
                        child: TickerMode(
                          enabled: false,
                          child: UiButton(
                            label: 'Retrying',
                            leading: UiIcons.retry,
                            variant: UiButtonVariant.secondary,
                            loading: true,
                            onPressed: _noop,
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
                _Section(
                  title: 'UiSegmented',
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: <Widget>[
                      GallerySpecimen(
                        label: 'two segments',
                        child: UiSegmented<_Pane>(
                          segments: _paneSegments
                              .take(2)
                              .toList(growable: false),
                          value: _pane == _Pane.readings
                              ? _Pane.readings
                              : _Pane.fields,
                          onChanged: (_Pane next) =>
                              setState(() => _pane = next),
                        ),
                      ),
                      SizedBox(height: ui.space.s4),
                      GallerySpecimen(
                        label: 'three segments',
                        child: UiSegmented<_Pane>(
                          segments: _paneSegments
                              .take(3)
                              .toList(growable: false),
                          value: _threePane,
                          onChanged: (_Pane next) =>
                              setState(() => _threePane = next),
                        ),
                      ),
                      SizedBox(height: ui.space.s4),
                      GallerySpecimen(
                        label: 'five segments, at lg',
                        child: UiSegmented<_Pane>(
                          segments: _paneSegments,
                          value: _fivePane,
                          size: UiSize.lg,
                          onChanged: (_Pane next) =>
                              setState(() => _fivePane = next),
                        ),
                      ),
                      SizedBox(height: ui.space.s4),
                      GallerySpecimen(
                        label: 'disabled',
                        child: UiSegmented<_Pane>(
                          segments: _paneSegments
                              .take(3)
                              .toList(growable: false),
                          value: _Pane.readings,
                          onChanged: null,
                          disabledReason:
                              'This run produced one pane of evidence.',
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
            Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                _Section(
                  title: 'UiIconButton',
                  child: _Row(
                    ui: ui,
                    children: <Widget>[
                      for (final UiIconButtonVariant variant
                          in UiIconButtonVariant.values)
                        GallerySpecimen(
                          label: variant.name,
                          child: UiIconButton(
                            icon: UiIcons.rotateView,
                            semanticsLabel: 'Rotate the view',
                            variant: variant,
                            onPressed: _noop,
                          ),
                        ),
                      const GallerySpecimen(
                        label: 'current glyph',
                        note: 'fill form, for a destination in view',
                        child: UiIconButton(
                          icon: UiIcons.queue,
                          semanticsLabel: 'Open the queue',
                          current: true,
                          onPressed: _noop,
                        ),
                      ),
                      const GallerySpecimen(
                        label: 'disabled',
                        child: UiIconButton(
                          icon: UiIcons.correctRegions,
                          semanticsLabel: 'Correct label regions',
                          variant: UiIconButtonVariant.secondary,
                          disabledReason:
                              'Label regions can be corrected once processing ends.',
                        ),
                      ),
                    ],
                  ),
                ),
                _Section(
                  title: 'UiCapsuleToggle',
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: <Widget>[
                      GallerySpecimen(
                        label: 'multiple',
                        child: UiCapsuleToggle<_Reading>(
                          options: _readingOptions,
                          selected: _sources,
                          onChanged: (Set<_Reading> next) =>
                              setState(() => _sources = next),
                        ),
                      ),
                      SizedBox(height: ui.space.s4),
                      GallerySpecimen(
                        label: 'single',
                        child: UiCapsuleToggle<_Reading>(
                          options: _readingOptions,
                          selected: _oneSource,
                          selection: UiToggleSelection.single,
                          onChanged: (Set<_Reading> next) =>
                              setState(() => _oneSource = next),
                        ),
                      ),
                      SizedBox(height: ui.space.s4),
                      const GallerySpecimen(
                        label: 'disabled',
                        child: UiCapsuleToggle<_Reading>(
                          options: _readingOptions,
                          selected: <_Reading>{_Reading.authority},
                          onChanged: null,
                          disabledReason:
                              'This run has one reading to compare.',
                        ),
                      ),
                    ],
                  ),
                ),
                _Section(
                  title: 'UiChip',
                  child: _Row(
                    ui: ui,
                    children: <Widget>[
                      const GallerySpecimen(
                        label: 'tag',
                        child: UiChip(label: 'Coleoptera'),
                      ),
                      GallerySpecimen(
                        label: 'tag, status triple',
                        child: UiChip(
                          label: 'Needs human review',
                          icon: UiIcons.needsReview,
                          status: ui.color.status.needsReview,
                          semanticsLabel: 'Queue: needs human review',
                        ),
                      ),
                      GallerySpecimen(
                        label: 'filter, off',
                        child: UiChip(
                          label: 'Oldest first',
                          variant: UiChipVariant.filter,
                          icon: UiIcons.filter,
                          onPressed: () =>
                              setState(() => _filterOn = !_filterOn),
                        ),
                      ),
                      GallerySpecimen(
                        label: 'filter, on',
                        child: UiChip(
                          label: 'Blocked runs',
                          variant: UiChipVariant.filter,
                          selected: _filterOn,
                          onPressed: () =>
                              setState(() => _filterOn = !_filterOn),
                        ),
                      ),
                      const GallerySpecimen(
                        label: 'filter, disabled',
                        child: UiChip(
                          label: 'Saved filters',
                          variant: UiChipVariant.filter,
                          disabledReason: 'Save a filter to reuse it here.',
                        ),
                      ),
                      for (final String entered in _entered)
                        GallerySpecimen(
                          label: 'input',
                          child: UiChip(
                            label: entered,
                            variant: UiChipVariant.input,
                            onRemove: () =>
                                setState(() => _entered.remove(entered)),
                          ),
                        ),
                    ],
                  ),
                ),
                _Section(
                  title: 'UiBadge',
                  child: _Row(
                    ui: ui,
                    children: <Widget>[
                      const GallerySpecimen(
                        label: 'count',
                        child: UiBadge(4, semanticsLabel: '4 records waiting'),
                      ),
                      const GallerySpecimen(
                        label: 'count, three digits',
                        child: UiBadge(
                          128,
                          semanticsLabel: '128 records waiting',
                        ),
                      ),
                      GallerySpecimen(
                        label: 'count, status',
                        child: UiBadge(
                          12,
                          status: ui.color.status.blocked,
                          semanticsLabel: '12 blocked runs',
                        ),
                      ),
                      const GallerySpecimen(
                        label: 'dot',
                        child: UiBadge.dot(semanticsLabel: 'Unread decisions'),
                      ),
                      GallerySpecimen(
                        label: 'dot, status',
                        child: UiBadge.dot(
                          status: ui.color.status.cleared,
                          semanticsLabel: 'Cleared since you last looked',
                        ),
                      ),
                    ],
                  ),
                ),
                _Section(
                  title: 'UiKeyCap',
                  child: _Row(
                    ui: ui,
                    children: <Widget>[
                      for (final String key in <String>[
                        'J',
                        'K',
                        'Esc',
                        'Shift',
                      ])
                        GallerySpecimen(
                          label: key,
                          child: UiKeyCap(label: key),
                        ),
                      const GallerySpecimen(
                        label: 'spoken',
                        note: 'a printed form that does not say itself aloud',
                        child: UiKeyCap(label: '/', semanticsLabel: 'Slash'),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ],
        ),
        _fit(ui),
      ],
    );
  }

  /// The controls that declare a fit policy, each at the four widths of
  /// 11 section 3.5.
  ///
  /// One note per row rather than one per column: which rung a control takes
  /// at which width is a measurement, and a caption that claimed one would go
  /// stale the first time a word or a type scale moved. The picture is the
  /// claim.
  Widget _fit(UiThemeData ui) => _Section(
    title: 'Fit, at 480, 360, 280 and 200 dp',
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        _FitRow(
          title: 'UiSegmented, named, every segment carrying a glyph',
          note:
              'words, then glyphs with a tooltip each, then a select over the '
              'same options',
          specimen: (double width, bool narrowest) => UiSegmented<_Pane>(
            label: 'Pane',
            segments: _glyphSegments,
            value: _fitPane,
            onChanged: (_Pane next) => setState(() => _fitPane = next),
          ),
        ),
        _FitRow(
          title: 'UiSegmented, unnamed, no glyphs',
          note:
              'no compact variant is available to it, so the words are cut '
              'short and each carries its own tooltip',
          specimen: (double width, bool narrowest) => UiSegmented<_Pane>(
            segments: _paneSegments.take(3).toList(growable: false),
            value: _fitPlainPane,
            onChanged: (_Pane next) => setState(() => _fitPlainPane = next),
          ),
        ),
        _FitRow(
          title: 'UiButton',
          note:
              'it keeps its own width and the parent arranges it; the '
              'narrowest column holds the page\'s focus ring',
          intrinsic: true,
          specimen: (double width, bool narrowest) => UiButton(
            label: 'Open the next record',
            leading: UiIcons.record,
            trailing: UiIcons.next,
            variant: UiButtonVariant.secondary,
            autofocus: narrowest,
            onPressed: _noop,
          ),
        ),
        _FitRow(
          title: 'UiChip, an entered value',
          note: 'the capsule keeps the remove target and the word gives way',
          intrinsic: true,
          specimen: (double width, bool narrowest) => const UiChip(
            label: 'Coleoptera Chrysomelidae',
            variant: UiChipVariant.input,
            onRemove: _noop,
          ),
        ),
        _FitRow(
          title: 'UiButtonRow',
          note:
              'one line with the primary last, or a column with the primary '
              'on top',
          specimen: (double width, bool narrowest) => const UiButtonRow(
            primary: UiButton(label: 'Approve record', onPressed: _noop),
            secondary: UiButton(
              label: 'Cancel',
              variant: UiButtonVariant.ghost,
              onPressed: _noop,
            ),
            tertiary: <UiButton>[
              UiButton(
                label: 'Save a draft',
                variant: UiButtonVariant.secondary,
                onPressed: _noop,
              ),
            ],
          ),
        ),
      ],
    ),
  );

  /// One label per variant, so the page reads as a set of real decisions
  /// rather than four copies of one word (02 section 4.3).
  String _variantLabel(UiButtonVariant variant) => switch (variant) {
    UiButtonVariant.primary => 'Approve record',
    UiButtonVariant.secondary => 'Save correction',
    UiButtonVariant.ghost => 'Cancel',
    UiButtonVariant.danger => 'Start new run',
  };

  static const List<UiToggleOption<_Reading>> _readingOptions =
      <UiToggleOption<_Reading>>[
        UiToggleOption<_Reading>(value: _Reading.model, label: 'Model'),
        UiToggleOption<_Reading>(value: _Reading.reviewer, label: 'Reviewer'),
        UiToggleOption<_Reading>(value: _Reading.authority, label: 'Authority'),
      ];

  /// The same five panes with a glyph each, so the icon only rung of the
  /// ladder is available to the Fit block's first row.
  static const List<UiSegment<_Pane>> _glyphSegments = <UiSegment<_Pane>>[
    UiSegment<_Pane>(
      value: _Pane.readings,
      label: 'Readings',
      icon: UiIcons.modelReading,
    ),
    UiSegment<_Pane>(
      value: _Pane.fields,
      label: 'Fields',
      icon: UiIcons.record,
    ),
    UiSegment<_Pane>(
      value: _Pane.history,
      label: 'History',
      icon: UiIcons.history,
    ),
    UiSegment<_Pane>(
      value: _Pane.regions,
      label: 'Regions',
      icon: UiIcons.correctRegions,
    ),
    UiSegment<_Pane>(
      value: _Pane.evidence,
      label: 'Evidence',
      icon: UiIcons.provenance,
    ),
  ];

  static const List<UiSegment<_Pane>> _paneSegments = <UiSegment<_Pane>>[
    UiSegment<_Pane>(value: _Pane.readings, label: 'Readings'),
    UiSegment<_Pane>(value: _Pane.fields, label: 'Fields'),
    UiSegment<_Pane>(value: _Pane.history, label: 'History'),
    UiSegment<_Pane>(value: _Pane.regions, label: 'Regions'),
    UiSegment<_Pane>(value: _Pane.evidence, label: 'Evidence'),
  ];
}

/// One control at each of the four widths of 11 section 3.5.
///
/// The column is exactly as wide as its caption says, and the control is
/// given all of it. A control that keeps its own width rather than taking
/// what it is given is aligned to the reading start instead, because a
/// stretched button is a picture of its parent rather than of the button
/// (11 section 3.3, the `UiButton` row).
class _FitRow extends StatelessWidget {
  const _FitRow({
    required this.title,
    required this.note,
    required this.specimen,
    this.intrinsic = false,
  });

  /// What is being shown.
  final String title;

  /// What to watch for as the columns narrow.
  final String note;

  /// Builds the specimen for a column [width]. `narrowest` is true for the
  /// last column, which is where the page spends its one focus.
  final Widget Function(double width, bool narrowest) specimen;

  /// True for a control that keeps its own width at every column.
  final bool intrinsic;

  /// The widths 11 section 3.5 names.
  static const List<double> widths = <double>[480, 360, 280, 200];

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    return Padding(
      padding: EdgeInsetsDirectional.only(bottom: ui.space.s5),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Text(title, style: ui.type.bodySmall.copyWith(color: ui.color.ink)),
          Text(
            note,
            style: ui.type.bodySmall.copyWith(color: ui.color.inkTertiary),
          ),
          SizedBox(height: ui.space.s3),
          Wrap(
            spacing: ui.space.s4,
            runSpacing: ui.space.s4,
            children: <Widget>[
              for (final double width in widths)
                GallerySpecimen(
                  label: '${width.toInt()} dp',
                  child: SizedBox(
                    width: width,
                    child: intrinsic
                        ? Align(
                            alignment: AlignmentDirectional.centerStart,
                            child: specimen(width, width == widths.last),
                          )
                        : specimen(width, width == widths.last),
                  ),
                ),
            ],
          ),
        ],
      ),
    );
  }
}

/// A wrapping row of specimens.
///
/// Aligned on the top edge, as the foundation pages are, so that controls of
/// different heights in one row are read against a common line rather than
/// against whatever note happens to sit under them.
class _Row extends StatelessWidget {
  const _Row({required this.ui, required this.children});

  final UiThemeData ui;
  final List<Widget> children;

  @override
  Widget build(BuildContext context) =>
      Wrap(spacing: ui.space.s4, runSpacing: ui.space.s3, children: children);
}

/// A titled block, tighter than `GallerySection`.
///
/// A foundation page has one subject and can spend a full step of the grid
/// between its blocks. This page carries the family's seven controls, and the
/// golden is captured at one window: every step spent on chrome is a control
/// pushed out of the review. The heading role and colour are the foundation
/// page's, so the two still read as one gallery.
class _Section extends StatelessWidget {
  const _Section({required this.title, required this.child});

  final String title;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    return Padding(
      padding: EdgeInsetsDirectional.only(bottom: ui.space.s5),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Text(
            title,
            style: ui.type.label.copyWith(color: ui.color.inkSecondary),
          ),
          SizedBox(height: ui.space.s2),
          child,
        ],
      ),
    );
  }
}

/// The gallery presses nothing. A null callback would render the control
/// disabled, which is a different specimen.
void _noop() {}
