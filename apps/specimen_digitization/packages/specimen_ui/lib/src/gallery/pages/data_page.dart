/// The data family in every variant, size and state (10 section 6).
///
/// Every control of 10 section 4.5 at once: rows in both modes with every
/// leading slot, progress as a ring at three sizes and as a bar, placeholders
/// in the three shapes they stand in for, an empty state, the numeral tiles
/// with their unit, footer and child slot, gauges with and without a value,
/// avatars, rules, and timelines with and without glyphs. The page is the
/// taste review for the family, and its golden is the diff a change to any of
/// them shows up in first.
library;

import 'package:flutter/widgets.dart';

import '../../../specimen_ui.dart';
import '../gallery_shell.dart';

/// Builds the data page.
Widget buildDataPage(BuildContext context) => const _DataPage();

/// The data page, as the gallery's page list carries it.
///
/// Eight frosted panes rather than the four a product window is held to
/// (09 section 3.3): four numeral tiles in the measures column and four more
/// in the fit section, which shows one tile per column. A specimen sheet
/// states its own number out loud rather than the golden quietly skipping the
/// check; a product window draws a row of tiles, not two.
const GalleryPage dataPage = GalleryPage(
  id: 'data',
  title: 'Data',
  summary:
      'Rows, progress, placeholders, empty states, numeral tiles, gauges, '
      'avatars, rules and timelines, in every variant, size and state.',
  builder: buildDataPage,
  maxGlassPanes: 8,
);

class _DataPage extends StatefulWidget {
  const _DataPage();

  @override
  State<_DataPage> createState() => _DataPageState();
}

class _DataPageState extends State<_DataPage> {
  /// The row a reviewer has open in the detail pane.
  String _open = 'SPEC-2026-0041';

  /// The rows a reviewer has checked in a selection.
  final Set<String> _checked = <String>{'SPEC-2026-0043'};

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    // Two columns rather than one long scroll, as the actions page does. The
    // rows want the wider column because they carry two lines of text and a
    // trailing slot; everything else is narrow by nature.
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        GalleryColumns(
          gap: ui.space.s6,
          flexes: const <int>[3, 2],
          children: <Widget>[_rowsColumn(ui), _measuresColumn(ui)],
        ),
        // The fit section spans the page rather than sitting in a column: a
        // 480 dp specimen inside a 370 dp column is a specimen of 370 dp.
        _fitSection(ui),
      ],
    );
  }

  Widget _fitSection(UiThemeData ui) => Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: <Widget>[
      _Section(
        title: 'Fit: a row and a tile in narrow columns',
        child: _Wrap(
          children: <Widget>[
            for (final double width in fitColumns)
              GallerySpecimen(
                label: '${width.toInt()} dp',
                note: switch (width) {
                  >= 360 => 'the word and the glyph',
                  >= 280 => 'the glyph',
                  _ => 'under the title',
                },
                child: SizedBox(
                  width: width,
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    mainAxisSize: MainAxisSize.min,
                    children: <Widget>[
                      _Rows(
                        ui: ui,
                        children: <Widget>[
                          const UiListRow(
                            title: 'SPEC-2026-0041',
                            subtitle: 'Two readings disagree on the collector',
                            leading: UiIcon(
                              UiIcons.record,
                              size: UiIconSize.action,
                            ),
                            trailing: UiRowTrailing(
                              label: 'Needs review',
                              icon: UiIcons.needsReview,
                            ),
                            onPressed: _noop,
                          ),
                        ],
                      ),
                      SizedBox(height: ui.space.s2),
                      const UiDataTile(
                        label: 'Cleared today',
                        value: 'Not measured',
                      ),
                    ],
                  ),
                ),
              ),
          ],
        ),
      ),
    ],
  );

  Widget _rowsColumn(UiThemeData ui) => Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: <Widget>[
      _Section(
        title: 'UiListRow, leading slots',
        child: _Rows(
          ui: ui,
          children: <Widget>[
            const UiListRow(
              title: 'SPEC-2026-0041',
              subtitle: 'Two readings disagree on the collector',
              leading: UiIcon(UiIcons.record, size: UiIconSize.action),
              trailing: UiIcon(UiIcons.next, size: UiIconSize.inline),
              onPressed: _noop,
            ),
            UiListRow(
              title: 'SPEC-2026-0042',
              subtitle: 'Waiting on label coverage',
              leading: const UiAvatar(name: 'Ana Ruiz'),
              trailing: UiChip(
                label: 'Needs review',
                icon: UiIcons.needsReview,
                status: ui.color.status.needsReview,
              ),
              semanticsLabel:
                  'SPEC-2026-0042, needs review, waiting on label '
                  'coverage',
              onPressed: _noop,
            ),
            UiListRow(
              title: 'SPEC-2026-0043',
              subtitle: 'Cleared 13 Sep 2026, 14:32 CDT',
              // An invisible leading slot, which is what a row looks like
              // before a selection starts. The title's edge is the same
              // three rows down whatever the slot holds.
              leading: const Opacity(
                opacity: 0,
                child: UiIcon(UiIcons.record, size: UiIconSize.action),
              ),
              trailing: Text(
                '3 d',
                style: ui.type.bodySmall.copyWith(color: ui.color.inkSecondary),
              ),
              onPressed: _noop,
            ),
          ],
        ),
      ),
      _Section(
        title: 'UiListRow, open and disabled',
        child: _Rows(
          ui: ui,
          children: <Widget>[
            for (final String id in <String>[
              'SPEC-2026-0041',
              'SPEC-2026-0044',
            ])
              UiListRow(
                title: id,
                subtitle: 'Two readings disagree on the collector',
                leading: const UiIcon(UiIcons.record, size: UiIconSize.action),
                trailing: const UiIcon(UiIcons.next, size: UiIconSize.inline),
                selected: _open == id,
                onPressed: () => setState(() => _open = id),
              ),
            const UiListRow(
              title: 'SPEC-2026-0045',
              subtitle: 'Open in another reviewer session',
              leading: UiIcon(UiIcons.record, size: UiIconSize.action),
              disabledReason:
                  'This record is open in another reviewer session.',
            ),
          ],
        ),
      ),
      _Section(
        title: 'UiListRow, selection mode',
        child: _Rows(
          ui: ui,
          children: <Widget>[
            for (final String id in <String>[
              'SPEC-2026-0043',
              'SPEC-2026-0046',
            ])
              UiListRow(
                title: id,
                subtitle: 'Cleared 13 Sep 2026, 14:32 CDT',
                leading: UiIcon(
                  _checked.contains(id) ? UiIcons.check : UiIcons.unselected,
                  size: UiIconSize.action,
                ),
                mode: UiListRowMode.select,
                selected: _checked.contains(id),
                onPressed: () => setState(() {
                  if (!_checked.remove(id)) _checked.add(id);
                }),
              ),
          ],
        ),
      ),
      _Section(
        title: 'UiListRow at sm, for a menu',
        child: _Rows(
          ui: ui,
          children: <Widget>[
            const UiListRow(
              title: 'Copy the specimen identifier',
              size: UiSize.sm,
              leading: UiIcon(UiIcons.copy, size: UiIconSize.inline),
              trailing: UiKeyCap(label: 'C'),
              onPressed: _noop,
            ),
            const UiListRow(
              title: 'Retry processing',
              size: UiSize.sm,
              leading: UiIcon(UiIcons.retry, size: UiIconSize.inline),
              onPressed: _noop,
            ),
          ],
        ),
      ),
      _Section(
        title: 'UiHairline',
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            const GallerySpecimen(
              label: 'horizontal',
              child: SizedBox(width: 260, child: UiHairline()),
            ),
            SizedBox(height: ui.space.s4),
            const GallerySpecimen(
              label: 'horizontal, inset',
              note: 'the inset clears a leading slot in either script',
              child: SizedBox(
                width: 260,
                child: UiHairline(indent: UiListRowStyle.leadingExtent),
              ),
            ),
            SizedBox(height: ui.space.s4),
            const GallerySpecimen(
              label: 'vertical',
              child: SizedBox(
                height: 40,
                child: Row(children: <Widget>[UiHairline.vertical()]),
              ),
            ),
          ],
        ),
      ),
      const _Section(
        title: 'UiSkeleton',
        // A pulse is a repeating animation, and a golden that waits for one
        // never settles. Muting the ticker captures the placeholder at its
        // resting alpha, which is the frame worth reviewing.
        child: TickerMode(
          enabled: false,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              GallerySpecimen(label: 'row', child: UiSkeleton.row()),
              GallerySpecimen(label: 'row', child: UiSkeleton.row()),
              GallerySpecimen(
                label: 'line',
                child: SizedBox(
                  width: 260,
                  child: UiSkeleton.line(widthFactor: 0.6),
                ),
              ),
              GallerySpecimen(
                label: 'tile',
                child: SizedBox(width: 200, child: UiSkeleton.tile()),
              ),
            ],
          ),
        ),
      ),
      const _Section(
        title: 'UiEmptyState',
        child: GallerySpecimen(
          label: 'no matches, with the way out of it',
          child: UiEmptyState(
            icon: UiIcons.noResults,
            title: 'No matches',
            body: 'No records match the current search and filters.',
            action: UiButton(label: 'Clear filters', onPressed: _noop),
          ),
        ),
      ),
      _Section(
        title: 'UiTimeline',
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: <Widget>[
            const GallerySpecimen(
              label: 'positions',
              note: 'no glyph and no tone, so the number stands in',
              child: UiTimeline(
                semanticsLabel: 'Steps',
                entries: <UiTimelineEntry>[
                  UiTimelineEntry(title: 'Label detection', meta: '2 regions'),
                  UiTimelineEntry(
                    title: 'Readings',
                    meta: '2 readers for each region',
                  ),
                  UiTimelineEntry(title: 'Comparison', meta: 'Not measured'),
                ],
              ),
            ),
            SizedBox(height: ui.space.s4),
            GallerySpecimen(
              label: 'glyphs, tones and slots',
              note: 'a tone always travels with a glyph and a word',
              child: UiTimeline(
                semanticsLabel: 'Lookups',
                entries: <UiTimelineEntry>[
                  UiTimelineEntry(
                    title: 'Species match, GBIF Backbone',
                    meta: 'Attempt 1 · decided transcript',
                    glyph: UiIcons.authority,
                    tone: ui.color.status.authority,
                    trailing: const UiChip(label: 'Match found'),
                  ),
                  UiTimelineEntry(
                    title: 'Place lookup, Google Maps',
                    meta: 'Attempt 2 · retry at 14:40 CDT',
                    glyph: UiIcons.time,
                    tone: ui.color.status.blocked,
                    trailing: const UiChip(label: 'Timed out'),
                    // A child stays quieter than the entry it belongs to: a
                    // ghost control, never a heading that outranks the title.
                    child: const UiButton(
                      label: 'Show the response',
                      variant: UiButtonVariant.ghost,
                      leading: UiIcons.show,
                      onPressed: _noop,
                    ),
                  ),
                  const UiTimelineEntry(
                    title: 'Collector name',
                    meta: 'Transcribed as seen',
                    glyph: UiIcons.modelReading,
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    ],
  );

  Widget _measuresColumn(UiThemeData ui) => Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: <Widget>[
      _Section(
        title: 'UiProgress.ring, determinate',
        child: _Wrap(
          children: <Widget>[
            for (final UiProgressSize size in UiProgressSize.values)
              GallerySpecimen(
                label: size.name,
                note: '${size.diameter.toInt()} dp',
                child: UiProgress.ring(
                  semanticsLabel: 'Upload progress',
                  value: 0.62,
                  size: size,
                ),
              ),
            const GallerySpecimen(
              label: 'complete',
              child: UiProgress.ring(
                semanticsLabel: 'Upload progress',
                value: 1,
              ),
            ),
            const GallerySpecimen(
              label: 'nothing yet',
              note: 'no mark on the track at zero',
              child: UiProgress.ring(
                semanticsLabel: 'Upload progress',
                value: 0,
              ),
            ),
          ],
        ),
      ),
      const _Section(
        title: 'UiProgress.ring, indeterminate',
        child: TickerMode(
          enabled: false,
          child: _Wrap(
            children: <Widget>[
              GallerySpecimen(
                label: 'small',
                note: 'held still for the golden',
                child: UiProgress.ring(
                  semanticsLabel: 'Waiting on the server',
                  size: UiProgressSize.small,
                ),
              ),
              GallerySpecimen(
                label: 'medium',
                child: UiProgress.ring(semanticsLabel: 'Waiting on the server'),
              ),
              GallerySpecimen(
                label: 'large',
                child: UiProgress.ring(
                  semanticsLabel: 'Waiting on the server',
                  size: UiProgressSize.large,
                ),
              ),
            ],
          ),
        ),
      ),
      _Section(
        title: 'UiProgress.bar',
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            for (final double value in <double>[0.12, 0.62, 1])
              Padding(
                padding: EdgeInsetsDirectional.only(bottom: ui.space.s4),
                child: GallerySpecimen(
                  label: '${(value * 100).round()} percent',
                  child: SizedBox(
                    width: 240,
                    child: UiProgress.bar(
                      semanticsLabel: 'Upload progress',
                      value: value,
                    ),
                  ),
                ),
              ),
            const GallerySpecimen(
              label: 'indeterminate',
              note: 'no track, because there is no scale',
              child: TickerMode(
                enabled: false,
                child: SizedBox(
                  width: 240,
                  child: UiProgress.bar(
                    semanticsLabel: 'Waiting on the server',
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
      _Section(
        title: 'UiDataTile',
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            const GallerySpecimen(
              label: 'label, numeral and unit',
              child: SizedBox(
                width: 240,
                child: UiDataTile(
                  label: 'Cleared today',
                  value: '128',
                  unit: 'OF 240',
                ),
              ),
            ),
            SizedBox(height: ui.space.s4),
            const GallerySpecimen(
              label: 'hero',
              note: 'one per window, which the caller keeps to',
              child: SizedBox(
                width: 240,
                child: UiDataTile(
                  label: 'Needs review',
                  value: '17',
                  hero: true,
                ),
              ),
            ),
            SizedBox(height: ui.space.s4),
            const GallerySpecimen(
              label: 'on paper',
              note: 'for a header or a list item, where glass is forbidden',
              child: SizedBox(
                width: 240,
                child: UiDataTile(
                  label: 'In this manifest',
                  value: '312',
                  unit: 'FILES',
                  surface: UiDataTileSurface.paper,
                ),
              ),
            ),
            SizedBox(height: ui.space.s4),
            const GallerySpecimen(
              label: 'footer and child slot',
              note: 'an absence wraps at a word, it never clips to a number',
              child: SizedBox(
                // Wider than the tiles above it: "Not measured" at
                // `display.large` is wider than one 240 dp line, so the
                // specimen is the width that wraps it at the space rather
                // than inside the word.
                width: 300,
                child: UiDataTile(
                  label: 'Risk',
                  value: 'Not measured',
                  footer: 'The policy has not been calibrated.',
                  semanticsLabel: 'Risk, not measured',
                  child: UiArcIndicator(
                    value: null,
                    semanticsLabel: 'Risk',
                    size: 96,
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
      const _Section(
        title: 'UiArcIndicator',
        child: _Wrap(
          children: <Widget>[
            GallerySpecimen(
              label: '270 degrees',
              child: UiArcIndicator(
                value: 0.62,
                semanticsLabel: 'Risk',
                valueLabel: '62 of 100',
                minLabel: '0',
                maxLabel: '100',
              ),
            ),
            GallerySpecimen(
              label: '180 degrees',
              child: UiArcIndicator(
                value: 0.24,
                semanticsLabel: 'Label coverage',
                sweep: UiArcSweep.half,
                minLabel: '0',
                maxLabel: '100',
              ),
            ),
            GallerySpecimen(
              label: 'unmeasured',
              note: 'the glyph and the word, never a marker at zero',
              child: UiArcIndicator(value: null, semanticsLabel: 'Risk'),
            ),
          ],
        ),
      ),
      _Section(
        title: 'UiAvatar',
        child: _Wrap(
          children: <Widget>[
            for (final UiAvatarSize size in UiAvatarSize.values)
              GallerySpecimen(
                label: size.name,
                note: '${size.diameter.toInt()} dp',
                child: UiAvatar(name: 'Ana Ruiz', size: size),
              ),
            const GallerySpecimen(
              label: 'one word',
              child: UiAvatar(name: 'Mei'),
            ),
          ],
        ),
      ),
    ],
  );

  /// The gallery presses nothing. A null callback would render the control
  /// disabled, which is a different specimen.
  static void _noop() {}
}

/// The columns 11 section 3.3 measures a control's fit in.
///
/// Repeated on each family page rather than shared, because the file that
/// would hold it is the gallery shell, which slot G3 owns this wave.
const List<double> fitColumns = <double>[480, 360, 280, 200];

/// A stack of rows, separated the way a list body separates them.
class _Rows extends StatelessWidget {
  const _Rows({required this.ui, required this.children});

  final UiThemeData ui;
  final List<Widget> children;

  @override
  Widget build(BuildContext context) => Surface(
    radius: ui.shape.tile,
    hairline: true,
    clip: true,
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        for (int i = 0; i < children.length; i++) ...<Widget>[
          if (i > 0) const UiHairline(),
          children[i],
        ],
      ],
    ),
  );
}

/// A wrapping row of specimens, aligned on the top edge as the foundation
/// pages are.
class _Wrap extends StatelessWidget {
  const _Wrap({required this.children});

  final List<Widget> children;

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    return Wrap(
      spacing: ui.space.s4,
      runSpacing: ui.space.s3,
      children: children,
    );
  }
}

/// A titled block, tighter than `GallerySection`.
///
/// The same block the actions page uses, for the same reason: a family page
/// carries eight controls and every step of the grid spent on chrome is a
/// control pushed further down the review.
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
