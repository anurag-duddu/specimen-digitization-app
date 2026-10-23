/// Async form compositions; network and authentication remain host responsibilities.
library;

import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import '../../foundation/theme.dart';
import '../actions/button.dart';
import '../inputs/checkbox.dart';
import '../inputs/field.dart';
import '../inputs/extended_inputs.dart';
import 'section.dart';

/// Host submission returns null on success or a user-facing error on failure.
/// The host owns persistence, consent, delivery and data policy.
typedef UiMarketingSubmit<T> = Future<String?> Function(T value);

bool _validEmail(String value) =>
    RegExp(r'^[^\s@]+@[^\s@]+\.[^\s@]+$').hasMatch(value);

/// Email capture with native email keyboard/autofill and async submission state.
class UiEmailCapture extends StatefulWidget {
  /// No subscription or message is sent unless the host callback does so.
  const UiEmailCapture({
    super.key,
    required this.onSubmit,
    this.label = 'Email address',
    this.submitLabel = 'Subscribe',
    this.successMessage = 'Thank you. Your request was received.',
    this.privacy,
    this.enabled = true,
  });

  /// Submission callback; null makes the form unavailable.
  final UiMarketingSubmit<String>? onSubmit;

  /// Visible email field label.
  final String label;

  /// Button command.
  final String submitLabel;

  /// Announcement shown only after successful host completion.
  final String successMessage;

  /// Privacy or consent text/link supplied by the host.
  final Widget? privacy;

  /// Disables edits and submission.
  final bool enabled;
  @override
  State<UiEmailCapture> createState() => _UiEmailCaptureState();
}

class _UiEmailCaptureState extends State<UiEmailCapture> {
  final _email = TextEditingController();
  final _focus = FocusNode();
  bool _busy = false;
  bool _success = false;
  String? _error;
  @override
  void dispose() {
    _email.dispose();
    _focus.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (_busy || !widget.enabled || widget.onSubmit == null) return;
    final email = _email.text.trim();
    if (!_validEmail(email)) {
      setState(() {
        _error = 'Enter a complete email address.';
        _success = false;
      });
      _focus.requestFocus();
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
      _success = false;
    });
    String? error;
    try {
      error = await widget.onSubmit!(email);
    } catch (_) {
      error = 'Your request could not be completed. Try again.';
    }
    if (!mounted) return;
    setState(() {
      _busy = false;
      _error = error;
      _success = error == null;
    });
  }

  @override
  Widget build(BuildContext context) => MarketingStack(
    children: [
      UiField(
        label: widget.label,
        controller: _email,
        focusNode: _focus,
        keyboardType: TextInputType.emailAddress,
        autofillHints: const [AutofillHints.email],
        autocorrect: false,
        textInputAction: TextInputAction.done,
        enabled: widget.enabled && widget.onSubmit != null && !_busy,
        errorText: _error,
        onSubmitted: (_) => _submit(),
        onChanged: (_) {
          if (_error != null || _success) {
            setState(() {
              _error = null;
              _success = false;
            });
          }
        },
      ),
      if (widget.privacy != null) widget.privacy!,
      Align(
        alignment: AlignmentDirectional.centerStart,
        child: UiButton(
          label: widget.submitLabel,
          loading: _busy,
          busyLabel: 'Submitting',
          onPressed: !widget.enabled || widget.onSubmit == null
              ? null
              : _submit,
        ),
      ),
      if (_success)
        Semantics(liveRegion: true, child: Text(widget.successMessage)),
    ],
  );
}

/// Newsletter section in centered, split, card or branded form.
class UiNewsletterSection extends StatelessWidget {
  /// Reuses the real email capture control; no static mock form.
  const UiNewsletterSection({
    super.key,
    required this.title,
    required this.onSubmit,
    this.description,
    this.privacy,
    this.media,
    this.layout = UiSectionLayout.centered,
    this.treatment = UiSectionTreatment.plain,
  });

  /// Heading.
  final String title;

  /// Supporting copy.
  final String? description;

  /// Subscription callback.
  final UiMarketingSubmit<String>? onSubmit;

  /// Privacy/consent disclosure.
  final Widget? privacy;

  /// Supporting visual.
  final Widget? media;

  /// Form and visual layout.
  final UiSectionLayout layout;

  /// Surface treatment.
  final UiSectionTreatment treatment;
  @override
  Widget build(BuildContext context) => UiMarketingSection(
    title: title,
    description: description,
    layout: layout,
    treatment: treatment,
    media: media,
    child: ConstrainedBox(
      constraints: BoxConstraints(maxWidth: context.ui.space.readingMax),
      child: UiEmailCapture(onSubmit: onSubmit, privacy: privacy),
    ),
  );
}

/// Contact request submitted to a host, never directly to a service.
@immutable
class UiContactRequest {
  /// Carries normalized non-secret form values.
  const UiContactRequest({
    required this.name,
    required this.email,
    required this.message,
    required this.consent,
    this.lastName,
    this.phone,
    this.phoneCountryCode,
    this.services = const [],
  });

  /// Optional separately entered family name. Never inferred from [name].
  final String? lastName;

  /// Optional verbatim phone number; the host owns parsing and validation.
  final String? phone;

  /// Explicitly selected phone country, never inferred.
  final String? phoneCountryCode;

  /// Explicitly selected service choices.
  final List<String> services;

  /// Sender-provided name.
  final String name;

  /// Trimmed email address.
  final String email;

  /// Message body.
  final String message;

  /// Explicit consent value.
  final bool consent;
}

/// A complete contact form with editable data, validation and consent.
class UiContactForm extends StatefulWidget {
  /// Submission is unavailable when [onSubmit] is null.
  const UiContactForm({
    super.key,
    required this.onSubmit,
    this.consentLabel,
    this.successMessage = 'Your message was received.',
    this.enabled = true,
    this.splitName = false,
    this.showPhone = false,
    this.phoneCountries = const [],
    this.initialPhoneCountry,
    this.services = const [],
  });

  /// Separates given/display name and optional family name on wide screens.
  final bool splitName;

  /// Adds optional native phone input.
  final bool showPhone;

  /// Explicit supported countries; empty keeps a simple verbatim phone editor.
  final List<UiPhoneCountry> phoneCountries;

  /// Explicit initial country, supplied by the host.
  final String? initialPhoneCountry;

  /// Optional service choices; no choice is preselected.
  final List<String> services;

  /// Host handler.
  final UiMarketingSubmit<UiContactRequest>? onSubmit;

  /// If supplied, the checkbox must be accepted before submission.
  final String? consentLabel;

  /// Announced after the host confirms success.
  final String successMessage;

  /// Enables editing and submission.
  final bool enabled;
  @override
  State<UiContactForm> createState() => _UiContactFormState();
}

class _UiContactFormState extends State<UiContactForm> {
  final _name = TextEditingController();
  final _lastName = TextEditingController();
  final _phone = TextEditingController();
  final _services = <String>{};
  late String? _phoneCountry = widget.initialPhoneCountry;
  final _email = TextEditingController();
  final _message = TextEditingController();
  final _nameFocus = FocusNode();
  final _emailFocus = FocusNode();
  final _messageFocus = FocusNode();
  bool _consent = false, _busy = false, _success = false;
  String? _nameError, _emailError, _messageError, _error;
  @override
  void dispose() {
    for (final c in [_name, _lastName, _phone, _email, _message]) {
      c.dispose();
    }
    for (final n in [_nameFocus, _emailFocus, _messageFocus]) {
      n.dispose();
    }
    super.dispose();
  }

  Future<void> _submit() async {
    if (_busy || !widget.enabled || widget.onSubmit == null) return;
    setState(() {
      _success = false;
      _nameError = _name.text.trim().isEmpty ? 'Enter your name.' : null;
      _emailError = _validEmail(_email.text.trim())
          ? null
          : 'Enter a complete email address.';
      _messageError = _message.text.trim().isEmpty ? 'Enter a message.' : null;
      _error = widget.consentLabel != null && !_consent
          ? 'Accept the consent statement to continue.'
          : null;
    });
    if (_nameError != null) {
      _nameFocus.requestFocus();
      return;
    }
    if (_emailError != null) {
      _emailFocus.requestFocus();
      return;
    }
    if (_messageError != null) {
      _messageFocus.requestFocus();
      return;
    }
    if (_error != null) return;
    setState(() => _busy = true);
    String? error;
    try {
      error = await widget.onSubmit!(
        UiContactRequest(
          name: _name.text.trim(),
          email: _email.text.trim(),
          message: _message.text.trim(),
          consent: _consent,
          lastName: widget.splitName ? _lastName.text.trim() : null,
          phone: widget.showPhone ? _phone.text : null,
          phoneCountryCode: widget.showPhone ? _phoneCountry : null,
          services: List.unmodifiable(
            widget.services.where(_services.contains),
          ),
        ),
      );
    } catch (_) {
      error = 'Your message could not be sent. Try again.';
    }
    if (!mounted) return;
    setState(() {
      _busy = false;
      _error = error;
      _success = error == null;
    });
  }

  @override
  Widget build(BuildContext context) {
    final enabled = widget.enabled && widget.onSubmit != null && !_busy;
    return MarketingStack(
      children: [
        UiSectionGrid(
          columns: widget.splitName ? 2 : 1,
          children: [
            UiField(
              label: widget.splitName ? 'First name' : 'Name',
              controller: _name,
              focusNode: _nameFocus,
              errorText: _nameError,
              enabled: enabled,
              autofillHints: [
                widget.splitName ? AutofillHints.givenName : AutofillHints.name,
              ],
              textInputAction: TextInputAction.next,
            ),
            if (widget.splitName)
              UiField(
                label: 'Last name (optional)',
                controller: _lastName,
                enabled: enabled,
                autofillHints: const [AutofillHints.familyName],
                textInputAction: TextInputAction.next,
              ),
          ],
        ),
        UiField(
          label: 'Email address',
          controller: _email,
          focusNode: _emailFocus,
          errorText: _emailError,
          enabled: enabled,
          keyboardType: TextInputType.emailAddress,
          autocorrect: false,
          autofillHints: const [AutofillHints.email],
          textInputAction: TextInputAction.next,
        ),
        if (widget.showPhone)
          UiPhoneField(
            label: 'Phone number (optional)',
            controller: _phone,
            enabled: enabled,
            countryCode: _phoneCountry,
            countries: widget.phoneCountries,
            onCountryChanged: (value) => setState(() => _phoneCountry = value),
          ),
        UiField(
          label: 'Message',
          controller: _message,
          focusNode: _messageFocus,
          errorText: _messageError,
          enabled: enabled,
          keyboardType: TextInputType.multiline,
          minLines: 4,
          maxLines: 8,
        ),
        if (widget.services.isNotEmpty) ...[
          Text('Services', style: context.ui.type.label),
          UiSectionGrid(
            columns: 2,
            children: [
              for (final service in widget.services)
                UiCheckbox(
                  label: service,
                  value: _services.contains(service),
                  onChanged: enabled
                      ? (value) => setState(() {
                          if (value) {
                            _services.add(service);
                          } else {
                            _services.remove(service);
                          }
                        })
                      : null,
                ),
            ],
          ),
        ],
        if (widget.consentLabel != null)
          UiCheckbox(
            label: widget.consentLabel!,
            value: _consent,
            onChanged: enabled
                ? (value) => setState(() => _consent = value)
                : null,
          ),
        if (_error != null)
          Semantics(
            liveRegion: true,
            child: Text(
              _error!,
              style: context.ui.type.body.copyWith(
                color: context.ui.color.status.blocked.content,
              ),
            ),
          ),
        Align(
          alignment: AlignmentDirectional.centerStart,
          child: UiButton(
            label: 'Send message',
            loading: _busy,
            busyLabel: 'Sending',
            onPressed: !widget.enabled || widget.onSubmit == null
                ? null
                : _submit,
          ),
        ),
        if (_success)
          Semantics(liveRegion: true, child: Text(widget.successMessage)),
      ],
    );
  }
}

/// Contact section with actual form plus contact-method, map or photograph slots.
class UiContactSection extends StatelessWidget {
  /// Methods are explicit host actions, such as opening email or a map.
  const UiContactSection({
    super.key,
    required this.title,
    required this.form,
    this.description,
    this.methods = const [],
    this.media,
    this.layout = UiSectionLayout.split,
  });

  /// Heading.
  final String title;

  /// Contact introduction.
  final String? description;

  /// Actual contact form or other contact workflow.
  final Widget form;

  /// Contact method commands.
  final List<UiMarketingAction> methods;

  /// Map or photograph. The host owns map accessibility and navigation.
  final Widget? media;

  /// Columns versus centered content.
  final UiSectionLayout layout;
  @override
  Widget build(BuildContext context) => UiMarketingSection(
    title: title,
    description: description,
    layout: layout,
    media: media,
    actions: methods,
    child: form,
  );
}

/// Auth form stages. Existing application auth services stay unchanged.
enum UiAuthMode {
  /// Existing account with a password.
  signIn,

  /// New account details and password.
  signUp,

  /// Password-recovery email request.
  recovery,

  /// New password supplied after host-side token validation.
  resetPassword,

  /// Email sign-in link request.
  emailLink,

  /// One-time verification code entry.
  verification,
}

/// Values delivered only to the host's authentication callback.
@immutable
class UiAuthSubmission {
  /// Secrets must not be logged or persisted by catalog examples.
  const UiAuthSubmission({
    required this.mode,
    required this.email,
    required this.password,
    required this.name,
    required this.code,
  });

  /// Submitted stage.
  final UiAuthMode mode;

  /// Trimmed email.
  final String email;

  /// Password without trimming or transformation.
  final String password;

  /// Display name supplied on signup.
  final String name;

  /// One-time code, trimmed only.
  final String code;
}

/// Auth form with correct autofill/keyboard modes, visibility and async states.
///
/// The host authenticates, enforces password policy and validates recovery
/// tokens; this component never changes providers or session behavior.
class UiAuthForm extends StatefulWidget {
  /// The callback returns a presentable error or null; null is not a session.
  const UiAuthForm({
    super.key,
    required this.mode,
    required this.onSubmit,
    this.email = '',
    this.successMessage = 'Request completed.',
    this.otherActions = const [],
    this.passwordHelp,
    this.validatePassword,
    this.enabled = true,
  });

  /// Current stage.
  final UiAuthMode mode;

  /// Auth service callback, null disables submission.
  final UiMarketingSubmit<UiAuthSubmission>? onSubmit;

  /// Initial email address. Key the form to reset for a different account.
  final String email;

  /// Host-specified success announcement.
  final String successMessage;

  /// Recovery, resend, social provider and stage-switch actions.
  final List<UiMarketingAction> otherActions;

  /// Actual password requirements supplied by the host.
  final String? passwordHelp;

  /// Host policy, used only for signup or reset; null requires a nonempty value.
  final String? Function(String value)? validatePassword;

  /// Enables editing/submission.
  final bool enabled;
  @override
  State<UiAuthForm> createState() => _UiAuthFormState();
}

class _UiAuthFormState extends State<UiAuthForm> {
  late final _email = TextEditingController(text: widget.email);
  final _password = TextEditingController();
  final _name = TextEditingController();
  final _code = TextEditingController();
  final _emailFocus = FocusNode();
  final _nameFocus = FocusNode();
  final _passwordFocus = FocusNode();
  final _codeFocus = FocusNode();
  bool _visible = false, _busy = false, _success = false;
  String? _error;
  String? _nameError, _emailError, _passwordError, _codeError;
  int _generation = 0;
  bool get _hasPassword => [
    UiAuthMode.signIn,
    UiAuthMode.signUp,
    UiAuthMode.resetPassword,
  ].contains(widget.mode);
  bool get _hasEmail =>
      widget.mode != UiAuthMode.resetPassword &&
      widget.mode != UiAuthMode.verification;
  @override
  void didUpdateWidget(UiAuthForm oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.mode != widget.mode) {
      _generation++;
      _password.clear();
      _code.clear();
      _error = null;
      _nameError = _emailError = _passwordError = _codeError = null;
      _busy = false;
      _success = false;
      _visible = false;
    }
  }

  @override
  void dispose() {
    _generation++;
    for (final c in [_email, _password, _name, _code]) {
      c.dispose();
    }
    for (final node in [_emailFocus, _nameFocus, _passwordFocus, _codeFocus]) {
      node.dispose();
    }
    super.dispose();
  }

  Future<void> _submit() async {
    if (_busy || !widget.enabled || widget.onSubmit == null) return;
    String? error;
    setState(() {
      _nameError = widget.mode == UiAuthMode.signUp && _name.text.trim().isEmpty
          ? 'Enter your name.'
          : null;
      _emailError = _hasEmail && !_validEmail(_email.text.trim())
          ? 'Enter a complete email address.'
          : null;
      _passwordError = _hasPassword && _password.text.isEmpty
          ? 'Enter a password.'
          : [UiAuthMode.signUp, UiAuthMode.resetPassword].contains(widget.mode)
          ? widget.validatePassword?.call(_password.text)
          : null;
      _codeError =
          widget.mode == UiAuthMode.verification && _code.text.trim().isEmpty
          ? 'Enter the verification code.'
          : null;
      _error = null;
      _success = false;
    });
    for (final invalid in [
      (_nameError, _nameFocus),
      (_emailError, _emailFocus),
      (_passwordError, _passwordFocus),
      (_codeError, _codeFocus),
    ]) {
      if (invalid.$1 != null) {
        invalid.$2.requestFocus();
        return;
      }
    }
    final generation = ++_generation;
    final submission = UiAuthSubmission(
      mode: widget.mode,
      email: _email.text.trim(),
      password: _password.text,
      name: _name.text.trim(),
      code: _code.text.trim(),
    );
    setState(() => _busy = true);
    try {
      error = await widget.onSubmit!(submission);
    } catch (_) {
      error = 'The request could not be completed. Try again.';
    }
    if (!mounted || generation != _generation) return;
    setState(() {
      _busy = false;
      _error = error;
      _success = error == null;
    });
  }

  @override
  Widget build(BuildContext context) {
    final enabled = widget.enabled && widget.onSubmit != null && !_busy;
    const resetActionLabel = 'Reset password';
    final label = switch (widget.mode) {
      UiAuthMode.signIn => 'Sign in',
      UiAuthMode.signUp => 'Create account',
      UiAuthMode.recovery => 'Send recovery link',
      UiAuthMode.resetPassword => resetActionLabel,
      UiAuthMode.emailLink => 'Send sign-in link',
      UiAuthMode.verification => 'Verify code',
    };
    return AutofillGroup(
      child: MarketingStack(
        children: [
          if (widget.mode == UiAuthMode.signUp)
            UiField(
              label: 'Name',
              controller: _name,
              focusNode: _nameFocus,
              errorText: _nameError,
              enabled: enabled,
              autofillHints: const [AutofillHints.name],
              textInputAction: TextInputAction.next,
            ),
          if (_hasEmail)
            UiField(
              label: 'Email address',
              controller: _email,
              focusNode: _emailFocus,
              errorText: _emailError,
              enabled: enabled,
              keyboardType: TextInputType.emailAddress,
              autofillHints: const [AutofillHints.email],
              autocorrect: false,
              textInputAction: _hasPassword
                  ? TextInputAction.next
                  : TextInputAction.done,
              onSubmitted: _hasPassword ? null : (_) => _submit(),
            ),
          if (_hasPassword)
            UiField(
              label: 'Password',
              controller: _password,
              focusNode: _passwordFocus,
              errorText: _passwordError,
              enabled: enabled,
              obscureText: !_visible,
              autocorrect: false,
              helpText: widget.passwordHelp,
              autofillHints: [
                widget.mode == UiAuthMode.signIn
                    ? AutofillHints.password
                    : AutofillHints.newPassword,
              ],
              textInputAction: TextInputAction.done,
              onSubmitted: (_) => _submit(),
              trailing: UiButton(
                label: _visible ? 'Hide' : 'Show',
                semanticsLabel: _visible ? 'Hide password' : 'Show password',
                variant: UiButtonVariant.ghost,
                onPressed: enabled
                    ? () => setState(() => _visible = !_visible)
                    : null,
              ),
            ),
          if (widget.mode == UiAuthMode.verification)
            UiField(
              label: 'Verification code',
              controller: _code,
              focusNode: _codeFocus,
              errorText: _codeError,
              enabled: enabled,
              keyboardType: TextInputType.text,
              autocorrect: false,
              autofillHints: const [AutofillHints.oneTimeCode],
              textInputAction: TextInputAction.done,
              onSubmitted: (_) => _submit(),
            ),
          if (_error != null)
            Semantics(
              liveRegion: true,
              child: Text(
                _error!,
                style: context.ui.type.body.copyWith(
                  color: context.ui.color.status.blocked.content,
                ),
              ),
            ),
          Align(
            alignment: AlignmentDirectional.centerStart,
            child: UiButton(
              label: label,
              loading: _busy,
              busyLabel: 'Submitting',
              onPressed: !widget.enabled || widget.onSubmit == null
                  ? null
                  : _submit,
            ),
          ),
          if (_success)
            Semantics(liveRegion: true, child: Text(widget.successMessage)),
          MarketingActions(actions: widget.otherActions),
        ],
      ),
    );
  }
}
