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

@Preview(name: 'Sidebar navigation', group: 'Shell', theme: shellPreviewThemes)
Widget shellNavigationPreview() {
  WorkspaceDestination selected = WorkspaceDestination.queue;
  return StatefulBuilder(
    builder: (BuildContext context, StateSetter setState) => UiScaffold(
      body: Padding(
        padding: EdgeInsets.all(context.ui.space.s4),
        child: Align(
          alignment: AlignmentDirectional.topStart,
          child: ShellSidebarNavigation(
            destination: selected,
            onSelect: (WorkspaceDestination next) =>
                setState(() => selected = next),
          ),
        ),
      ),
    ),
  );
}
