import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';
import '../../harness/control_contract.dart';

void main() {
  for (final double width in <double>[390, 840, 1440]) {
    for (final double scale in <double>[1, 2]) {
      testWidgets('workspace hierarchy fits $width at $scale text', (
        tester,
      ) async {
        tester.view.devicePixelRatio = 1;
        tester.view.physicalSize = Size(width, 900);
        addTearDown(tester.view.reset);
        final selected = ValueNotifier<int>(0);
        addTearDown(selected.dispose);
        await tester.pumpWidget(
          uiHarness(
            child: Builder(
              builder: (context) {
                return MediaQuery(
                  data: MediaQuery.of(
                    context,
                  ).copyWith(textScaler: TextScaler.linear(scale)),
                  child: UiWorkspaceHeader(
                    identity: const Text('Specimen Digitization / Insects'),
                    compactIdentity: UiButton(
                      label: 'Synthetic Insects',
                      semanticsLabel: 'Choose collection',
                      variant: UiButtonVariant.ghost,
                      trailing: UiIcons.expand,
                      onPressed: () {},
                    ),
                    navigation: UiTabs(
                      tabs: const [
                        UiTab(label: 'Queue'),
                        UiTab(label: 'Intake'),
                      ],
                      selected: selected,
                      semanticsLabel: 'Workspace navigation',
                    ),
                    navigationWidth:
                        UiTabStyle.resolve(
                          context.ui,
                          textScaler: TextScaler.linear(scale),
                        ).intrinsicWidth(context, const [
                          UiTab(label: 'Queue'),
                          UiTab(label: 'Intake'),
                        ]),
                    actions: <Widget>[
                      UiButton(
                        label: 'Test',
                        variant: UiButtonVariant.ghost,
                        onPressed: () {},
                      ),
                      UiIconButton(
                        icon: UiIcons.account,
                        semanticsLabel: 'Account',
                        onPressed: () {},
                      ),
                    ],
                  ),
                );
              },
            ),
          ),
        );
        await tester.pumpAndSettle();
        expect(tester.takeException(), isNull);
        final Rect header = tester.getRect(find.byType(UiWorkspaceHeader));
        expect(header.width, width);
        expect(header.height, greaterThanOrEqualTo(UiDensity.hitBox));
        if (width < WindowClass.expandedMin) {
          expect(find.text('Specimen Digitization / Insects'), findsNothing);
          expect(find.text('Synthetic Insects'), findsOneWidget);
        } else {
          expect(find.text('Specimen Digitization / Insects'), findsOneWidget);
        }
      });
    }
  }

  testWidgets('workspace header survives a routed local toolbar', (
    tester,
  ) async {
    UiScaffoldSlots? slots;
    await tester.pumpWidget(
      uiHarness(
        child: UiScaffold(
          header: const Text('Workspace navigation'),
          body: Builder(
            builder: (context) {
              slots = UiScaffoldSlots.of(context);
              return const Text('Record body');
            },
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    slots!.setTopBar(const UiTopBar(title: 'Record commands'));
    await tester.pumpAndSettle();
    expect(find.text('Workspace navigation'), findsOneWidget);
    expect(find.text('Record commands'), findsOneWidget);
    expect(
      tester.getRect(find.text('Workspace navigation')).bottom,
      lessThanOrEqualTo(tester.getRect(find.text('Record commands')).top),
    );
    expect(tester.takeException(), isNull);
  });
}
