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
  final int iris = UiColor.light.accent.toARGB32();
  final int obsidian = UiColor.light.onAccent.toARGB32();

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
      bool hasObsidian = false;
      bool rejected = false;
      for (final image.Pixel pixel in decoded!) {
        if (pixel.a < 128) continue;
        hasIris = hasIris || _near(pixel, iris);
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
      final bool monochrome =
          file.path.contains('mark-mono') || file.path.contains('foreground');
      if (background) {
        final bool dark =
            file.path.contains('night') || file.path.contains('dark');
        final int ground = (dark ? UiColor.dark.ground : UiColor.light.ground)
            .toARGB32();
        expect(_near(decoded.getPixel(0, 0), ground), isTrue);
      } else {
        expect(hasObsidian, isTrue, reason: 'Pin must use current Obsidian');
        if (!monochrome) {
          expect(hasIris, isTrue, reason: 'Icon must use current Iris');
        }
      }
    });
  }

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
      contains(hex(iris)),
    );
    expect(
      File('android/app/src/main/res/values/colors.xml').readAsStringSync(),
      contains(hex(iris)),
    );
    expect(
      File('assets/brand/pin.svg').readAsStringSync(),
      contains(hex(iris)),
    );
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
