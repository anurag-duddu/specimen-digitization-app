/// Supported embedding boundary for the production screens and router.
///
/// The component workbench supplies isolated repositories and device hooks;
/// layouts, navigation, review safeguards and shell remain application-owned.
/// This library does not initialize Firebase or import any preview fixtures.
library;

export 'src/app/app_router.dart';
export 'src/app/routes.dart' show AppRoutes;
export 'src/app/session_notifier.dart' show AppSessionNotifier;
export 'src/auth.dart' show SessionAccess;
export 'src/capture/capture_camera.dart'
    show CaptureCameraUnavailable, CaptureUnavailable;
export 'src/models.dart';
export 'src/screens/intake/bulk_intake_repository.dart';
export 'src/screens/intake/bulk_intake_screen.dart' show BulkIntakeScreen;
export 'src/screens/queue/queue_screen.dart' show QueueScreen;
export 'src/screens/queue/workbench_screen.dart' show WorkbenchScreen;
export 'src/workbench.dart' show ReviewWorkbench;
export 'src/workspace.dart'
    show WorkspaceController, WorkspaceScope, encodeCollectionKey;
