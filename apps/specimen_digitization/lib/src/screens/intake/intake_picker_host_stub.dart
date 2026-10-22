import 'package:flutter/widgets.dart';

String? get intakePickerReturnOrigin => null;

Widget buildIntakePickerFrame({
  required String url,
  required String pickerId,
  required ValueChanged<String> onEvent,
  required ValueChanged<String> onFailure,
}) => throw UnsupportedError('Inline Drive selection is available on web.');
