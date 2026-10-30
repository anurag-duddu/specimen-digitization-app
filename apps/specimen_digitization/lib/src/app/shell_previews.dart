/// Isolated, interactive previews for the shell navigation.
library;

import 'package:flutter/widget_previews.dart';
import 'package:flutter/widgets.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../theme/app_theme.dart';
import '../workspace.dart';
import 'shell.dart';

PreviewThemeData shellPreviewThemes() => PreviewThemeData(
  materialLight: AppTheme.light(),
  materialDark: AppTheme.dark(),
);

@Preview(name: 'Primary rail', group: 'Shell', theme: shellPreviewThemes)
Widget shellNavigationPreview() {
  WorkspaceDestination selected = WorkspaceDestination.queue;
  // The same capability-aware primary rail used by the application shell.
  return StatefulBuilder(
    builder: (BuildContext context, StateSetter setState) => UiScaffold(
      nav: UiRail(
        destinations: AppShell.destinations,
        currentIndex: selected.index,
        semanticsLabel: AppShell.navigationLabel,
        onSelect: (int index) =>
            setState(() => selected = WorkspaceDestination.values[index]),
      ),
      body: const SizedBox.expand(),
    ),
  );
}
