/// Character shortcuts are inactive while an editor owns the caret.
library;

import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';

/// A shortcut whose unmodified characters remain available to text input.
class EditingSafeActivator extends SingleActivator {
  const EditingSafeActivator(
    super.trigger, {
    super.shift,
    super.control,
    super.alt,
    super.meta,
  });

  @override
  bool accepts(KeyEvent event, HardwareKeyboard state) {
    final BuildContext? context = FocusManager.instance.primaryFocus?.context;
    if (context != null &&
        (context.widget is EditableText ||
            context.findAncestorWidgetOfExactType<EditableText>() != null)) {
      return false;
    }
    return super.accepts(event, state);
  }
}
