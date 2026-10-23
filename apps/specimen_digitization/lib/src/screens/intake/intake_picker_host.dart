import 'package:flutter/widgets.dart';
import 'intake_auth_session.dart' as platform;

/// Presentation is separate from the popup reserved for OAuth consent.
class IntakePickerHost {
  const IntakePickerHost();

  String? get returnOrigin => platform.intakePickerReturnOrigin;

  Widget buildFrame({
    required String url,
    required String pickerId,
    required ValueChanged<String> onEvent,
    required ValueChanged<String> onFailure,
  }) => platform.buildIntakePickerFrame(
    url: url,
    pickerId: pickerId,
    onEvent: onEvent,
    onFailure: onFailure,
  );
}
