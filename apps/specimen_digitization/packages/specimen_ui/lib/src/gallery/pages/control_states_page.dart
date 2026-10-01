/// Current runtime control states, separate from optional decorative studies.
library;

import 'package:flutter/widgets.dart';

import '../../../specimen_ui.dart';
import '../gallery_shell.dart';

/// The live shared-control acceptance page.
const controlStatesPage = GalleryPage(
  id: 'control-states',
  title: 'Current control states',
  summary:
      'Runtime defaults. Keyboard, hover, selected, busy and unavailable states remain interactive.',
  builder: buildControlStatesPage,
  maxGlassPanes: 0,
);

/// Builds the current-default interactive state gallery.
Widget buildControlStatesPage(BuildContext context) =>
    const UiControlStatesPage();

/// Review surface for the current shared controls, using the inherited theme.
class UiControlStatesPage extends StatefulWidget {
  /// Creates the state review surface.
  const UiControlStatesPage({super.key});

  @override
  State<UiControlStatesPage> createState() => _UiControlStatesPageState();
}

class _UiControlStatesPageState extends State<UiControlStatesPage> {
  final _hover = WidgetStatesController({WidgetState.hovered});
  final _pressed = WidgetStatesController({WidgetState.pressed});
  final _focus = FocusNode(debugLabel: 'Focused command');
  final _tabs = ValueNotifier(0);
  final _search = TextEditingController(text: 'FMNH 118402');
  final _readOnly = TextEditingController(
    text: 'Original label text, selectable evidence',
  );
  final _reason = TextEditingController(
    text: 'Corrected from the source photograph.',
  );
  int? _choice = 1;
  bool _checked = true;
  bool _working = false;
  String _lastAction = 'No command submitted';

  @override
  void dispose() {
    _hover.dispose();
    _pressed.dispose();
    _focus.dispose();
    _tabs.dispose();
    _search.dispose();
    _readOnly.dispose();
    _reason.dispose();
    super.dispose();
  }

  void _action(String label) => setState(() => _lastAction = label);

  @override
  Widget build(BuildContext context) {
    final ui = context.ui;
    Widget group(String title, List<Widget> children) => Padding(
      padding: EdgeInsets.only(bottom: ui.space.s6),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(title, style: ui.type.title.copyWith(color: ui.color.ink)),
          SizedBox(height: ui.space.s2),
          Wrap(
            spacing: ui.space.s3,
            runSpacing: ui.space.s2,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: children,
          ),
        ],
      ),
    );
    Widget example(String label, Widget child) => Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          label,
          style: ui.type.labelSmall.copyWith(color: ui.color.inkSecondary),
        ),
        SizedBox(height: ui.space.s1),
        child,
      ],
    );
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'Control state review',
          style: ui.type.titleLarge.copyWith(color: ui.color.ink),
        ),
        SizedBox(height: ui.space.s2),
        Text(
          'Current runtime defaults. Use Tab, arrows and Enter or Space. Unavailable commands explain why; synthetic actions update the receipt below.',
          style: ui.type.body.copyWith(color: ui.color.inkSecondary),
        ),
        SizedBox(height: ui.space.s6),
        group('Commands', [
          example(
            'Rest',
            UiButton(
              label: 'Save correction',
              onPressed: () => _action('Saved correction'),
            ),
          ),
          example(
            'Hover',
            UiButton(
              label: 'Save correction',
              statesController: _hover,
              onPressed: () => _action('Hovered command activated'),
            ),
          ),
          example(
            'Pressed',
            UiButton(
              label: 'Save correction',
              statesController: _pressed,
              onPressed: () => _action('Pressed command activated'),
            ),
          ),
          example(
            'Keyboard focus',
            UiButton(
              label: 'Review source',
              size: UiSize.sm,
              variant: UiButtonVariant.secondary,
              focusNode: _focus,
              onPressed: () => _action('Reviewed source'),
            ),
          ),
          example(
            'Unavailable',
            const UiButton(
              label: 'Approve record',
              disabledReason:
                  'Confirm label coverage before approving this record.',
            ),
          ),
          example(
            'Busy',
            const TickerMode(
              enabled: false,
              child: UiButton(
                label: 'Save correction',
                busyLabel: 'Saving correction',
                loading: true,
              ),
            ),
          ),
        ]),
        group('Selection and navigation', [
          example(
            'Selected icon',
            UiIconButton(
              icon: UiIcons.rotateView,
              semanticsLabel: 'Rotation mode selected',
              current: true,
              onPressed: () => _action('Rotation mode'),
            ),
          ),
          example(
            'Inactive icon',
            UiIconButton(
              icon: UiIcons.rotateView,
              semanticsLabel: 'Rotation mode inactive',
              onPressed: () => _action('Rotation available'),
            ),
          ),
          example(
            'Unavailable selected',
            const UiIconButton(
              icon: UiIcons.rotateView,
              semanticsLabel: 'Rotation mode unavailable',
              current: true,
              disabledReason: 'Finish saving before changing rotation.',
            ),
          ),
          example(
            'Workspace destinations',
            UiTabs(
              tabs: const [
                UiTab(label: 'Queue'),
                UiTab(label: 'Intake'),
              ],
              selected: _tabs,
              semanticsLabel: 'Workspace destinations',
              onSelected: (value) => _action(
                value == 0 ? 'Queue destination' : 'Intake destination',
              ),
            ),
          ),
        ]),
        group('Value choices', [
          UiChoiceGroup<int>(
            label: 'Review state',
            choices: const [
              UiChoice(value: 1, label: 'Needs review'),
              UiChoice(value: 2, label: 'Approved'),
              UiChoice(value: 3, label: 'Processing'),
            ],
            value: _choice,
            onChanged: (value) => setState(() => _choice = value),
          ),
        ]),
        LayoutBuilder(
          builder: (context, constraints) {
            final metrics = UiLayoutMetrics.fromConstraints(
              constraints,
              textScaler: MediaQuery.textScalerOf(context),
            );
            final columns = metrics.columns(maxColumns: 2);
            final width =
                (constraints.maxWidth - ui.space.s2 * (columns - 1)) / columns;
            return group('Fields', [
              SizedBox(
                width: width,
                child: UiSearchField(
                  label: 'Exact specimen ID',
                  clearLabel: 'Clear specimen ID',
                  controller: _search,
                  onChanged: (_) {},
                ),
              ),
              SizedBox(
                width: width,
                child: UiField(
                  label: 'Correction reason',
                  controller: _reason,
                  errorText: 'Add the source detail that supports this change.',
                ),
              ),
              SizedBox(
                width: width,
                child: UiField(
                  label: 'Original reading',
                  controller: _readOnly,
                  readOnly: true,
                  clearLabel: 'Clear original reading',
                  helpText:
                      'Read-only evidence. Select and copy the original text.',
                ),
              ),
              SizedBox(
                width: width,
                child: const UiField(
                  label: 'Unavailable field',
                  enabled: false,
                  disabledReason: 'You have read access to this record.',
                  helpText: 'You have read access to this record.',
                ),
              ),
            ]);
          },
        ),
        group('Checks, status and progress', [
          UiCheckbox(
            label: 'Include this record',
            value: _checked,
            onChanged: (value) => setState(() => _checked = value),
          ),
          const UiChip(label: 'Saved', leading: UiIcon(UiIcons.check)),
          const UiChip(
            label: 'Needs attention',
            leading: UiIcon(UiIcons.blocked),
          ),
          const SizedBox(
            width: 180,
            child: UiProgress.bar(semanticsLabel: 'Upload progress', value: .6),
          ),
        ]),
        group('Busy transition', [
          UiButton(
            label: 'Save',
            busyLabel: 'Saving correction',
            loading: _working,
            onPressed: () => setState(() => _working = true),
          ),
          UiButton(
            label: 'Finish synthetic save',
            variant: UiButtonVariant.ghost,
            onPressed: () => setState(() {
              _working = false;
              _lastAction = 'Synthetic save finished';
            }),
          ),
          UiButton(
            label: 'Focus small command',
            variant: UiButtonVariant.ghost,
            onPressed: _focus.requestFocus,
          ),
        ]),
        const UiHairline(),
        SizedBox(height: ui.space.s3),
        Semantics(
          liveRegion: true,
          child: Text(
            'Interaction receipt: $_lastAction',
            style: ui.type.body.copyWith(color: ui.color.inkSecondary),
          ),
        ),
      ],
    );
  }
}
