/// The primitives in every state (10 section 6).
///
/// `Pressable` at rest, hovered, focused, pressed and disabled with a reason;
/// the three glass levels; the focus ring; a popover; and the two modal
/// routes. The states that need a gesture are forced with a states controller
/// so the golden holds them all at once.
library;

import 'package:flutter/widgets.dart';

import '../../../specimen_ui.dart';
import '../gallery_shell.dart';

/// Builds the primitives page.
Widget buildPrimitivesPage(BuildContext context) => const _PrimitivesPage();

class _PrimitivesPage extends StatefulWidget {
  const _PrimitivesPage();

  @override
  State<_PrimitivesPage> createState() => _PrimitivesPageState();
}

class _PrimitivesPageState extends State<_PrimitivesPage> {
  final PopoverController _popover = PopoverController();
  final Map<WidgetState, WidgetStatesController> _forced =
      <WidgetState, WidgetStatesController>{
        for (final WidgetState state in <WidgetState>[
          WidgetState.hovered,
          WidgetState.pressed,
          WidgetState.selected,
        ])
          state: WidgetStatesController(<WidgetState>{state}),
      };

  @override
  void dispose() {
    _popover.dispose();
    for (final WidgetStatesController controller in _forced.values) {
      controller.dispose();
    }
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        GallerySection(
          title: 'Pressable, every state',
          child: Wrap(
            spacing: ui.space.s4,
            runSpacing: ui.space.s4,
            children: <Widget>[
              const GallerySpecimen(
                label: 'rest',
                child: UiButton(label: 'Approve record', onPressed: _noop),
              ),
              GallerySpecimen(
                label: 'hovered',
                child: _Forced(
                  controller: _forced[WidgetState.hovered]!,
                  label: 'Approve record',
                ),
              ),
              GallerySpecimen(
                label: 'pressed',
                child: _Forced(
                  controller: _forced[WidgetState.pressed]!,
                  label: 'Approve record',
                ),
              ),
              const GallerySpecimen(
                label: 'focused',
                child: _FocusedSpecimen(),
              ),
              const GallerySpecimen(
                label: 'disabled with a reason',
                note: 'the reason is on the semantics hint',
                child: UiButton(
                  label: 'Approve record',
                  disabledReason:
                      'Confirm label coverage before you approve this record.',
                ),
              ),
            ],
          ),
        ),
        GallerySection(
          title: 'Button variants',
          child: Wrap(
            spacing: ui.space.s4,
            runSpacing: ui.space.s4,
            children: <Widget>[
              for (final UiButtonVariant variant in UiButtonVariant.values)
                GallerySpecimen(
                  label: variant.name,
                  child: UiButton(
                    label: 'Save and revalidate',
                    variant: variant,
                    onPressed: _noop,
                  ),
                ),
            ],
          ),
        ),
        GallerySection(
          title: 'Surfaces',
          child: Wrap(
            spacing: ui.space.s4,
            runSpacing: ui.space.s4,
            children: <Widget>[
              for (final MapEntry<String, UiGlassStyle> level
                  in ui.glass.all.entries)
                GallerySpecimen(
                  label: 'glass.${level.key}',
                  child: SizedBox(
                    width: 180,
                    height: 90,
                    child: GlassSurface(
                      level: level.value.level,
                      padding: EdgeInsetsDirectional.all(ui.space.s3),
                      child: Text('One pane', style: ui.type.title),
                    ),
                  ),
                ),
              for (final SurfaceRole role in SurfaceRole.values)
                GallerySpecimen(
                  label: 'surface.${role.name}',
                  child: SizedBox(
                    width: 180,
                    height: 90,
                    child: Surface(
                      role: role,
                      hairline: true,
                      padding: EdgeInsetsDirectional.all(ui.space.s3),
                      child: Text('Solid', style: ui.type.title),
                    ),
                  ),
                ),
            ],
          ),
        ),
        GallerySection(
          title: 'FocusRing',
          child: Wrap(
            spacing: ui.space.s6,
            runSpacing: ui.space.s6,
            children: <Widget>[
              GallerySpecimen(
                label: 'on radius.field',
                child: Padding(
                  padding: EdgeInsetsDirectional.all(ui.space.s2),
                  child: FocusRing(
                    visible: true,
                    radius: ui.shape.field,
                    child: SizedBox(
                      width: 160,
                      height: 48,
                      child: Surface(
                        radius: ui.shape.field,
                        boundary: true,
                        child: const SizedBox.shrink(),
                      ),
                    ),
                  ),
                ),
              ),
              GallerySpecimen(
                label: 'on a capsule',
                child: Padding(
                  padding: EdgeInsetsDirectional.all(ui.space.s2),
                  child: const FocusRing(
                    visible: true,
                    shape: FocusRingShape.stadium,
                    child: SizedBox(
                      width: 160,
                      height: 48,
                      child: Surface(
                        capsule: true,
                        boundary: true,
                        child: SizedBox.shrink(),
                      ),
                    ),
                  ),
                ),
              ),
            ],
          ),
        ),
        GallerySection(
          title: 'Overlays',
          child: Wrap(
            spacing: ui.space.s4,
            runSpacing: ui.space.s4,
            children: <Widget>[
              Popover(
                controller: _popover,
                semanticsLabel: 'Collection menu',
                overlayBuilder: (BuildContext context) => Padding(
                  padding: EdgeInsetsDirectional.all(ui.space.s3),
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: <Widget>[
                      Text('Insects', style: ui.type.body),
                      Text('Herbarium', style: ui.type.body),
                    ],
                  ),
                ),
                child: UiButton(
                  label: 'Open a popover',
                  variant: UiButtonVariant.secondary,
                  onPressed: _popover.toggle,
                ),
              ),
              UiButton(
                label: 'Open a sheet',
                variant: UiButtonVariant.secondary,
                onPressed: () => _openModal(context, sheet: true),
              ),
              UiButton(
                label: 'Open a dialog',
                variant: UiButtonVariant.secondary,
                onPressed: () => _openModal(context, sheet: false),
              ),
            ],
          ),
        ),
        GallerySection(
          title: 'FieldCore',
          child: SizedBox(
            width: 320,
            child: Surface(
              radius: ui.shape.field,
              boundary: true,
              padding: EdgeInsetsDirectional.symmetric(
                horizontal: ui.space.s3,
                vertical: ui.space.s2,
              ),
              child: const FieldCore(
                semanticsLabel: 'Reason',
                hintText: 'Why this changed',
              ),
            ),
          ),
        ),
        GallerySection(
          title: 'Density',
          child: Text(
            'Resolved from the last pointer event: '
            '${ui.density.mode.name}, rows '
            '${ui.density.rowHeight.toStringAsFixed(0)} dp, controls '
            '${ui.density.controlHeight.toStringAsFixed(0)} dp, hit box '
            '${UiDensity.hitBox.toStringAsFixed(0)} dp',
            style: ui.type.bodySmall.copyWith(color: ui.color.inkSecondary),
          ),
        ),
      ],
    );
  }

  void _openModal(BuildContext context, {required bool sheet}) {
    final UiThemeData ui = context.ui;
    final Future<void> opened = sheet
        ? showUiSheet<void>(
            context: context,
            semanticsLabel: 'Record a reason',
            dismissLabel: 'Close the sheet',
            builder: (BuildContext context) => _modalBody(ui, 'A sheet'),
          )
        : showUiDialog<void>(
            context: context,
            semanticsLabel: 'Record a reason',
            dismissLabel: 'Close the dialog',
            builder: (BuildContext context) => _modalBody(ui, 'A dialog'),
          );
    opened.ignore();
  }

  Widget _modalBody(UiThemeData ui, String title) => Padding(
    padding: EdgeInsetsDirectional.all(ui.space.s6),
    child: Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        Text(title, style: ui.type.titleLarge),
        SizedBox(height: ui.space.s2),
        Text(
          'Glass at the modal level, over the scrim.',
          style: ui.type.body.copyWith(color: ui.color.inkSecondary),
        ),
      ],
    ),
  );
}

/// A pressable held in one state, so a golden can show a state a gesture
/// would otherwise be needed for.
class _Forced extends StatelessWidget {
  const _Forced({required this.controller, required this.label});

  final WidgetStatesController controller;
  final String label;

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    return Pressable(
      semanticsLabel: label,
      onPressed: _noop,
      capsule: true,
      statesController: controller,
      builder: (BuildContext context, Set<WidgetState> states) => DecoratedBox(
        decoration: ShapeDecoration(
          shape: const StadiumBorder(),
          color: ui.color.ink,
        ),
        child: ConstrainedBox(
          constraints: BoxConstraints(minHeight: ui.density.controlHeight),
          child: Padding(
            padding: EdgeInsetsDirectional.symmetric(horizontal: ui.space.s5),
            child: Center(
              widthFactor: 1,
              child: Text(
                label,
                style: ui.type.label.copyWith(color: ui.color.paper),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// A pressable that takes focus on the first frame, so the ring is in the
/// golden without the test having to press Tab.
class _FocusedSpecimen extends StatelessWidget {
  const _FocusedSpecimen();

  @override
  Widget build(BuildContext context) => const UiButton(
    label: 'Approve record',
    onPressed: _noop,
    autofocus: true,
  );
}

/// The gallery presses nothing. A null callback would render the control
/// disabled, which is a different specimen.
void _noop() {}
