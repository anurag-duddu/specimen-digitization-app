import 'dart:async';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';
import 'harness/control_contract.dart';

void main() {
  testWidgets('a different composer draft is not blocked by prior delivery', (
    tester,
  ) async {
    final first = TextEditingController(text: 'First conversation');
    final second = TextEditingController(text: 'Second conversation');
    final pending = Completer<void>();
    addTearDown(first.dispose);
    addTearDown(second.dispose);
    await tester.pumpWidget(
      uiHarness(
        child: UiMessageComposer(
          controller: first,
          onSend: (_) => pending.future,
        ),
      ),
    );
    await tester.tap(find.text('Send message'));
    await tester.pump();
    await tester.pumpWidget(
      uiHarness(
        child: UiMessageComposer(controller: second, onSend: (_) async {}),
      ),
    );
    final send = tester
        .widgetList<UiButton>(find.byType(UiButton))
        .singleWhere((b) => b.label == 'Send message');
    final available = send.onPressed != null && !send.loading;
    pending.complete();
    await tester.pump();
    expect(available, isTrue);
  });
  testWidgets('radar accepts long host category labels at narrow large text', (
    tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(
        textScaler: const TextScaler.linear(2),
        child: const SizedBox(
          width: 320,
          child: SingleChildScrollView(
            child: UiDataVisualization(
              label: 'Collection completeness',
              kind: UiDataVisualizationKind.radar,
              series: [
                UiChartSeries(
                  label: 'Reviewed',
                  data: [
                    UiChartDatum(
                      label:
                          'Geographic location evidence and historical collection locality precision',
                      value: 10,
                    ),
                    UiChartDatum(
                      label:
                          'Taxonomic authority resolution and current accepted identification',
                      value: 20,
                    ),
                    UiChartDatum(
                      label:
                          'Collector attribution and original source transcription completeness',
                      value: 30,
                    ),
                  ],
                ),
              ],
            ),
          ),
        ),
      ),
    );
    expect(tester.takeException(), isNull);
  });
  testWidgets('valid tiny right-edge crop can be resized', (tester) async {
    await tester.pumpWidget(
      uiHarness(
        child: SingleChildScrollView(
          child: UiCropEditor(
            image: const SizedBox(),
            value: const Rect.fromLTWH(.995, .1, .005, .5),
            onChanged: (_) {},
          ),
        ),
      ),
    );
    final slider = tester
        .widgetList<UiSlider>(find.byType(UiSlider))
        .firstWhere((s) => s.label == 'Crop width');
    expect(() => slider.onChanged!(.003), returnsNormally);
  });
  testWidgets('drawer remains usable with short keyboard-constrained height', (
    tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(
        textScaler: const TextScaler.linear(2),
        child: SizedBox(
          width: 320,
          height: 280,
          child: UiDrawer(
            title: 'Notification settings',
            description: 'Choose which collection updates you want to receive.',
            header: const UiSearchField(
              label: 'Search settings',
              clearLabel: 'Clear',
            ),
            footer: UiButtonRow(
              primary: UiButton(label: 'Apply locally', onPressed: () {}),
              secondary: UiButton(label: 'Cancel', onPressed: () {}),
            ),
            child: const Text('Preferences'),
          ),
        ),
      ),
    );
    expect(tester.takeException(), isNull);
  });
}
