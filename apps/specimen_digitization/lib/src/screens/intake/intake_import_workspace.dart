/// One import route; switching source retains each source's local selection.
library;

import 'package:flutter/widgets.dart';
import 'package:specimen_ui/specimen_ui.dart';
import 'bulk_intake_controller.dart';
import 'intake_source_picker.dart';

class IntakeImportWorkspace extends StatefulWidget {
  const IntakeImportWorkspace({
    super.key,
    required this.controller,
    required this.provider,
    this.initialSourceId,
  });
  final BulkIntakeController controller;
  final String provider;
  final String? initialSourceId;

  static Future<void> show({
    required BuildContext context,
    required BulkIntakeController controller,
    required String provider,
    String? initialSourceId,
  }) => showUiImportWorkspace<void>(
    context: context,
    builder: (_) => IntakeImportWorkspace(
      controller: controller,
      provider: provider,
      initialSourceId: initialSourceId,
    ),
  );

  @override
  State<IntakeImportWorkspace> createState() => _IntakeImportWorkspaceState();
}

class _IntakeImportWorkspaceState extends State<IntakeImportWorkspace> {
  static const sources = [
    UiImportSource('google_drive', 'Google Drive', UiIcons.cloudUpload),
    UiImportSource('dropbox', 'Dropbox', UiIcons.cloudUpload),
    UiImportSource('storage', 'Storage', UiIcons.source),
    UiImportSource('url', 'Import links', UiIcons.sourceImport),
  ];
  late String current = widget.provider;
  late final Set<String> visited = {current};
  final Set<String> busySources = {};

  @override
  Widget build(BuildContext context) => UiImportWorkspace(
    sources: sources,
    source: current,
    onClose: () => Navigator.of(context).pop(),
    onSourceChanged: busySources.isNotEmpty
        ? null
        : (value) => setState(() {
            current = value;
            visited.add(value);
          }),
    child: IndexedStack(
      index: sources.indexWhere((source) => source.value == current),
      sizing: StackFit.expand,
      children: [
        for (final source in sources)
          if (visited.contains(source.value))
            IntakeSourcePicker(
              key: ValueKey(source.value),
              controller: widget.controller,
              provider: source.value,
              initialSourceId: source.value == widget.provider
                  ? widget.initialSourceId
                  : null,
              active: current == source.value,
              showHeading: false,
              onBusyChanged: (busy) {
                WidgetsBinding.instance.addPostFrameCallback((_) {
                  if (mounted) {
                    setState(() {
                      busy
                          ? busySources.add(source.value)
                          : busySources.remove(source.value);
                    });
                  }
                });
              },
            )
          else
            const SizedBox.shrink(),
      ],
    ),
  );
}
