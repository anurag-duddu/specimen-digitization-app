import 'package:flutter/widget_previews.dart';
import 'package:flutter/widgets.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../../theme/app_theme.dart';
import '../../widgets/adaptive_form.dart';
import 'capture_card.dart';

PreviewThemeData intakePreviewThemes() => PreviewThemeData(
  materialLight: AppTheme.light(),
  materialDark: AppTheme.dark(),
);

void choosePreviewFiles() {}

@Preview(name: 'Web file intake', group: 'Intake', theme: intakePreviewThemes)
Widget intakeFilePreview() => SizedBox(
  width: UiSpace.standard.readingMax,
  height: DialogWidths.narrow,
  child: IntakeCaptureCard(
    web: true,
    onChooseFiles: choosePreviewFiles,
    onTakePhotograph: null,
    onDropFiles: (_) {},
    cameraAvailable: false,
  ),
);

@Preview(
  name: 'Intake while uploading',
  group: 'Intake',
  theme: intakePreviewThemes,
)
Widget intakeBusyPreview() => SizedBox(
  width: UiSpace.standard.readingMax,
  height: DialogWidths.narrow,
  child: const IntakeCaptureCard(
    web: true,
    onChooseFiles: null,
    onTakePhotograph: null,
    onDropFiles: null,
    cameraAvailable: false,
  ),
);
