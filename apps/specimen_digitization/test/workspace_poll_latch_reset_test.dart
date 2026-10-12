// The poll a return to the app owes belongs to the session that returned.
// Signing out forgets it, so the next account never inherits it.

import 'dart:async';

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/workspace.dart';

import 'widget_test.dart' show TestSession;
import 'workspace_queue_refresh_test.dart'
    show KeysetRepository, move, row, started;

void main() {
  testWidgets('resetSession clears an owed poll', (WidgetTester tester) async {
    final KeysetRepository repository = KeysetRepository(<Specimen>[row('a')]);
    final TestSession session = TestSession();
    final WorkspaceController controller = await started(
      tester,
      repository,
      session,
    );
    try {
      // A poll in flight blocks the owed one.
      final Completer<void> slow = Completer<void>();
      repository.gates[''] = slow;
      await tester.pump(queuePollInterval);
      move(tester, <AppLifecycleState>[
        AppLifecycleState.inactive,
        AppLifecycleState.hidden,
        AppLifecycleState.paused,
        AppLifecycleState.hidden,
        AppLifecycleState.inactive,
        AppLifecycleState.resumed,
      ]);
      await tester.pump();
      expect(controller.pollOwed, isTrue);

      controller.resetSession();
      expect(controller.pollOwed, isFalse);
      final int asked = repository.pageReads;
      slow.complete();
      await tester.pump();
      await tester.pump();
      expect(repository.pageReads, asked, reason: 'nothing is owed any more');
    } finally {
      controller.dispose();
      await session.controller.close();
    }
  });
}
