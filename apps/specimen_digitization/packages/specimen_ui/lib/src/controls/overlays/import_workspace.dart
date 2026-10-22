/// A stable source browser around a private photo batch.
library;

import 'package:flutter/widgets.dart';
import '../../foundation/icons.dart';
import '../../foundation/theme.dart';
import '../actions/icon_button.dart';
import '../data/list_row.dart';
import '../inputs/select.dart';
import 'popover_menu.dart';

/// A destination in the import source navigation.
class UiImportSource {
  /// Uses a stable [value] for selection and a readable [label].
  const UiImportSource(this.value, this.label, this.icon);

  /// Stable source identity.
  final String value;

  /// Human-readable source name.
  final String label;

  /// The source's design-system glyph.
  final IconSpec icon;
}

/// Shared desktop rail / compact selector and a bounded source workspace.
/// The source body owns its scrolling file area and persistent action footer.
class UiImportWorkspace extends StatelessWidget {
  /// Composes source navigation around a bounded file browser.
  const UiImportWorkspace({
    super.key,
    required this.sources,
    required this.source,
    required this.onSourceChanged,
    required this.onClose,
    required this.child,
  });

  /// Available acquisition sources.
  final List<UiImportSource> sources;

  /// The currently visible source.
  final String source;

  /// Changes source; null while an exclusive action is pending.
  final ValueChanged<String>? onSourceChanged;

  /// Dismisses the workspace while retaining the private draft.
  final VoidCallback onClose;

  /// Source content, including its scrolling area and action footer.
  final Widget child;

  @override
  Widget build(BuildContext context) {
    final ui = context.ui;
    return LayoutBuilder(
      builder: (context, constraints) {
        final rail =
            constraints.maxWidth >= ui.space.paneDetailMin * 2 &&
            MediaQuery.textScalerOf(context).scale(1) < 1.5;
        final divider = BorderSide(color: ui.color.boundary);
        final short = constraints.maxHeight < ui.space.paneDetailMin;
        return SizedBox(
          width: double.infinity,
          height: constraints.maxHeight.clamp(
            0,
            ui.space.importWorkspaceHeight,
          ),
          child: Column(
            children: [
              Padding(
                padding: EdgeInsets.fromLTRB(
                  ui.space.s4,
                  ui.space.s2,
                  ui.space.s2,
                  ui.space.s2,
                ),
                child: Row(
                  children: [
                    Expanded(
                      child: Semantics(
                        header: true,
                        child: Text(
                          short
                              ? sources
                                    .firstWhere(
                                      (option) => option.value == source,
                                    )
                                    .label
                              : 'Add photos',
                          style: ui.type.title,
                        ),
                      ),
                    ),
                    if (short)
                      UiMenuTrigger(
                        semanticsLabel: 'Change photo source',
                        items: [
                          for (final option in sources)
                            UiMenuItem(
                              label: option.label,
                              onSelected: onSourceChanged == null
                                  ? null
                                  : () => onSourceChanged!(option.value),
                            ),
                        ],
                      ),
                    UiIconButton(
                      icon: UiIcons.close,
                      semanticsLabel: 'Close photo sources',
                      onPressed: onClose,
                    ),
                  ],
                ),
              ),
              Expanded(
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    if (rail)
                      Container(
                        width: ui.space.rail * 2 + ui.space.s8,
                        decoration: BoxDecoration(
                          border: Border(right: divider, top: divider),
                        ),
                        child: ListView(
                          padding: EdgeInsets.all(ui.space.s2),
                          children: [
                            for (final option in sources)
                              UiListRow(
                                title: option.label,
                                leading: UiIcon(option.icon),
                                selected: source == option.value,
                                onPressed: onSourceChanged == null
                                    ? null
                                    : () => onSourceChanged!(option.value),
                              ),
                          ],
                        ),
                      ),
                    Expanded(
                      child: Container(
                        decoration: BoxDecoration(border: Border(top: divider)),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.stretch,
                          children: [
                            if (!rail && !short)
                              Padding(
                                padding: EdgeInsets.all(ui.space.s4),
                                child: UiSelect<String>(
                                  label: 'Photo source',
                                  placeholder: 'Choose a source',
                                  value: source,
                                  options: [
                                    for (final option in sources)
                                      UiSelectOption(
                                        value: option.value,
                                        label: option.label,
                                      ),
                                  ],
                                  onChanged: onSourceChanged,
                                ),
                              ),
                            Expanded(child: child),
                          ],
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        );
      },
    );
  }
}
