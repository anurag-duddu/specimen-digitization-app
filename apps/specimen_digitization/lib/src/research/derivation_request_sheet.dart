import 'package:flutter/services.dart' show TextInputAction;
import 'package:flutter/widgets.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../vocabulary.dart';
import '../widgets/adaptive_form.dart';

class ResearchDerivationRequestChoice {
  const ResearchDerivationRequestChoice({
    required this.fields,
    required this.reason,
  });

  final List<String> fields;
  final String reason;
}

/// Asks which server-eligible fields to consider and records the review reason.
Future<ResearchDerivationRequestChoice?> showResearchDerivationRequest(
  BuildContext context, {
  required List<String> eligibleFields,
}) {
  final formKey = GlobalKey<_DerivationRequestFormState>();
  return showAdaptiveModal<ResearchDerivationRequestChoice>(
    context,
    title: 'Fill the rest',
    body: (_) =>
        _DerivationRequestForm(key: formKey, eligibleFields: eligibleFields),
    primaryAction: (actionContext) => UiButton(
      label: 'Request suggestions',
      onPressed: () {
        final choice = formKey.currentState?.choice;
        if (choice == null) {
          formKey.currentState?.showValidationError();
          return;
        }
        Navigator.of(actionContext).pop(choice);
      },
    ),
    secondaryAction: (actionContext) => UiButton(
      label: 'Cancel',
      variant: UiButtonVariant.ghost,
      onPressed: () => Navigator.of(actionContext).pop(),
    ),
  );
}

class _DerivationRequestForm extends StatefulWidget {
  const _DerivationRequestForm({super.key, required this.eligibleFields});

  final List<String> eligibleFields;

  @override
  State<_DerivationRequestForm> createState() => _DerivationRequestFormState();
}

class _DerivationRequestFormState extends State<_DerivationRequestForm> {
  final TextEditingController _reason = TextEditingController();
  late final Set<String> _selected = widget.eligibleFields.toSet();
  bool _invalid = false;

  ResearchDerivationRequestChoice? get choice {
    final reason = _reason.text.trim();
    if (_selected.isEmpty || reason.isEmpty) return null;
    return ResearchDerivationRequestChoice(
      fields: List.unmodifiable(
        widget.eligibleFields.where(_selected.contains),
      ),
      reason: reason,
    );
  }

  void showValidationError() => setState(() => _invalid = true);

  @override
  void dispose() {
    _reason.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final ui = context.ui;
    return SingleChildScrollView(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(
            'Choose which missing location details to look up. You will review each suggestion before it can change the record.',
            style: ui.type.body,
          ),
          SizedBox(height: ui.space.s3),
          for (final field in widget.eligibleFields)
            UiCheckbox(
              key: ValueKey('derive-field-$field'),
              label: vocabularyLabel(field),
              value: _selected.contains(field),
              onChanged: (selected) => setState(() {
                if (selected) {
                  _selected.add(field);
                } else {
                  _selected.remove(field);
                }
                _invalid = false;
              }),
            ),
          SizedBox(height: ui.space.s3),
          UiField(
            label: 'Reason',
            controller: _reason,
            errorText: _invalid && _reason.text.trim().isEmpty
                ? 'Enter a reason for this request.'
                : null,
            textInputAction: TextInputAction.done,
            onChanged: (_) => setState(() => _invalid = false),
          ),
          if (_invalid && _selected.isEmpty) ...[
            SizedBox(height: ui.space.s2),
            Text(
              'Choose at least one location detail.',
              style: ui.type.bodySmall.copyWith(
                color: ui.color.status.needsReview.content,
              ),
            ),
          ],
        ],
      ),
    );
  }
}
