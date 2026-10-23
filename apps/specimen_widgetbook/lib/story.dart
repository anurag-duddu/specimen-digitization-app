import 'package:flutter/widgets.dart';
import 'package:specimen_ui/specimen_ui.dart';
import 'package:widgetbook/widgetbook.dart';

/// Every story carries its use, state and keyboard contract beside the live UI.
WidgetbookUseCase story(String name, String guidance, WidgetBuilder builder) =>
    WidgetbookUseCase(
      name: name,
      builder: (context) =>
          StoryFrame(title: name, guidance: guidance, child: builder(context)),
    );

class StoryFrame extends StatelessWidget {
  const StoryFrame({
    super.key,
    required this.title,
    required this.guidance,
    required this.child,
  });
  final String title;
  final String guidance;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    final ui = context.ui;
    return SingleChildScrollView(
      padding: EdgeInsets.all(ui.space.s4),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(title, style: ui.type.titleLarge.copyWith(color: ui.color.ink)),
          SizedBox(height: ui.space.s2),
          Text(
            guidance,
            style: ui.type.body.copyWith(color: ui.color.inkSecondary),
          ),
          SizedBox(height: ui.space.s6),
          child,
        ],
      ),
    );
  }
}

/// Stateful action receipt for synthetic stories; never calls an app service.
class ActionExample extends StatefulWidget {
  const ActionExample({super.key, required this.builder});
  final Widget Function(BuildContext, ValueChanged<String>) builder;
  @override
  State<ActionExample> createState() => _ActionExampleState();
}

class _ActionExampleState extends State<ActionExample> {
  String _receipt = 'No action yet';
  int _count = 0;
  @override
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: [
      widget.builder(context, (value) {
        if (!mounted) return;
        setState(() {
          _receipt = value;
          _count++;
        });
      }),
      SizedBox(height: context.ui.space.s4),
      Semantics(
        liveRegion: true,
        child: Text(
          '$_receipt · $_count actions',
          style: context.ui.type.bodySmall.copyWith(
            color: context.ui.color.inkSecondary,
          ),
        ),
      ),
    ],
  );
}
