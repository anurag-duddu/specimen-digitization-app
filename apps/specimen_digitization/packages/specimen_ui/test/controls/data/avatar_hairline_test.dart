// `UiAvatar` and `UiHairline` are the two smallest entries of the data
// family. Neither is interactive, so the control contract does not apply:
// what they owe is a name that stands alone, initials that are taken rather
// than manufactured, and a rule that separates without pretending to be a
// boundary.

import 'dart:typed_data';

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../../harness/control_contract.dart';

/// A one pixel image, so the image path is exercised without a fixture file.
final Uint8List _onePixel = Uint8List.fromList(<int>[
  0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A, 0x00, 0x00, 0x00, 0x0D,
  0x49, 0x48, 0x44, 0x52, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01,
  0x08, 0x06, 0x00, 0x00, 0x00, 0x1F, 0x15, 0xC4, 0x89, 0x00, 0x00, 0x00,
  0x0A, 0x49, 0x44, 0x41, 0x54, 0x78, 0x9C, 0x63, 0x00, 0x01, 0x00, 0x00,
  0x05, 0x00, 0x01, 0x0D, 0x0A, 0x2D, 0xB4, 0x00, 0x00, 0x00, 0x00, 0x49,
  0x45, 0x4E, 0x44, 0xAE, 0x42, 0x60, 0x82,
]);

void main() {
  group('UiAvatar', () {
    testWidgets('the person name is the whole of the semantics', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        uiHarness(child: const UiAvatar(name: 'Ana Ruiz')),
      );
      await tester.pumpAndSettle();
      expect(find.bySemanticsLabel('Ana Ruiz'), findsOneWidget);
      expect(
        find.text('AR'),
        findsOneWidget,
        reason: 'the disc shows initials and the label says who they are',
      );
    });

    testWidgets('initials are taken, never upper cased', (
      WidgetTester tester,
    ) async {
      expect(UiAvatarStyle.initialsOf('Ana Ruiz'), 'AR');
      expect(UiAvatarStyle.initialsOf('ana ruiz'), 'ar');
      expect(
        UiAvatarStyle.initialsOf('Mei'),
        'M',
        reason: 'one word gives one initial, not a doubled letter',
      );
      expect(UiAvatarStyle.initialsOf('Ana Maria Ruiz'), 'AR');
      expect(UiAvatarStyle.initialsOf('  Ana   Ruiz  '), 'AR');
      expect(UiAvatarStyle.initialsOf(''), '');
      expect(
        UiAvatarStyle.initialsOf('Aleksandr Ivanov'),
        'AI',
        reason:
            '09 section 11 rejects upper case outside the unit role, so the '
            'characters are taken as the person wrote them',
      );
    });

    testWidgets('the two sizes are 32 and 40', (WidgetTester tester) async {
      expect(
        UiAvatarSize.values.map((UiAvatarSize s) => s.diameter),
        <double>[32, 40],
      );
      for (final UiAvatarSize size in UiAvatarSize.values) {
        await tester.pumpWidget(
          uiHarness(child: UiAvatar(name: 'Ana Ruiz', size: size)),
        );
        await tester.pumpAndSettle();
        expect(
          tester.getSize(find.byType(UiAvatar)),
          Size.square(size.diameter),
        );
      }
    });

    testWidgets('the disc is ink at 8 percent in both modes', (
      WidgetTester tester,
    ) async {
      for (final Brightness mode in Brightness.values) {
        final UiThemeData ui = mode == Brightness.dark
            ? UiThemeData.dark()
            : UiThemeData.light();
        final UiAvatarStyle style = UiAvatarStyle.resolve(
          ui,
          UiAvatarSize.medium,
        );
        expect(style.fill, ui.color.stateLayer(ui.color.hoverOpacity));
        expect(style.initials.fontSize, ui.type.label.fontSize);
      }
    });

    testWidgets('an image takes the disc, and a broken one falls back to the '
        'initials', (WidgetTester tester) async {
      await tester.pumpWidget(
        uiHarness(
          child: UiAvatar(
            name: 'Ana Ruiz',
            image: MemoryImage(_onePixel),
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.byType(Image), findsOneWidget);
      expect(find.text('AR'), findsNothing);
      expect(find.bySemanticsLabel('Ana Ruiz'), findsOneWidget);

      await tester.pumpWidget(
        uiHarness(
          child: UiAvatar(
            name: 'Ana Ruiz',
            image: MemoryImage(Uint8List.fromList(<int>[1, 2, 3])),
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(
        find.text('AR'),
        findsOneWidget,
        reason:
            'a photograph that will not decode is a fact about the record, '
            'so the disc says who it is rather than leaving a hole',
      );
      expect(tester.takeException(), isNull);
    });

    testWidgets('it builds right to left and at 200 percent text', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        uiHarness(
          textDirection: TextDirection.rtl,
          textScaler: const TextScaler.linear(2),
          child: const UiAvatar(name: 'Ana Ruiz'),
        ),
      );
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
    });

    testWidgets('nothing about it animates, in either motion mode', (
      WidgetTester tester,
    ) async {
      for (final bool reduced in <bool>[false, true]) {
        await tester.pumpWidget(
          uiHarness(
            disableAnimations: reduced,
            child: const UiAvatar(name: 'Ana Ruiz'),
          ),
        );
        await tester.pump();
        expect(tester.binding.transientCallbackCount, 0);
      }
    });
  });

  group('UiHairline', () {
    testWidgets('it is one dp in the hairline role, both ways round', (
      WidgetTester tester,
    ) async {
      final UiThemeData ui = UiThemeData.light();
      await tester.pumpWidget(
        uiHarness(
          child: const SizedBox(
            width: 200,
            height: 200,
            child: Column(
              children: <Widget>[
                UiHairline(),
                Expanded(child: Row(children: <Widget>[UiHairline.vertical()])),
              ],
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      final List<Size> sizes = tester
          .widgetList<UiHairline>(find.byType(UiHairline))
          .map((UiHairline rule) => tester.getSize(find.byWidget(rule)))
          .toList();
      expect(sizes[0].height, ui.shape.stroke.hairline);
      expect(sizes[0].width, 200, reason: 'a rule spans what it is given');
      expect(sizes[1].width, ui.shape.stroke.hairline);
      expect(
        tester
            .widgetList<ColoredBox>(
              find.descendant(
                of: find.byType(UiHairline),
                matching: find.byType(ColoredBox),
              ),
            )
            .map((ColoredBox box) => box.color)
            .toSet(),
        <Color>{ui.color.hairline},
      );
    });

    testWidgets('the inset is directional, so it flips under right to left', (
      WidgetTester tester,
    ) async {
      final Map<TextDirection, double> lefts = <TextDirection, double>{};
      for (final TextDirection direction in TextDirection.values) {
        await tester.pumpWidget(
          uiHarness(
            textDirection: direction,
            child: const SizedBox(
              width: 200,
              child: UiHairline(indent: 40),
            ),
          ),
        );
        await tester.pumpAndSettle();
        lefts[direction] = tester
            .getTopLeft(
              find.descendant(
                of: find.byType(UiHairline),
                matching: find.byType(ColoredBox),
              ),
            )
            .dx;
      }
      expect(
        lefts[TextDirection.ltr],
        isNot(lefts[TextDirection.rtl]),
        reason: 'a rule that clears a leading slot clears it in both scripts',
      );
    });

    testWidgets('it says nothing to a screen reader', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        uiHarness(child: const SizedBox(width: 200, child: UiHairline())),
      );
      await tester.pumpAndSettle();
      expect(
        find.descendant(
          of: find.byType(UiHairline),
          matching: find.byType(ExcludeSemantics),
        ),
        findsOneWidget,
      );
    });
  });
}
