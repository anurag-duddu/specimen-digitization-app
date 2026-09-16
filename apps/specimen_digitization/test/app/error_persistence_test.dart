// No error is taken away by a background process, and every persistent error
// can be dismissed by the person who read it (pass criterion 9.5).
//
// The screen banner used to be cleared by the next successful refresh, and the
// next successful refresh is usually the twenty second poll, which nobody
// asked for. A poll may not decide that a message has been read.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:specimen_digitization/main.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/workspace.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../widget_test.dart' show TestRepository, TestSession;
import '../ui_finders.dart';

/// A collection whose page fails once, then succeeds.
class FlakyRepository extends TestRepository {
  /// True while the next page request should fail.
  bool failNext = false;

  @override
  Future<SpecimenPage> specimenPage(
    CollectionScope scope, {
    Map<String, String> filters = const <String, String>{},
    String? cursor,
  }) async {
    if (failNext) {
      failNext = false;
      throw const ApiFailure(
        'The service could not be reached.',
        code: 'network',
      );
    }
    return super.specimenPage(scope, filters: filters, cursor: cursor);
  }
}

void main() {
  setUp(() => SharedPreferences.setMockInitialValues(<String, Object>{}));

  testWidgets('a quiet poll does not take the banner away', (
    WidgetTester tester,
  ) async {
    final FlakyRepository repository = FlakyRepository();
    final TestSession session = TestSession();
    addTearDown(session.controller.close);
    final WorkspaceController controller = WorkspaceController(
      repository: repository,
      session: session,
    );

    await controller.checkAccess();
    repository.failNext = true;
    await controller.refresh();
    expect(controller.error, isNotNull);

    // The poll answers successfully. The message stays.
    await controller.refresh(quiet: true);
    expect(
      controller.error,
      isNotNull,
      reason: 'a background refresh cleared an error the reviewer may not '
          'have read',
    );

    // A refresh the reviewer asked for does clear it, because they are
    // watching the result.
    await controller.refresh();
    expect(controller.error, isNull);
    controller.dispose();
  });

  testWidgets('the banner offers Dismiss beside its recovery action', (
    WidgetTester tester,
  ) async {
    tester.view.devicePixelRatio = 1;
    tester.view.physicalSize = const Size(1000, 900);
    addTearDown(tester.view.reset);

    final FlakyRepository repository = FlakyRepository()..failNext = true;
    final TestSession session = TestSession();
    addTearDown(session.controller.close);

    await tester.pumpWidget(
      SpecimenDigitizationApp(session: session, repository: repository),
    );
    await tester.pumpAndSettle();

    // The environment band is a `UiBanner` too, so the failure's own band is
    // named rather than counted.
    final Finder band = find.byWidgetPredicate(
      (Widget widget) =>
          widget is UiBanner &&
          widget.message.startsWith('The service could not be reached.'),
      description: 'the failure band',
    );
    expect(band, findsOneWidget);
    // The band carries its recovery action beside the message and a named
    // dismiss control at its end (07 section 11).
    expect(uiButton('Retry'), findsOneWidget);
    expect(uiControl('Dismiss'), findsOneWidget);

    await tester.tap(uiControl('Dismiss'));
    await tester.pumpAndSettle();
    expect(band, findsNothing);
    await tester.pumpWidget(const SizedBox());
  });

  test('the conflict warning cannot be later than the criterion allows', () {
    // Pass criterion 1.4: an open specimen is warned within 30 s of its
    // revision changing. The poll is the only thing that raises it, so the
    // poll interval is the bound, and this is what holds it there.
    expect(queuePollInterval.inSeconds, lessThanOrEqualTo(30));
  });
}
