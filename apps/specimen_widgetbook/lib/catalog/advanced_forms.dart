import 'package:flutter/widgets.dart';
import 'package:specimen_ui/specimen_ui.dart';
import 'package:widgetbook/widgetbook.dart';

/// Individual advanced-input stories with real local state and inspection knobs.
List<WidgetbookComponent> get advancedFormsComponents => <WidgetbookComponent>[
  WidgetbookComponent(
    name: 'UiSlider',
    useCases: <WidgetbookUseCase>[
      WidgetbookUseCase(
        name: 'Controlled steps',
        builder: (BuildContext context) {
          final double start = context.knobs.double.slider(
            label: 'Initial value',
            min: 0,
            max: 100,
            initialValue: 40,
            divisions: 20,
          );
          final bool continuous = context.knobs.boolean(
            label: 'Continuous pointer input',
          );
          return _Example(
            description:
                'Drag, tap or use arrow keys. Home/End select limits. Horizontal arrows follow RTL. The caller accepts each proposed value.',
            child: _SliderDemo(
              key: ValueKey<String>('$start:$continuous'),
              initial: start,
              divisions: continuous ? null : 20,
              enabled: context.knobs.boolean(
                label: 'Enabled',
                initialValue: true,
              ),
              error: context.knobs.boolean(label: 'Validation error'),
            ),
          );
        },
      ),
      WidgetbookUseCase(
        name: 'Disabled with reason',
        builder: (_) => const _Example(
          description:
              'The disabled input retains its value and reason without pointer, keyboard or semantic adjustment actions.',
          child: UiSlider(
            label: 'Preview magnification',
            value: 100,
            min: 50,
            max: 200,
            disabledReason:
                'Select a photograph before changing magnification.',
          ),
        ),
      ),
    ],
  ),
  WidgetbookComponent(
    name: 'UiDatePicker',
    useCases: <WidgetbookUseCase>[
      WidgetbookUseCase(
        name: 'Bounded calendar',
        builder: (BuildContext context) => _Example(
          description:
              'Inclusive date bounds: 15 September–15 December 2026. Below seven 48 dp targets the calendar becomes a scrolling day list. Arrow, Home/End and Page keys move focus; Enter selects.',
          child: _DateDemo(
            enabled: context.knobs.boolean(
              label: 'Enabled',
              initialValue: true,
            ),
            error: context.knobs.boolean(label: 'Validation error'),
            sundayFirst: context.knobs.boolean(label: 'Sunday first'),
          ),
        ),
      ),
      WidgetbookUseCase(
        name: 'Empty and single allowed date',
        builder: (_) => const _Example(
          description:
              'An initially empty, bounded selection. Dates outside 22 October cannot be selected and both month navigation actions are disabled.',
          child: _SingleDateDemo(),
        ),
      ),
    ],
  ),
  WidgetbookComponent(
    name: 'UiFileUpload',
    useCases: <WidgetbookUseCase>[
      WidgetbookUseCase(
        name: 'Progress fill and file type',
        builder: (_) => const _Example(
          description:
              'Reported progress fills the row, with the same retry, remove and file identity contracts as the separate bar.',
          child: _UploadDemo(
            enabled: true,
            choosing: false,
            progress: .45,
            error: false,
            fill: true,
          ),
        ),
      ),

      WidgetbookUseCase(
        name: 'Transfer and recovery states',
        builder: (BuildContext context) => _Example(
          description:
              'Synthetic presentation only. The host supplies file IDs, status, real progress and retry attempts. Transfer completion does not imply specimen processing completed.',
          child: _UploadDemo(
            enabled: context.knobs.boolean(
              label: 'Enabled',
              initialValue: true,
            ),
            choosing: context.knobs.boolean(label: 'Chooser busy'),
            progress: context.knobs.double.slider(
              label: 'Reported progress',
              min: 0,
              max: 1,
              initialValue: .4,
              divisions: 20,
            ),
            error: context.knobs.boolean(label: 'Collection error'),
            fill: context.knobs.boolean(label: 'Progress fill'),
          ),
        ),
      ),
      WidgetbookUseCase(
        name: 'Drop adapter contract',
        builder: (_) => const _Example(
          description:
              'Drag this synthetic file token into the target, or choose it by keyboard. This Flutter DragTarget demonstrates the adapter boundary; it does not read OS files or contact a server.',
          child: _DropDemo(),
        ),
      ),
    ],
  ),
  WidgetbookComponent(
    name: 'UiCommandMenu',
    useCases: <WidgetbookUseCase>[
      WidgetbookUseCase(
        name: 'Grouped search and activation',
        builder: (BuildContext context) => _Example(
          description:
              'Type labels, descriptions or keywords. Arrows focus enabled results; Enter activates; Escape asks the host to close. Disabled items retain their reason.',
          child: _CommandDemo(
            showDisabled: context.knobs.boolean(
              label: 'Show unavailable command',
              initialValue: true,
            ),
            searchHint: context.knobs.string(
              label: 'Search placeholder',
              initialValue: 'Search commands…',
            ),
          ),
        ),
      ),
      WidgetbookUseCase(
        name: 'Empty results',
        builder: (_) => _Example(
          description:
              'The no-results message is announced as a live region. This is an intentionally empty command collection.',
          child: UiCommandMenu(
            autofocus: false,
            commands: const <UiCommand>[],
            onDismiss: () {},
          ),
        ),
      ),
    ],
  ),
];

class _Example extends StatelessWidget {
  const _Example({required this.description, required this.child});
  final String description;
  final Widget child;
  @override
  Widget build(BuildContext context) => Align(
    alignment: AlignmentDirectional.topStart,
    child: ConstrainedBox(
      constraints: const BoxConstraints(maxWidth: 620),
      child: SingleChildScrollView(
        child: Padding(
          padding: EdgeInsets.all(context.ui.space.s4),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: <Widget>[
              Text(
                description,
                style: context.ui.type.bodySmall.copyWith(
                  color: context.ui.color.inkSecondary,
                ),
              ),
              SizedBox(height: context.ui.space.s5),
              child,
            ],
          ),
        ),
      ),
    ),
  );
}

class _SliderDemo extends StatefulWidget {
  const _SliderDemo({
    super.key,
    required this.initial,
    required this.divisions,
    required this.enabled,
    required this.error,
  });
  final double initial;
  final int? divisions;
  final bool enabled;
  final bool error;
  @override
  State<_SliderDemo> createState() => _SliderDemoState();
}

class _SliderDemoState extends State<_SliderDemo> {
  late double _value = widget.initial;
  @override
  Widget build(BuildContext context) => UiSlider(
    label: 'Preview magnification',
    min: 0,
    max: 100,
    value: _value,
    divisions: widget.divisions,
    valueLabel: (double value) => '${value.round()}%',
    onChanged: widget.enabled
        ? (double value) => setState(() => _value = value)
        : null,
    helpText: 'Use 5% steps to inspect image details.',
    errorText: widget.error ? 'Choose an allowed magnification.' : null,
    disabledReason: widget.enabled ? null : 'Select a photograph first.',
  );
}

class _DateDemo extends StatefulWidget {
  const _DateDemo({
    required this.enabled,
    required this.error,
    required this.sundayFirst,
  });
  final bool enabled;
  final bool error;
  final bool sundayFirst;
  @override
  State<_DateDemo> createState() => _DateDemoState();
}

class _DateDemoState extends State<_DateDemo> {
  DateTime? _value = DateTime.utc(2026, 10, 22);
  @override
  Widget build(BuildContext context) => UiDatePicker(
    label: 'Acquisition date',
    value: _value,
    firstDate: DateTime.utc(2026, 9, 15),
    lastDate: DateTime.utc(2026, 12, 15),
    firstDayOfWeek: widget.sundayFirst ? DateTime.sunday : DateTime.monday,
    onChanged: widget.enabled
        ? (DateTime value) => setState(() => _value = value)
        : null,
    helpText: 'Choose the date recorded in the accession ledger.',
    errorText: widget.error ? 'Confirm the date against the ledger.' : null,
    disabledReason: widget.enabled
        ? null
        : 'Date editing is unavailable for this record.',
  );
}

class _SingleDateDemo extends StatefulWidget {
  const _SingleDateDemo();
  @override
  State<_SingleDateDemo> createState() => _SingleDateDemoState();
}

class _SingleDateDemoState extends State<_SingleDateDemo> {
  DateTime? _value;
  @override
  Widget build(BuildContext context) => UiDatePicker(
    label: 'Available date',
    value: _value,
    firstDate: DateTime.utc(2026, 10, 22),
    lastDate: DateTime.utc(2026, 10, 22),
    onChanged: (DateTime value) => setState(() => _value = value),
  );
}

class _UploadDemo extends StatefulWidget {
  const _UploadDemo({
    required this.enabled,
    required this.choosing,
    required this.progress,
    required this.error,
    this.fill = false,
  });
  final bool enabled;
  final bool choosing;
  final double progress;
  final bool error;
  final bool fill;
  @override
  State<_UploadDemo> createState() => _UploadDemoState();
}

class _UploadDemoState extends State<_UploadDemo> {
  final Set<String> _removed = <String>{};
  final List<UiUploadFile> _added = <UiUploadFile>[];
  bool _retried = false;
  @override
  Widget build(BuildContext context) => UiFileUpload(
    label: 'Specimen photographs',
    progressStyle: widget.fill
        ? UiFileUploadProgressStyle.fill
        : UiFileUploadProgressStyle.bar,
    enabled: widget.enabled,
    isChoosing: widget.choosing,
    chooseLabel: 'Add synthetic file',
    disabledReason: widget.enabled ? null : 'Sign in to add or change files.',
    errorText: widget.error
        ? 'A photograph exceeds the collection size limit.'
        : null,
    helpText: 'JPEG and PNG. These rows are local examples.',
    files: <UiUploadFile>[
      UiUploadFile(
        id: 'uploading',
        name: 'Specimen-001.jpg',
        leading: const UiIcon(UiIcons.record),
        detail: 'JPEG · 2.4 MB',
        statusLabel: 'Uploading · ${(widget.progress * 100).round()}%',
        status: UiFileUploadStatus.uploading,
        progress: widget.progress,
        attempt: (widget.progress * 1000).round(),
      ),
      UiUploadFile(
        id: 'failed',
        name: 'Specimen-002.jpg',
        detail: 'JPEG · 1.8 MB',
        statusLabel: _retried ? 'Ready to retry' : 'Transfer failed',
        status: _retried ? UiFileUploadStatus.queued : UiFileUploadStatus.error,
        errorText: 'Connection interrupted. Retry when ready.',
      ),
      const UiUploadFile(
        id: 'complete',
        name: 'Specimen-003.jpg',
        statusLabel: 'Transfer complete',
        status: UiFileUploadStatus.complete,
      ),
      ..._added,
    ].where((UiUploadFile file) => !_removed.contains(file.id)).toList(),
    onChooseFiles: () => setState(
      () => _added.add(
        UiUploadFile(
          id: 'new-${_added.length}',
          name: 'Demo-${_added.length + 1}.jpg',
          statusLabel: 'Ready to upload',
        ),
      ),
    ),
    onRemove: (UiUploadFile file) => setState(() => _removed.add(file.id)),
    onRetry: (_) => setState(() => _retried = true),
  );
}

class _DropDemo extends StatefulWidget {
  const _DropDemo();
  @override
  State<_DropDemo> createState() => _DropDemoState();
}

class _DropDemoState extends State<_DropDemo> {
  bool _dragging = false;
  final List<UiUploadFile> _files = <UiUploadFile>[];
  void _add() => setState(
    () => _files.add(
      UiUploadFile(
        id: 'drop-${_files.length}',
        name: 'Synthetic-image.jpg',
        statusLabel: 'Ready to upload',
      ),
    ),
  );
  @override
  Widget build(BuildContext context) {
    final Widget token = Container(
      padding: EdgeInsets.all(context.ui.space.s3),
      decoration: BoxDecoration(
        color: context.ui.color.paper,
        border: Border.all(color: context.ui.color.boundary),
        borderRadius: BorderRadius.circular(context.ui.shape.inner),
      ),
      child: Text('Drag demo file', style: context.ui.defaultTextStyle),
    );
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        Align(
          alignment: AlignmentDirectional.centerStart,
          child: Draggable<String>(
            data: 'synthetic-file',
            feedback: token,
            child: token,
          ),
        ),
        SizedBox(height: context.ui.space.s4),
        UiFileUpload(
          label: 'Drop adapter example',
          files: _files,
          chooseLabel: 'Choose demo file',
          onChooseFiles: _add,
          dropLabel: 'Drop the synthetic file here',
          dragActive: _dragging,
          dropTargetBuilder: (BuildContext context, Widget child) =>
              DragTarget<String>(
                onWillAcceptWithDetails: (DragTargetDetails<String> details) {
                  final bool accepted = details.data == 'synthetic-file';
                  setState(() => _dragging = accepted);
                  return accepted;
                },
                onLeave: (_) => setState(() => _dragging = false),
                onAcceptWithDetails: (_) {
                  setState(() => _dragging = false);
                  _add();
                },
                builder: (_, _, _) => child,
              ),
          onRemove: (UiUploadFile file) => setState(() => _files.remove(file)),
        ),
      ],
    );
  }
}

class _CommandDemo extends StatefulWidget {
  const _CommandDemo({required this.showDisabled, required this.searchHint});
  final bool showDisabled;
  final String searchHint;
  @override
  State<_CommandDemo> createState() => _CommandDemoState();
}

class _CommandDemoState extends State<_CommandDemo> {
  String _last = 'No command selected.';
  @override
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: <Widget>[
      UiCommandMenu(
        autofocus: false,
        hintText: widget.searchHint,
        onDismiss: () => setState(() => _last = 'Dismiss requested.'),
        commands: <UiCommand>[
          UiCommand(
            id: 'queue',
            label: 'Open review queue',
            description: 'Review specimens that need attention',
            group: 'Navigate',
            icon: UiIcons.queue,
            keywords: const <String>['specimens'],
            onSelected: () =>
                setState(() => _last = 'Open review queue selected.'),
          ),
          UiCommand(
            id: 'sources',
            label: 'Browse sources',
            group: 'Navigate',
            icon: UiIcons.sources,
            onSelected: () =>
                setState(() => _last = 'Browse sources selected.'),
          ),
          if (widget.showDisabled)
            const UiCommand(
              id: 'export',
              label: 'Export selected records',
              group: 'Actions',
              icon: UiIcons.download,
              disabledReason: 'Select a record before exporting.',
            ),
          UiCommand(
            id: 'keyboard',
            label: 'Keyboard help',
            group: 'Actions',
            icon: UiIcons.keyboard,
            keywords: const <String>['shortcuts'],
            onSelected: () => setState(() => _last = 'Keyboard help selected.'),
          ),
        ],
      ),
      SizedBox(height: context.ui.space.s3),
      Semantics(
        liveRegion: true,
        child: Text(_last, style: context.ui.type.bodySmall),
      ),
    ],
  );
}
