/// The overlays family in every state (10 sections 4.3 and 6).
///
/// Banners and disclosures render in place, because they are in the page flow.
/// Menus, tooltips, toasts, sheets and dialogs render as their triggers, with
/// the toast capsule also drawn in place so the golden reviews the capsule
/// rather than an empty corner. The sheet and the dialog have goldens of their
/// own, opened by the family golden test.
library;

import 'package:flutter/widgets.dart';

import '../../../specimen_ui.dart';
import '../gallery_shell.dart';
import '../fit_columns.dart';

/// Builds the overlays page.
Widget buildOverlaysPage(BuildContext context) => const _OverlaysPage();

/// The overlays family page, as the gallery shell lists it.
///
/// Seven frosted panes rather than the four a product window is held to
/// (09 section 3.3): three toast capsules in the triggers section and four
/// more in the fit section, which shows one capsule per column. A specimen
/// sheet states its own number out loud rather than the golden quietly
/// skipping the check; a product window never draws seven toasts, because
/// `UiToastHost` shows one at a time.
const GalleryPage overlaysPage = GalleryPage(
  id: 'overlays',
  title: 'Overlays',
  summary:
      'Menus, tooltips, toasts, banners, disclosures, tabs, sheets and '
      'dialogs.',
  builder: buildOverlaysPage,
  maxGlassPanes: 7,
);

class _OverlaysPage extends StatefulWidget {
  const _OverlaysPage();

  @override
  State<_OverlaysPage> createState() => _OverlaysPageState();
}

class _OverlaysPageState extends State<_OverlaysPage> {
  final ValueNotifier<int> _tab = ValueNotifier<int>(0);

  /// The fit section's strips, all on the middle tab, so the golden shows a
  /// scrolling strip that has been scrolled rather than one at its start.
  final ValueNotifier<int> _fit = ValueNotifier<int>(1);

  @override
  void dispose() {
    _tab.dispose();
    _fit.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        GallerySection(
          title: 'UiBanner, every tone',
          child: GalleryColumns(
            gap: ui.space.s4,
            children: <Widget>[
              const _BannerColumn(specimens: _bannerSpecimens),
              Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: <Widget>[
                  const _BannerColumn(specimens: _moreBannerSpecimens),
                  SizedBox(height: ui.space.s2),
                  const UiBanner(
                    message: 'Test environment. Not approved museum records.',
                    tone: UiBannerTone.synthetic,
                    detail:
                        'Each reading names the model and provider that '
                        'produced it.',
                  ),
                  SizedBox(height: ui.space.s2),
                  const UiBanner(
                    message:
                        'Readings refresh every twenty seconds while a '
                        'record is open.',
                    onDismiss: _noop,
                    dismissLabel: 'Hide this banner',
                  ),
                ],
              ),
            ],
          ),
        ),
        GallerySection(
          title: 'UiDisclosure and UiTabs',
          child: GalleryColumns(
            gap: ui.space.s4,
            children: <Widget>[
              Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: <Widget>[
                  Surface(
                    radius: ui.shape.tile,
                    hairline: true,
                    child: UiDisclosure(
                      title: 'Label coverage',
                      summary: 'Three regions, one unmeasured',
                      child: Text(
                        'Region 3 has no measured area.',
                        style: ui.type.body.copyWith(
                          color: ui.color.inkSecondary,
                        ),
                      ),
                    ),
                  ),
                  SizedBox(height: ui.space.s2),
                  Surface(
                    radius: ui.shape.tile,
                    hairline: true,
                    child: UiDisclosure(
                      title: 'Why this is not calibrated',
                      initiallyExpanded: true,
                      child: Text(
                        'The score has no reference set behind it, so it '
                        'ranks records and does not measure them.',
                        style: ui.type.body.copyWith(
                          color: ui.color.inkSecondary,
                        ),
                      ),
                    ),
                  ),
                ],
              ),
              Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  UiTabs(
                    tabs: _tabs,
                    selected: _tab,
                    semanticsLabel: 'Record panels',
                  ),
                  SizedBox(height: ui.space.s3),
                  UiTabView(
                    selected: _tab,
                    children: <Widget>[
                      for (final String pane in _panes)
                        Text(
                          pane,
                          style: ui.type.body.copyWith(
                            color: ui.color.inkSecondary,
                          ),
                        ),
                    ],
                  ),
                ],
              ),
            ],
          ),
        ),
        GallerySection(
          title: 'Triggers and UiToast',
          child: Wrap(
            spacing: ui.space.s4,
            runSpacing: ui.space.s4,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: <Widget>[
              GallerySpecimen(
                label: 'UiMenuTrigger',
                child: UiMenuTrigger(
                  semanticsLabel: 'Record actions',
                  label: 'Record actions',
                  items: _menuItems,
                ),
              ),
              const GallerySpecimen(
                label: 'UiTooltip',
                note: 'after 400 ms of hover',
                child: UiTooltip(
                  message: 'Rotate view 90 degrees',
                  child: UiButton(
                    label: 'Rotate view',
                    variant: UiButtonVariant.secondary,
                    onPressed: _noop,
                  ),
                ),
              ),
              const GallerySpecimen(
                label: 'UiTooltip.reason',
                note: 'carries a disabled reason',
                child: _DisabledReason(),
              ),
              GallerySpecimen(
                label: 'UiSheet',
                child: UiButton(
                  label: 'Open a sheet',
                  variant: UiButtonVariant.secondary,
                  onPressed: () => openGallerySheet(context),
                ),
              ),
              GallerySpecimen(
                label: 'UiDialog',
                child: UiButton(
                  label: 'Open a dialog',
                  variant: UiButtonVariant.secondary,
                  onPressed: () => openGalleryDialog(context),
                ),
              ),
              const GallerySpecimen(
                label: 'message only',
                note: 'clears itself after six seconds',
                child: UiToast(
                  data: UiToastData(
                    message: 'Review recorded on version 4',
                    icon: UiIcons.cleared,
                  ),
                ),
              ),
              const GallerySpecimen(
                label: 'with an action',
                note: 'waits for the reviewer',
                child: UiToast(
                  data: UiToastData(
                    message: 'Upload paused. The network dropped.',
                    icon: UiIcons.syncProblem,
                    actionLabel: 'Retry upload',
                    onAction: _noop,
                  ),
                ),
              ),
            ],
          ),
        ),
        GallerySection(
          title: 'Fit: a banner, a toast and a tab strip in narrow columns',
          child: Wrap(
            spacing: ui.space.s4,
            runSpacing: ui.space.s4,
            crossAxisAlignment: WrapCrossAlignment.start,
            children: <Widget>[
              for (final double width in fitColumns)
                GallerySpecimen(
                  label: '${width.toInt()} dp',
                  child: SizedBox(
                    width: width,
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      mainAxisSize: MainAxisSize.min,
                      children: <Widget>[
                        const UiBanner(
                          message: 'Upload paused. The network dropped.',
                          tone: UiBannerTone.blocked,
                          actionLabel: 'Retry upload',
                          onAction: _noop,
                        ),
                        SizedBox(height: ui.space.s2),
                        const UiToast(
                          data: UiToastData(
                            message: 'Upload paused. The network dropped.',
                            icon: UiIcons.syncProblem,
                            actionLabel: 'Retry upload',
                            onAction: _noop,
                          ),
                        ),
                        SizedBox(height: ui.space.s2),
                        UiTabs(
                          tabs: _tabs,
                          selected: _fit,
                          semanticsLabel: 'Record panels at $width dp',
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
  }
}

/// The columns 11 section 3.3 measures a control's fit in.
///

/// A stack of banners, so the tones read as one grid rather than as a column
/// the length of the page.
class _BannerColumn extends StatelessWidget {
  const _BannerColumn({required this.specimens});

  final List<(UiBannerTone, String)> specimens;

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        for (final (int index, (UiBannerTone tone, String message))
            in specimens.indexed) ...<Widget>[
          if (index > 0) SizedBox(height: ui.space.s2),
          UiBanner(message: message, tone: tone),
        ],
      ],
    );
  }
}

/// Opens the sheet the family golden captures.
///
/// Public so the golden test opens the same sheet the gallery does, rather
/// than a second one written beside it.
void openGallerySheet(BuildContext context) {
  UiSheet.show<void>(
    context: context,
    title: 'Record a reason',
    dismissLabel: 'Close the sheet',
    body: (BuildContext context) => Text(
      'Recorded in the audit history with your name and the time.',
      style: context.ui.type.body.copyWith(
        color: context.ui.color.inkSecondary,
      ),
    ),
    secondaryAction: (BuildContext context) => UiButton(
      label: 'Cancel',
      variant: UiButtonVariant.ghost,
      onPressed: () => Navigator.of(context).pop(),
    ),
    primaryAction: (BuildContext context) => UiButton(
      label: 'Save correction',
      onPressed: () => Navigator.of(context).pop(),
    ),
  ).ignore();
}

/// Opens the dialog the family golden captures.
void openGalleryDialog(BuildContext context) {
  UiDialog.show<void>(
    context: context,
    title: 'Correct classification?',
    dismissLabel: 'Close the dialog',
    body: (BuildContext context) => Text(
      'A new run replaces the results that depend on the profile. Run 2 and '
      'its evidence stay in history.',
      style: context.ui.type.body.copyWith(
        color: context.ui.color.inkSecondary,
      ),
    ),
    secondaryAction: (BuildContext context) => UiButton(
      label: 'Cancel',
      variant: UiButtonVariant.ghost,
      onPressed: () => Navigator.of(context).pop(),
    ),
    primaryAction: (BuildContext context) => UiButton(
      label: 'Correct classification',
      onPressed: () => Navigator.of(context).pop(),
    ),
  ).ignore();
}

/// A disabled control whose reason arrives through the tooltip.
class _DisabledReason extends StatelessWidget {
  const _DisabledReason();

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    return UiTooltip.reason(
      builder: (BuildContext context, ValueChanged<String> report) => Pressable(
        semanticsLabel: 'Approve record',
        disabledReason: 'Confirm label coverage before you approve this record',
        onDisabledReason: report,
        capsule: true,
        builder: (BuildContext context, Set<WidgetState> states) =>
            DecoratedBox(
              decoration: ShapeDecoration(
                shape: const StadiumBorder(),
                color: ui.color.disabledFill,
              ),
              child: ConstrainedBox(
                constraints: BoxConstraints(
                  minHeight: ui.density.controlHeight,
                ),
                child: Padding(
                  padding: EdgeInsetsDirectional.symmetric(
                    horizontal: ui.space.s5,
                  ),
                  child: Center(
                    widthFactor: 1,
                    child: Text(
                      'Approve record',
                      style: ui.type.label.copyWith(
                        color: ui.color.disabledContent,
                      ),
                    ),
                  ),
                ),
              ),
            ),
      ),
    );
  }
}

const List<(UiBannerTone, String)> _bannerSpecimens = <(UiBannerTone, String)>[
  (
    UiBannerTone.info,
    'Readings refresh every twenty seconds while a record is open.',
  ),
  (UiBannerTone.synthetic, 'Test environment. Not approved museum records.'),
  (UiBannerTone.cleared, 'Twelve records cleared in this batch.'),
  (
    UiBannerTone.needsReview,
    'Four records need review before this batch closes.',
  ),
  (
    UiBannerTone.deferred,
    'This batch is deferred until the copy stand is recalibrated.',
  ),
];

const List<(UiBannerTone, String)> _moreBannerSpecimens =
    <(UiBannerTone, String)>[
      (UiBannerTone.processing, 'Three runs are reading labels.'),
      (
        UiBannerTone.blocked,
        'Processing is blocked on a missing calibration file.',
      ),
    ];

const List<UiTab> _tabs = <UiTab>[
  UiTab(label: 'Readings'),
  UiTab(label: 'Fields'),
  UiTab(label: 'History'),
];

const List<String> _panes = <String>[
  'Two model readings, with every character that differs marked.',
  'Literal, parsed and normalised layers for each field.',
  'Every decision on this record, with the reason and the time.',
];

final List<UiMenuItem> _menuItems = <UiMenuItem>[
  const UiMenuItem(
    label: 'Copy record id',
    icon: UiIcons.copy,
    shortcut: 'Cmd C',
    onSelected: _noop,
  ),
  const UiMenuItem(
    label: 'Correct label regions',
    icon: UiIcons.correctRegions,
    onSelected: _noop,
  ),
  const UiMenuItem(
    label: 'Retry processing',
    icon: UiIcons.retry,
    shortcut: 'Cmd R',
    onSelected: null,
    disabledReason: 'Wait for the run in flight to finish',
  ),
  const UiMenuItem(
    label: 'Discard this correction',
    icon: UiIcons.remove,
    destructive: true,
    onSelected: _noop,
  ),
];

/// The gallery presses nothing. A null callback would render a control
/// disabled, which is a different specimen.
void _noop() {}
