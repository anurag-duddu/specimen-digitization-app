import 'dart:io';

import 'package:app_links/app_links.dart';

import 'email_link_source.dart';

/// Creates mobile link input after binding setup and before async startup.
///
/// The application owns the returned source and must close it on disposal.
/// URI validation remains in the sign-in controller. Desktop keeps its existing
/// behavior. Startup creates this before asynchronous Firebase initialization
/// so a cold or warm delivery can wait for the sign-in controller.
EmailLinkSource? createNativeEmailLinkSource() {
  if (!Platform.isAndroid && !Platform.isIOS) return null;
  final links = AppLinks();
  return BufferedEmailLinkSource(
    initialLink: links.getInitialLink,
    incomingLinks: links.uriLinkStream,
  );
}
