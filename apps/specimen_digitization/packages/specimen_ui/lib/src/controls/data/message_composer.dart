/// Message drafting with caller-owned text and delivery.
library;

import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import '../../foundation/theme.dart';
import '../actions/button.dart';
import '../inputs/text_area.dart';

/// Multiline composer. Ctrl/Cmd+Enter sends; Enter inserts a new line.
/// A failed send preserves the draft. A successful send clears it only if the
/// same controller still contains the submitted text. Attachments remain owned
/// by the host, and [attachments] does not imply they have been transmitted.
/// Replacing [controller] starts a new draft context immediately. Completion
/// from a previous context cannot clear, report an error or unlock a newer send.
class UiMessageComposer extends StatefulWidget {
  /// Creates the component with explicit content and caller-owned state.
  const UiMessageComposer({
    super.key,
    required this.controller,
    required this.onSend,
    this.label = 'Message',
    this.enabled = true,
    this.onAttach,
    this.attachments = const [],
  });

  /// The caller-owned draft controller, never disposed by this component.
  final TextEditingController controller;

  /// The delivery callback; successful completion clears only the unchanged draft.
  final Future<void> Function(String message)? onSend;

  /// The visible accessible name supplied by the host.
  final String label;

  /// Whether the caller permits interaction.
  final bool enabled;

  /// The caller action opening an attachment chooser.
  final VoidCallback? onAttach;

  /// The caller-owned attachment previews, without implicit upload or transmission.
  final List<Widget> attachments;
  @override
  State<UiMessageComposer> createState() => _UiMessageComposerState();
}

class _UiMessageComposerState extends State<UiMessageComposer> {
  bool _busy = false;
  int _generation = 0;
  String? _error;
  bool get _canSend =>
      widget.enabled &&
      !_busy &&
      widget.onSend != null &&
      (widget.controller.text.trim().isNotEmpty ||
          widget.attachments.isNotEmpty);
  @override
  void initState() {
    super.initState();
    widget.controller.addListener(_changed);
  }

  void _changed() {
    if (mounted) setState(() {});
  }

  @override
  void didUpdateWidget(UiMessageComposer old) {
    super.didUpdateWidget(old);
    if (old.controller != widget.controller) {
      old.controller.removeListener(_changed);
      widget.controller.addListener(_changed);
      _generation++;
      _busy = false;
      _error = null;
    }
  }

  @override
  void dispose() {
    widget.controller.removeListener(_changed);
    super.dispose();
  }

  Future<void> _send() async {
    if (!_canSend) return;
    final controller = widget.controller;
    final text = controller.text;
    final send = widget.onSend!;
    final generation = ++_generation;
    bool current() =>
        mounted && generation == _generation && widget.controller == controller;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await send(text);
      if (current() && controller.text == text) {
        controller.clear();
      }
    } catch (_) {
      if (current()) {
        setState(() => _error = 'Could not send. Your draft is preserved.');
      }
    } finally {
      if (current()) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final ui = context.ui;
    return CallbackShortcuts(
      bindings: {
        const SingleActivator(LogicalKeyboardKey.enter, control: true): _send,
        const SingleActivator(LogicalKeyboardKey.enter, meta: true): _send,
      },
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        mainAxisSize: MainAxisSize.min,
        children: [
          UiTextArea(
            label: widget.label,
            controller: widget.controller,
            enabled: widget.enabled,
            errorText: _error,
            helpText: 'Ctrl or ⌘ + Enter to send',
            minLines: 3,
          ),
          if (widget.attachments.isNotEmpty)
            Padding(
              padding: EdgeInsets.only(top: ui.space.s3),
              child: Wrap(
                spacing: ui.space.s2,
                runSpacing: ui.space.s2,
                children: widget.attachments,
              ),
            ),
          SizedBox(height: ui.space.s3),
          Wrap(
            alignment: WrapAlignment.spaceBetween,
            spacing: ui.space.s3,
            runSpacing: ui.space.s2,
            children: [
              if (widget.onAttach != null)
                UiButton(
                  label: 'Attach file',
                  variant: UiButtonVariant.secondary,
                  onPressed: widget.enabled && !_busy ? widget.onAttach : null,
                ),
              UiButton(
                label: 'Send message',
                busyLabel: 'Sending message',
                loading: _busy,
                onPressed: _canSend ? _send : null,
              ),
            ],
          ),
        ],
      ),
    );
  }
}
