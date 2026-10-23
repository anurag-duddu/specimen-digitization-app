import 'package:flutter/material.dart';
import 'package:specimen_ui/specimen_ui.dart';
import 'package:widgetbook/widgetbook.dart';

/// The environment is outside the viewport navigator so modal routes inherit
/// the same tokens, text scale, direction and motion preference as their trigger.
class SpecimenEnvironmentAddon extends WidgetbookAddon<SpecimenEnvironment> {
  SpecimenEnvironmentAddon() : super(name: 'Specimen environment');

  @override
  List<Field<dynamic>> get fields => [
    ObjectDropdownField<String>(
      name: 'appearance',
      values: ['Light', 'Dark'],
      initialValue: 'Light',
    ),
    ObjectDropdownField<String>(
      name: 'input',
      values: ['Automatic', 'Touch', 'Pointer'],
      initialValue: 'Automatic',
    ),
    ObjectDropdownField<String>(
      name: 'direction',
      values: ['LTR', 'RTL'],
      initialValue: 'LTR',
    ),
    BooleanField(name: 'reduced motion', initialValue: false),
  ];

  @override
  SpecimenEnvironment valueFromQueryGroup(Map<String, String> group) =>
      SpecimenEnvironment(
        dark: valueOf<String>('appearance', group) == 'Dark',
        density: switch (valueOf<String>('input', group)) {
          'Touch' => UiDensityMode.touch,
          'Pointer' => UiDensityMode.pointer,
          _ => null,
        },
        direction: valueOf<String>('direction', group) == 'RTL'
            ? TextDirection.rtl
            : TextDirection.ltr,
        reduceMotion: valueOf<bool>('reduced motion', group) ?? false,
      );

  @override
  Widget buildUseCase(
    BuildContext context,
    Widget child,
    SpecimenEnvironment setting,
  ) => SpecimenEnvironmentScope(setting: setting, child: child);
}

class SpecimenEnvironment {
  const SpecimenEnvironment({
    this.dark = false,
    this.density,
    this.direction = TextDirection.ltr,
    this.reduceMotion = false,
  });
  final bool dark;
  final UiDensityMode? density;
  final TextDirection direction;
  final bool reduceMotion;
}

class SpecimenEnvironmentScope extends StatelessWidget {
  const SpecimenEnvironmentScope({
    super.key,
    required this.setting,
    required this.child,
  });
  final SpecimenEnvironment setting;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    final ui = setting.dark ? UiThemeData.dark() : UiThemeData.light();
    return Theme(
      data: ui.toThemeData().copyWith(platform: Theme.of(context).platform),
      child: MediaQuery(
        data: MediaQuery.of(context).copyWith(
          platformBrightness: setting.dark ? Brightness.dark : Brightness.light,
          disableAnimations: setting.reduceMotion,
          accessibleNavigation: setting.reduceMotion,
        ),
        child: Directionality(
          textDirection: setting.direction,
          child: UiTheme(
            data: ui,
            child: Density(initialMode: setting.density, child: child),
          ),
        ),
      ),
    );
  }
}

/// Owns modal routes inside the selected preview viewport. Product modal helpers
/// normally target the root navigator; the explicit scope preserves that default
/// while containing preview dialogs and retaining the environment above them.
class SpecimenPreview extends StatefulWidget {
  const SpecimenPreview({super.key, required this.child});
  final Widget child;
  @override
  State<SpecimenPreview> createState() => _SpecimenPreviewState();
}

class _SpecimenPreviewState extends State<SpecimenPreview> {
  var _navigator = GlobalKey<NavigatorState>();
  String? _storyPath;
  @override
  Widget build(BuildContext context) {
    final path = WidgetbookState.of(context).path;
    if (_storyPath != path) {
      _storyPath = path;
      // Routes, queued toasts and callbacks belong to the selected story.
      // Knob and environment changes keep the same story-owned navigator.
      _navigator = GlobalKey<NavigatorState>();
    }
    return UiModalNavigator(
      navigatorKey: _navigator,
      child: Navigator(
        key: _navigator,
        pages: [
          MaterialPage<void>(
            child: ColoredBox(
              color: context.ui.color.ground,
              child: UiToastHost(child: SafeArea(child: widget.child)),
            ),
          ),
        ],
        onDidRemovePage: (_) {},
      ),
    );
  }
}
