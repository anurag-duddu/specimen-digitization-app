import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/intake_compute.dart';

void main() {
  testWidgets('intakeRunOffUi completes under fake async without runAsync', (
    tester,
  ) async {
    // Clear any suite-wide pin so binding detection is what we exercise.
    debugIntakeComputeOverride = null;
    addTearDown(() {
      debugIntakeComputeOverride = intakeComputeInProcess;
    });

    expect(
      WidgetsBinding.instance.runtimeType.toString().contains(
        'TestWidgetsFlutterBinding',
      ),
      isTrue,
    );

    var ran = false;
    final int value = await intakeRunOffUi(() {
      ran = true;
      return 7;
    });
    await tester.pump();
    expect(ran, isTrue);
    expect(value, 7);
  });

  test('intakeRunOffUi honors debug override', () async {
    debugIntakeComputeOverride = intakeComputeInProcess;
    var ran = false;
    final int value = await intakeRunOffUi(() {
      ran = true;
      return 42;
    });
    expect(ran, isTrue);
    expect(value, 42);
  });
}
