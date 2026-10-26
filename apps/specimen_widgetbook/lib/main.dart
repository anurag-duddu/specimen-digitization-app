import 'package:flutter/material.dart';
import 'package:widgetbook/widgetbook.dart';

import 'catalog.dart';
import 'environment.dart';

void main() => runApp(const SpecimenWidgetbook());

class SpecimenWidgetbook extends StatelessWidget {
  const SpecimenWidgetbook({super.key});

  @override
  Widget build(BuildContext context) => Widgetbook.material(
    initialRoute: '/?path=foundations/brand-hero/welcome-and-actions',
    directories: specimenCatalog,
    addons: [
      SpecimenEnvironmentAddon(),
      TextScaleAddon(min: 1, max: 2, divisions: 4, initialScale: 1),
      ViewportAddon([
        ViewportData(
          name: 'Small phone',
          width: 320,
          height: 720,
          pixelRatio: 2,
          platform: TargetPlatform.android,
        ),
        ViewportData(
          name: 'Phone',
          width: 390,
          height: 844,
          pixelRatio: 3,
          platform: TargetPlatform.iOS,
          safeAreas: const EdgeInsets.only(top: 47, bottom: 34),
        ),
        ViewportData(
          name: 'Tablet portrait',
          width: 768,
          height: 1024,
          pixelRatio: 2,
          platform: TargetPlatform.iOS,
        ),
        ViewportData(
          name: 'Tablet landscape',
          width: 1180,
          height: 820,
          pixelRatio: 2,
          platform: TargetPlatform.android,
        ),
        ViewportData(
          name: 'Desktop',
          width: 1440,
          height: 900,
          pixelRatio: 1,
          platform: TargetPlatform.macOS,
        ),
      ]),
      BuilderAddon(
        name: 'Product canvas',
        builder: (context, child) => SpecimenPreview(child: child),
      ),
      SemanticsAddon(),
    ],
  );
}
