import 'dart:io';
import 'dart:math' as math;

import 'package:flutter_test/flutter_test.dart';
import 'package:image/image.dart' as image;
import 'package:specimen_ui/specimen_ui.dart';

bool _near(image.Pixel pixel, int value, {int tolerance = 2}) =>
    (pixel.r - ((value >> 16) & 255)).abs() <= tolerance &&
    (pixel.g - ((value >> 8) & 255)).abs() <= tolerance &&
    (pixel.b - (value & 255)).abs() <= tolerance;

bool _rejectedYellowGreen(image.Pixel pixel) {
  if (pixel.a < 128) return false;
  final double r = pixel.r.toDouble();
  final double g = pixel.g.toDouble();
  final double b = pixel.b.toDouble();
  // Exclude neutrals and the approved purple/amber families cheaply before
  // calculating hue. This also catches antialiased relatives of old seeds.
  if (r < 64 || g < 64 || b >= math.min(r, g) * 0.7) return false;
  final double high = math.max(r, math.max(g, b));
  final double low = math.min(r, math.min(g, b));
  final double delta = high - low;
  final double hue = high == r
      ? 60 * ((g - b) / delta)
      : 60 * ((b - r) / delta + 2);
  return hue >= 55 && hue <= 95;
}

List<File> _rasters() => <File>[
  for (final String path in <String>[
    'assets/brand',
    'android/app/src/main/res',
    'ios/Runner/Assets.xcassets',
    'web/icons',
  ])
    ...Directory(path)
        .listSync(recursive: true)
        .whereType<File>()
        .where((File file) => file.path.endsWith('.png')),
  File('web/favicon.png'),
]..sort((File a, File b) => a.path.compareTo(b.path));

void main() {
  final List<File> rasters = _rasters();
  const UiBrandColors brand = UiBrandColors.light;
  final int iris = brand.iris.toARGB32();
  final int amber = brand.amber.toARGB32();
  final int obsidian = brand.obsidian.toARGB32();
  final int paper = brand.paper.toARGB32();

  test('asset inventory covers every native and browser generation target', () {
    expect(rasters.length, greaterThan(60));
    for (final String expected in <String>[
      'assets/brand/icon-1024.png',
      'assets/brand/splash-mark-android12-1024.png',
      'android/app/src/main/res/mipmap-xxxhdpi/ic_launcher.png',
      'ios/Runner/Assets.xcassets/AppIcon.appiconset/Icon-App-1024x1024@1x.png',
      'web/favicon.png',
      'web/icons/Icon-maskable-512.png',
    ]) {
      expect(rasters.map((File f) => f.path), contains(expected));
    }
  });

  for (final File file in rasters) {
    test('${file.path} has the current brand and no rejected hue', () {
      final image.Image? decoded = image.decodePng(file.readAsBytesSync());
      expect(decoded, isNotNull);
      bool hasIris = false;
      bool hasAmber = false;
      bool hasObsidian = false;
      bool rejected = false;
      for (final image.Pixel pixel in decoded!) {
        if (pixel.a < 128) continue;
        // Small icons sample the approved gradient between its exact stops.
        hasIris = hasIris || (pixel.b > pixel.r + 40 && pixel.b > pixel.g + 50);
        hasAmber =
            hasAmber ||
            (pixel.r > pixel.b + 40 &&
                pixel.r > pixel.g + 20 &&
                pixel.g > pixel.b + 10);
        hasObsidian = hasObsidian || _near(pixel, obsidian);
        if (_rejectedYellowGreen(pixel)) {
          rejected = true;
          break;
        }
      }
      expect(
        rejected,
        isFalse,
        reason: 'Regenerate ${file.path} from current tokens',
      );
      final bool background = file.path.toLowerCase().contains('background');
      final bool monochrome = file.path.contains('mark-mono');
      if (background) {
        final bool dark =
            file.path.contains('night') || file.path.contains('dark');
        final int ground = (dark ? UiColor.dark.ground : UiColor.light.ground)
            .toARGB32();
        expect(_near(decoded.getPixel(0, 0), ground), isTrue);
      } else {
        expect(
          hasObsidian,
          isTrue,
          reason: 'The ribbons must use current Obsidian',
        );
        if (!monochrome) {
          expect(hasIris, isTrue, reason: 'The fold must retain its Iris end');
          expect(
            hasAmber,
            isTrue,
            reason: 'The fold must retain its Amber bend',
          );
        }
        // Check actual silhouette anatomy in each generated target: two outer
        // ribbons, the open aperture, and both gaps. A disc or a pin cannot
        // satisfy these independent probes. At tiny icon sizes the colour
        // checks above cover the resampled gradient instead of subpixel gaps.
        if (decoded.width >= 48) {
          final double frame = file.path.contains('foreground')
              ? 0.66
              : file.path.toLowerCase().contains('android12')
              ? 2 / 3
              : file.path.toLowerCase().contains('maskable')
              ? 0.8
              : 1;
          image.Pixel at(double x, double y) => decoded.getPixel(
            ((0.5 + (x / 512 - 0.5) * frame) * decoded.width).floor(),
            ((0.5 + (y / 512 - 0.5) * frame) * decoded.height).floor(),
          );
          if (decoded.width >= 128) {
            final bool primary =
                file.path.endsWith('/mark-1024.png') || monochrome;
            final image.Pixel tip = at(390, 153);
            expect(
              _near(tip, primary ? obsidian : amber, tolerance: 24),
              isTrue,
              reason: primary
                  ? 'The primary fold ends in Obsidian'
                  : 'The owner app-icon fold ends in Amber',
            );
          }
          for (final (double, double) point in <(double, double)>[
            (81, 282),
            (271, 117),
            (231, 372),
            (431, 272),
          ]) {
            final image.Pixel pixel = at(point.$1, point.$2);
            expect(pixel.a, greaterThan(220), reason: 'Ribbon at $point');
            expect(pixel.r, lessThan(90), reason: 'Obsidian ribbon at $point');
            expect(pixel.g, lessThan(90));
            expect(pixel.b, lessThan(90));
          }
          for (final (double, double) point in <(double, double)>[
            (331, 302),
            (241, 175),
            (241, 257),
          ]) {
            final image.Pixel pixel = at(point.$1, point.$2);
            expect(
              pixel.a < 32 || _near(pixel, paper, tolerance: 20),
              isTrue,
              reason: 'Open aperture or ribbon gap at $point',
            );
          }
        }
      }
    });
  }

  test(
    'canonical SVG carries three ribbons and the approved fold gradient',
    () {
      final String source = File(
        'assets/brand/specimen-mark.svg',
      ).readAsStringSync();
      expect(RegExp(r'<path\b').allMatches(source), hasLength(3));
      for (final String id in <String>['upper', 'folded', 'lower']) {
        expect(source, contains('id="$id"'));
      }
      expect(source, contains('fill-rule="evenodd"'));
      expect(source, contains('gradientUnits="userSpaceOnUse"'));
      expect(source, contains('id="fold-app-icon"'));
      expect(source, contains('stop-color="#7B61FF"'));
      expect(source, contains('stop-color="#F5A45B"'));
      expect(source, contains('stop-color="#0E0E11"'));
      expect(File('assets/brand/pin.svg').existsSync(), isFalse);
    },
  );

  test('launcher icons retain opaque Paper and the foreground safe circle', () {
    for (final String path in <String>[
      'assets/brand/icon-1024.png',
      'assets/brand/icon-maskable-1024.png',
      'ios/Runner/Assets.xcassets/AppIcon.appiconset/Icon-App-1024x1024@1x.png',
      'android/app/src/main/res/mipmap-xxxhdpi/ic_launcher.png',
      'web/icons/Icon-maskable-512.png',
    ]) {
      final image.Image decoded = image.decodePng(
        File(path).readAsBytesSync(),
      )!;
      expect(decoded.every((image.Pixel pixel) => pixel.a == 255), isTrue);
      expect(_near(decoded.getPixel(0, 0), paper), isTrue, reason: path);
    }
    for (final String path in <String>[
      'assets/brand/icon-foreground-1024.png',
      'assets/brand/splash-mark-android12-1024.png',
    ]) {
      final image.Image decoded = image.decodePng(
        File(path).readAsBytesSync(),
      )!;
      expect(decoded.getPixel(0, 0).a, 0);
      double farthestSquared = 0;
      for (final image.Pixel pixel in decoded) {
        if (pixel.a < 128) continue;
        final double dx = (pixel.x + 0.5) / decoded.width - 0.5;
        final double dy = (pixel.y + 0.5) / decoded.height - 0.5;
        farthestSquared = math.max(farthestSquared, dx * dx + dy * dy);
      }
      expect(farthestSquared, lessThan(1 / 9), reason: path);
    }
  });

  test('native and browser source colours agree with Flutter', () {
    String hex(int value) =>
        '#${(value & 0xFFFFFF).toRadixString(16).toUpperCase().padLeft(6, '0')}';
    final String light = hex(UiColor.light.ground.toARGB32());
    final String dark = hex(UiColor.dark.ground.toARGB32());
    for (final String path in <String>[
      'flutter_native_splash.yaml',
      'web/index.html',
    ]) {
      final String source = File(path).readAsStringSync().toUpperCase();
      expect(source, contains(light));
      expect(source, contains(dark));
    }
    expect(
      File('flutter_launcher_icons.yaml').readAsStringSync(),
      contains(light),
    );
    expect(
      File('android/app/src/main/res/values/colors.xml').readAsStringSync(),
      contains(light),
    );
    final String vector = File(
      'assets/brand/specimen-mark.svg',
    ).readAsStringSync();
    for (final int seed in <int>[iris, amber, obsidian]) {
      expect(vector, contains(hex(seed)));
    }
    expect(File('web/manifest.json').readAsStringSync(), contains(light));
  });

  test('launcher generation preserves Xcode boolean build settings', () {
    final String project = File(
      'ios/Runner.xcodeproj/project.pbxproj',
    ).readAsStringSync();
    final Iterable<RegExpMatch> flags = RegExp(
      r'ASSETCATALOG_COMPILER_GENERATE_SWIFT_ASSET_SYMBOL_EXTENSIONS = ([^;]+);',
    ).allMatches(project);
    expect(flags, isNotEmpty);
    for (final RegExpMatch flag in flags) {
      expect(<String>['YES', 'NO'], contains(flag.group(1)));
    }
  });
}
