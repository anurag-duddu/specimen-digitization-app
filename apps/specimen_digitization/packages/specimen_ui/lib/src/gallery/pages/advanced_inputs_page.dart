/// Interactive synthetic examples for advanced inputs and discovery.
library;

import 'package:flutter/widgets.dart';

import '../../../specimen_ui.dart';
import '../gallery_shell.dart';

/// The advanced forms page registered by the catalog shell.
const GalleryPage advancedInputsPage = GalleryPage(
  id: 'advanced-inputs',
  title: 'Advanced inputs',
  summary: 'Sliders, bounded dates, file states and keyboard command search.',
  builder: buildAdvancedInputsPage,
);

/// Builds local examples. No picker, transfer or production API is connected.
Widget buildAdvancedInputsPage(BuildContext context) => const _AdvancedInputs();

class _AdvancedInputs extends StatefulWidget {
  const _AdvancedInputs();

  @override
  State<_AdvancedInputs> createState() => _AdvancedInputsState();
}

class _AdvancedInputsState extends State<_AdvancedInputs> {
  double _zoom = 100;
  DateTime? _date = DateTime.utc(2026, 10, 22);
  String _command = 'Use arrow keys to move through matching commands.';
  int _fileNumber = 2;
  final List<UiUploadFile> _files = <UiUploadFile>[
    const UiUploadFile(
      id: 'one',
      name: 'Specimen-001.jpg',
      detail: 'JPEG · 2.4 MB',
      statusLabel: 'Uploading · 40%',
      status: UiFileUploadStatus.uploading,
      progress: .4,
    ),
    const UiUploadFile(
      id: 'two',
      name: 'Specimen-002.jpg',
      detail: 'JPEG · 1.8 MB',
      statusLabel: 'Upload failed',
      status: UiFileUploadStatus.error,
      errorText: 'Connection interrupted. Retry when ready.',
    ),
  ];

  void _choose() => setState(() {
    final String id = 'demo-${++_fileNumber}';
    _files.add(
      UiUploadFile(
        id: id,
        name: 'Specimen-00$_fileNumber.jpg',
        detail: 'Synthetic example · no file read',
        statusLabel: 'Ready to upload',
      ),
    );
  });

  void _retry(UiUploadFile file) => setState(() {
    _files[_files.indexOf(file)] = UiUploadFile(
      id: file.id,
      name: file.name,
      detail: file.detail,
      statusLabel: 'Uploading · 20%',
      status: UiFileUploadStatus.uploading,
      progress: .2,
      attempt: file.attempt + 1,
    );
  });

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        Text(
          'Synthetic controls only. These examples do not read files, upload data or change application records.',
          style: ui.type.bodySmall.copyWith(color: ui.color.inkSecondary),
        ),
        SizedBox(height: ui.space.s5),
        GallerySection(
          title: 'Slider · controlled value and keyboard steps',
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: <Widget>[
              UiSlider(
                label: 'Preview magnification',
                min: 50,
                max: 200,
                divisions: 30,
                value: _zoom,
                valueLabel: (double value) => '${value.round()}%',
                onChanged: (double value) => setState(() => _zoom = value),
                helpText:
                    'Use arrow keys for 5% steps; Home and End select the limits.',
              ),
              SizedBox(height: ui.space.s4),
              const UiSlider(
                label: 'Locked magnification',
                min: 50,
                max: 200,
                value: 100,
                disabledReason:
                    'Select a photograph before changing magnification.',
              ),
            ],
          ),
        ),
        GallerySection(
          title: 'Date picker · calendar and compact day list',
          child: Align(
            alignment: AlignmentDirectional.centerStart,
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 480),
              child: UiDatePicker(
                label: 'Acquisition date',
                value: _date,
                firstDate: DateTime.utc(2026, 9, 15),
                lastDate: DateTime.utc(2026, 12, 15),
                onChanged: (DateTime value) => setState(() => _date = value),
                helpText:
                    '15 September to 15 December 2026. At narrow widths the same dates appear in a scrollable list.',
              ),
            ),
          ),
        ),
        GallerySection(
          title: 'File upload · host-controlled transfer states',
          child: UiFileUpload(
            label: 'Specimen photographs',
            files: _files,
            chooseLabel: 'Add demo file',
            helpText:
                'This chooser adds a synthetic row. Drop instructions appear only when a host supplies a working drop adapter.',
            onChooseFiles: _choose,
            onRetry: _retry,
            onRemove: (UiUploadFile file) =>
                setState(() => _files.remove(file)),
          ),
        ),
        GallerySection(
          title: 'Command menu · filter, navigate, activate',
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: <Widget>[
              UiCommandMenu(
                autofocus: false,
                onDismiss: () => setState(
                  () => _command =
                      'Dismiss requested. The containing dialog owns closing and focus return.',
                ),
                commands: <UiCommand>[
                  UiCommand(
                    id: 'queue',
                    label: 'Open review queue',
                    description: 'Review specimens that need attention',
                    group: 'Navigate',
                    icon: UiIcons.queue,
                    keywords: const <String>['specimens'],
                    onSelected: () => setState(
                      () => _command = 'Open review queue selected.',
                    ),
                  ),
                  UiCommand(
                    id: 'source',
                    label: 'Browse sources',
                    group: 'Navigate',
                    icon: UiIcons.sources,
                    onSelected: () =>
                        setState(() => _command = 'Browse sources selected.'),
                  ),
                  const UiCommand(
                    id: 'export',
                    label: 'Export selected records',
                    group: 'Actions',
                    icon: UiIcons.download,
                    disabledReason: 'Select at least one record first.',
                  ),
                  UiCommand(
                    id: 'help',
                    label: 'Keyboard help',
                    group: 'Actions',
                    icon: UiIcons.keyboard,
                    keywords: const <String>['shortcuts'],
                    onSelected: () =>
                        setState(() => _command = 'Keyboard help selected.'),
                  ),
                ],
              ),
              SizedBox(height: ui.space.s3),
              Semantics(
                liveRegion: true,
                child: Text(
                  _command,
                  style: ui.type.bodySmall.copyWith(
                    color: ui.color.inkSecondary,
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
