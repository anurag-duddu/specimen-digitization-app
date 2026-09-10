import 'auth.dart';
import 'connection_config.dart';
import 'models.dart';

const collectionPendingMessage =
    'Collection access is still being set up. Please try again later or contact your administrator.';

class ProductionStartup {
  const ProductionStartup({this.session, this.repository, this.setupMessage});
  final SessionAccess? session;
  final SpecimenRepository? repository;
  final String? setupMessage;
}

Future<ProductionStartup> initializeProduction({
  required bool firebaseConfigured,
  required ConnectionConfig config,
  required bool web,
  required Future<SessionAccess> Function() initializeSession,
  required Future<void> Function() activateAppCheck,
  required SpecimenRepository Function(Uri, SessionAccess) createRepository,
}) async {
  if (!firebaseConfigured) {
    return const ProductionStartup(
      setupMessage:
          'This verification build has no live Firebase configuration. Configure Firebase Authentication and the application API to connect to a collection.',
    );
  }
  final SessionAccess session;
  try {
    session = await initializeSession();
  } catch (_) {
    return const ProductionStartup(
      setupMessage:
          'Sign-in could not be set up. Please try again later or contact your administrator.',
    );
  }
  // Authentication and explicit email verification do not depend on the API.
  // Keep App Check and all repository work behind valid backend configuration.
  if (config.apiUrl.isEmpty) {
    return ProductionStartup(
      session: session,
      setupMessage: collectionPendingMessage,
    );
  }
  try {
    final uri = config.validate(web: web);
    await activateAppCheck();
    return ProductionStartup(
      session: session,
      repository: createRepository(uri, session),
    );
  } catch (_) {
    return ProductionStartup(
      session: session,
      setupMessage: collectionPendingMessage,
    );
  }
}
