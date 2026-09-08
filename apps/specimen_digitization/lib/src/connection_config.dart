/// Public build configuration only. Firebase identity is supplied separately by
/// the approved build pipeline; no provider credentials belong in this client.
class ConnectionConfig {
  const ConnectionConfig({
    required this.apiUrl,
    required this.siteKey,
    this.synthetic = false,
    this.authEmulatorHost = '',
  });
  final String apiUrl;
  final String siteKey;
  final bool synthetic;
  final String authEmulatorHost;

  Uri validate({required bool web}) {
    final uri = Uri.tryParse(apiUrl);
    final local =
        uri != null &&
        ['localhost', '127.0.0.1', '::1', '10.0.2.2'].contains(uri.host);
    if (uri == null ||
        uri.host.isEmpty ||
        uri.userInfo.isNotEmpty ||
        uri.hasQuery ||
        uri.hasFragment ||
        (uri.scheme != 'https' &&
            !(synthetic && local && uri.scheme == 'http'))) {
      throw const FormatException(
        'The collection service address is missing or invalid. Ask your administrator to check the approved connection configuration.',
      );
    }
    if (synthetic && !local) {
      throw const FormatException('Synthetic access requires a local API.');
    }
    if (!synthetic && authEmulatorHost.isNotEmpty) {
      throw const FormatException(
        'Live collection access cannot use an authentication emulator.',
      );
    }
    if (!synthetic && web && siteKey.trim().isEmpty) {
      throw const FormatException(
        'App verification is not configured. Ask your administrator to configure App Check for this website.',
      );
    }
    return uri;
  }
}
