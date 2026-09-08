import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/main.dart';

void main() {
  testWidgets('shows the configured application identity', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(const SpecimenDigitizationApp());

    expect(find.text('Specimen Digitization'), findsOneWidget);
    expect(
      find.text('Firebase is configured for Web, iOS, and Android.'),
      findsOneWidget,
    );
  });
}
