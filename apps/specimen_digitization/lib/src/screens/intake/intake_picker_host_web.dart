import 'dart:async';
import 'package:flutter/widgets.dart';
import 'package:specimen_ui/specimen_ui.dart';
import 'package:web/web.dart' as web;
import '../../api_repository.dart' show apiRequestTimeout;
import 'intake_picker_bridge_web.dart';
import 'intake_timing.dart';

String get intakePickerReturnOrigin => web.window.location.origin;

Widget buildIntakePickerFrame({
  required String url,
  required String pickerId,
  required ValueChanged<String> onEvent,
  required ValueChanged<String> onFailure,
}) => _InlinePickerFrame(
  key: ValueKey(pickerId),
  url: url,
  pickerId: pickerId,
  onEvent: onEvent,
  onFailure: onFailure,
);

class _InlinePickerFrame extends StatefulWidget {
  const _InlinePickerFrame({
    super.key,
    required this.url,
    required this.pickerId,
    required this.onEvent,
    required this.onFailure,
  });
  final String url, pickerId;
  final ValueChanged<String> onEvent, onFailure;
  @override
  State<_InlinePickerFrame> createState() => _InlinePickerFrameState();
}

class _InlinePickerFrameState extends State<_InlinePickerFrame> {
  IntakePickerBridge? bridge;
  Timer? loadingTimer, expiryTimer;
  int generation = 0;
  bool ready = false;
  @override
  void initState() {
    super.initState();
    start();
  }

  @override
  void didUpdateWidget(_InlinePickerFrame oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.url != oldWidget.url || widget.pickerId != oldWidget.pickerId) {
      clear();
      start();
    }
  }

  void start() {
    final epoch = ++generation;
    bool current() => mounted && generation == epoch;
    try {
      bridge = IntakePickerBridge(
        url: widget.url,
        pickerId: widget.pickerId,
        onEvent: (action) {
          if (!current()) return;
          if (action == 'ready') {
            loadingTimer?.cancel();
            bridge?.frame.style.visibility = 'visible';
            setState(() => ready = true);
          }
          widget.onEvent(action);
        },
      );
      bridge!.frame.style.visibility = 'hidden';
      loadingTimer = Timer(apiRequestTimeout, () {
        if (current() && !ready) {
          widget.onFailure(
            'Google Drive could not load. Retry to choose photos.',
          );
        }
      });
      expiryTimer = Timer(intakeAuthorizationTimeout, () {
        if (current()) {
          widget.onFailure('Drive selection expired. Choose photos again.');
        }
      });
    } catch (_) {
      scheduleMicrotask(() {
        if (current()) {
          widget.onFailure(
            'Google Drive could not load. Retry to choose photos.',
          );
        }
      });
    }
  }

  void clear() {
    generation++;
    loadingTimer?.cancel();
    expiryTimer?.cancel();
    bridge?.dispose();
    bridge = null;
    ready = false;
  }

  @override
  void dispose() {
    clear();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => Stack(
    fit: StackFit.expand,
    children: [
      if (bridge case final current?)
        HtmlElementView.fromTagName(
          key: ObjectKey(current),
          tagName: 'div',
          onElementCreated: (element) {
            if (!mounted || !identical(bridge, current)) return;
            final container = element as web.HTMLElement;
            container.style
              ..width = '100%'
              ..height = '100%';
            container.appendChild(current.frame);
          },
        ),
      if (!ready)
        Center(
          child: Padding(
            padding: EdgeInsets.all(context.ui.space.s4),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Semantics(
                  liveRegion: true,
                  child: Text(
                    'Loading Google Drive photos…',
                    style: context.ui.type.body,
                  ),
                ),
                SizedBox(height: context.ui.space.s3),
                const UiProgress.bar(
                  semanticsLabel: 'Loading Google Drive photos',
                ),
              ],
            ),
          ),
        ),
    ],
  );
}
