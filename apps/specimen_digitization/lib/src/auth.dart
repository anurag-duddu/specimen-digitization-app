import 'dart:async';
import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart' show TextInputAction, TextInputType;
import 'package:flutter/widgets.dart';
import 'package:http/http.dart' as http;
import 'package:specimen_ui/specimen_ui.dart';
import 'api_repository.dart';
import 'models.dart';
import 'magic_link.dart';
import 'magic_link_screen.dart';
import 'firebase_google_sign_in.dart';
import 'google_sign_in.dart';
import 'administrator_contact.dart';
import 'app/auth_layout.dart';
import 'widgets/caveat_text.dart';

const emailLinkAndroidPackageName = 'org.fieldmuseum.specimen_digitization';
const emailLinkIosBundleId = 'org.fieldmuseum.specimenDigitization';

/// Builds the hosted email-link request for the platform making the request.
///
/// Firebase chooses its default Hosting link domain because [linkDomain] stays
/// unset. [emailLinkReturnUrl] remains the continue/fallback destination. Web
/// keeps the existing hosted flow, while each mobile platform names the app
/// registered for that platform so the link can return to the installed app.
ActionCodeSettings emailLinkActionCodeSettings({
  bool? web,
  TargetPlatform? platform,
}) {
  final bool isWeb = web ?? kIsWeb;
  final TargetPlatform target = platform ?? defaultTargetPlatform;
  return ActionCodeSettings(
    url: emailLinkReturnUrl,
    handleCodeInApp: true,
    androidPackageName: !isWeb && target == TargetPlatform.android
        ? emailLinkAndroidPackageName
        : null,
    iOSBundleId: !isWeb && target == TargetPlatform.iOS
        ? emailLinkIosBundleId
        : null,
  );
}

abstract class SessionAccess {
  Stream<bool> get changes;
  bool get signedIn;
  String get userId;
  String get displayName;
  Future<String?> token();
  Future<void> signIn(String email, String password);
  Future<void> signOut();
  Future<void> resetPassword(String email);
}

abstract class VerifiedEmailAccess {
  bool get emailVerified;
  Future<void> refreshVerification();
  Future<void> sendVerification();
}

class FirebaseSession
    implements
        SessionAccess,
        VerifiedEmailAccess,
        EmailLinkAccess,
        GoogleSignInAccess {
  FirebaseSession(this.auth, {GoogleFirebaseSignInAdapter? google})
    : _google =
          google ??
          GoogleFirebaseSignInAdapter(
            auth: auth,
            enabled: const bool.fromEnvironment(
              'SPECIMEN_GOOGLE_SIGN_IN_ENABLED',
            ),
            nativeConfigured: const bool.fromEnvironment(
              'SPECIMEN_GOOGLE_NATIVE_ENABLED',
            ),
          );
  final FirebaseAuth auth;
  final GoogleFirebaseSignInAdapter _google;
  final _googleChanges = StreamController<bool>.broadcast();
  bool _googlePending = false;
  bool _googleQuarantined = false;
  int _googleEpoch = 0;
  bool get _sessionBlocked => _googlePending || _googleQuarantined;

  // Firebase publishes userChanges before a provider Future completes. Keep
  // those events private until the selected account has been checked.
  @override
  Stream<bool> get changes => Stream<bool>.multi((controller) {
    final raw = auth.userChanges().listen((_) {
      if (!_sessionBlocked) controller.add(signedIn);
    }, onError: controller.addError);
    final checked = _googleChanges.stream.listen((_) {
      controller.add(signedIn);
    });
    controller.onCancel = () async {
      await raw.cancel();
      await checked.cancel();
    };
  }, isBroadcast: true);
  @override
  bool get signedIn => !_sessionBlocked && auth.currentUser != null;
  @override
  String get userId => _sessionBlocked ? '' : auth.currentUser?.uid ?? '';
  @override
  String get displayName =>
      _sessionBlocked ? '' : auth.currentUser?.email ?? 'Signed in';

  @override
  bool get googleSignInAvailable => _google.available;

  @override
  Future<GoogleSignInOutcome> signInWithGoogle({String? emailHint}) async {
    if (!googleSignInAvailable) {
      throw const GoogleSignInFailure(GoogleSignInFailureKind.unavailable);
    }
    if (_googlePending) {
      throw const GoogleSignInFailure(GoogleSignInFailureKind.accountConflict);
    }
    if (_googleQuarantined) {
      // Retry cleanup on a later gesture. Start the provider only on the next
      // gesture, because awaiting sign-out here would lose popup activation.
      try {
        await _signOutProviders();
        _googleQuarantined = auth.currentUser != null;
      } catch (_) {
        _googleQuarantined = true;
      }
      _googleChanges.add(signedIn);
      throw const GoogleSignInFailure(GoogleSignInFailureKind.unknown);
    }
    if (auth.currentUser != null) {
      throw const GoogleSignInFailure(GoogleSignInFailureKind.accountConflict);
    }
    final epoch = ++_googleEpoch;
    _googlePending = true;
    _googleQuarantined = true;
    var accepted = false;
    try {
      // Invoke the popup synchronously in the original submit gesture.
      final result = await _google.authenticate(emailHint);
      if (epoch != _googleEpoch) {
        throw const GoogleSignInFailure(GoogleSignInFailureKind.unknown);
      }
      if (result == null) return GoogleSignInOutcome.cancelled;
      final returned = result.user;
      final current = auth.currentUser;
      if (returned == null ||
          current == null ||
          returned.uid.isEmpty ||
          returned.uid != current.uid ||
          normalizedStaffEmail(returned.email ?? '') == null ||
          normalizedStaffEmail(returned.email ?? '') !=
              normalizedStaffEmail(current.email ?? '')) {
        throw const GoogleSignInFailure(
          GoogleSignInFailureKind.accountNotAllowed,
        );
      }
      if (!returned.emailVerified || !current.emailVerified) {
        throw const GoogleSignInFailure(
          GoogleSignInFailureKind.unverifiedEmail,
        );
      }
      accepted = true;
      _googleQuarantined = false;
      return GoogleSignInOutcome.signedIn;
    } finally {
      if (!accepted) {
        try {
          await _signOutProviders();
          _googleQuarantined = auth.currentUser != null;
        } catch (_) {
          // A failed cleanup must never expose the rejected identity.
          _googleQuarantined = true;
        }
      }
      _googlePending = false;
      _googleChanges.add(signedIn);
    }
  }

  Future<void> _signOutProviders() async {
    try {
      await auth.signOut();
    } finally {
      try {
        await _google.signOut();
      } catch (_) {
        // Firebase owns app access. The native bridge also clears its cached
        // account before the next attempt if SDK cleanup failed here.
      }
    }
  }

  @override
  Future<String?> token() async {
    _requireStaffAccess();
    return auth.currentUser?.getIdToken();
  }

  /// A newly minted sign-in token, for a request the server refused or for
  /// the access check that follows a refusal.
  Future<String?> freshToken() async {
    _requireStaffAccess();
    return auth.currentUser?.getIdToken(true);
  }

  void _requireStaffAccess() {
    if (!staffEmailAllowed) {
      throw const ApiFailure(
        staffEmailMessage,
        code: 'staff_email_required',
        status: 403,
      );
    }
    if (!emailVerified) {
      throw const ApiFailure(
        'Verify your email address before opening a collection.',
        code: 'email_unverified',
        status: 403,
      );
    }
  }

  @override
  bool get emailVerified =>
      !_sessionBlocked && auth.currentUser?.emailVerified == true;
  bool get staffEmailAllowed =>
      !_sessionBlocked &&
      normalizedStaffEmail(auth.currentUser?.email ?? '') != null;
  @override
  Future<void> refreshVerification() async {
    await auth.currentUser?.reload();
    await auth.currentUser?.getIdToken(true);
  }

  @override
  Future<void> sendVerification() async {
    final user = auth.currentUser;
    if (user == null) throw StateError('Sign in again.');
    await user.sendEmailVerification();
  }

  @override
  bool isSignInWithEmailLink(String link) => auth.isSignInWithEmailLink(link);

  @override
  Future<void> sendSignInLink(String email) async {
    final normalized = normalizedStaffEmail(email);
    if (normalized == null) throw const FormatException(staffEmailMessage);
    await auth.sendSignInLinkToEmail(
      email: normalized,
      actionCodeSettings: emailLinkActionCodeSettings(),
    );
  }

  @override
  Future<void> completeEmailLink(String email, String link) async {
    if (_sessionBlocked) {
      throw const GoogleSignInFailure(GoogleSignInFailureKind.accountConflict);
    }
    final normalized = normalizedStaffEmail(email);
    if (normalized == null) throw const FormatException(staffEmailMessage);
    if (!auth.isSignInWithEmailLink(link)) {
      throw FirebaseAuthException(code: 'invalid-action-code');
    }
    await auth.signInWithEmailLink(email: normalized, emailLink: link);
  }

  @override
  Future<void> signIn(String email, String password) async =>
      throw UnsupportedError('Use an email sign-in link.');
  @override
  Future<void> resetPassword(String email) async =>
      throw UnsupportedError('Use an email sign-in link.');
  @override
  Future<void> signOut() async {
    _googleEpoch++;
    await _signOutProviders();
    _googleQuarantined = auth.currentUser != null;
    _googleChanges.add(signedIn);
  }
}

class SignInScreen extends StatelessWidget {
  const SignInScreen({super.key, required this.session, this.magicLink});
  final SessionAccess session;
  final MagicLinkController? magicLink;

  @override
  Widget build(BuildContext context) {
    if (session is EmailLinkAccess) {
      final google = session is GoogleSignInAccess
          ? session as GoogleSignInAccess
          : null;
      return MagicLinkSignInScreen(
        access: session as EmailLinkAccess,
        controller: magicLink,
        google: google?.googleSignInAvailable == true ? google : null,
      );
    }
    return _FixtureSignInScreen(session: session);
  }
}

// Legacy SessionAccess adapters remain for isolated local fixtures/tests only.
// FirebaseSession uses email links and an optional configured Google provider.
class _FixtureSignInScreen extends StatefulWidget {
  const _FixtureSignInScreen({required this.session});
  final SessionAccess session;
  @override
  State<_FixtureSignInScreen> createState() => _SignInScreenState();
}

class _SignInScreenState extends State<_FixtureSignInScreen> {
  final TextEditingController _email = TextEditingController();
  final TextEditingController _password = TextEditingController();
  String? _emailError;
  String? _passwordError;
  String? _message;
  bool _busy = false;
  bool _obscure = true;
  bool _resetting = false;

  bool get _fixture => widget.session is LocalFixtureSession;

  @override
  void dispose() {
    _email.dispose();
    _password.dispose();
    super.dispose();
  }

  /// The inline errors for what is in the fields now.
  ///
  /// Fires on submit rather than on every keystroke, and states the rule
  /// positively (02 section 4.10).
  bool _validate({required bool reset}) {
    final String? email = _email.text.contains('@')
        ? null
        : 'Enter an address like name@fieldmuseum.org.';
    final String? password = reset || _password.text.isNotEmpty
        ? null
        : _fixture
        ? 'Enter the fixture token.'
        : 'Enter your password.';
    setState(() {
      _emailError = email;
      _passwordError = password;
    });
    return email == null && password == null;
  }

  Future<void> _submit({bool reset = false}) async {
    if (!_validate(reset: reset)) return;
    setState(() {
      _busy = true;
      _resetting = reset;
      _message = null;
    });
    try {
      if (reset) {
        await widget.session.resetPassword(_email.text);
        if (mounted) {
          setState(
            () => _message =
                'If this account is eligible, a password reset email will arrive shortly.',
          );
        }
      } else {
        await widget.session.signIn(_email.text, _password.text);
      }
    } catch (error) {
      if (mounted) {
        setState(
          () => _message = _fixture && error is ApiFailure
              ? error.message
              : authErrorMessage(error, reset: reset),
        );
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    return UiScaffold(
      body: AutofillGroup(
        child: AuthLayout(
          title: _fixture ? 'Test data access' : 'Sign in to your collection',
          children: <Widget>[
            if (_fixture)
              const CaveatText(
                label:
                    'Test data only. This email is a test label, not a '
                    'museum account.',
                why:
                    'Access needs a fixture token the local server accepts. '
                    'There is no live sign-in and no live model processing.',
              )
            else
              Text(
                'Use the account provided by your museum. Collection access '
                'is checked by the server.',
                style: ui.type.body.copyWith(color: ui.color.inkSecondary),
              ),
            SizedBox(height: ui.space.s6),
            UiField(
              label: 'Email address',
              controller: _email,
              errorText: _emailError,
              enabled: !_busy,
              keyboardType: TextInputType.emailAddress,
              autocorrect: false,
              textInputAction: TextInputAction.next,
            ),
            SizedBox(height: ui.space.s4),
            UiField(
              label: _fixture ? 'Fixture token' : 'Password',
              controller: _password,
              errorText: _passwordError,
              enabled: !_busy,
              obscureText: _obscure,
              onSubmitted: (_) {
                if (!_busy) unawaited(_submit());
              },
              trailing: UiIconButton(
                icon: _obscure ? UiIcons.show : UiIcons.unreadable,
                semanticsLabel: _obscure ? 'Show password' : 'Hide password',
                tooltip: _obscure ? 'Show password' : 'Hide password',
                onPressed: () => setState(() => _obscure = !_obscure),
              ),
            ),
            if (_message != null) ...<Widget>[
              SizedBox(height: ui.space.s4),
              UiBanner(message: _message!, tone: UiBannerTone.blocked),
            ],
            SizedBox(height: ui.space.s6),
            UiButton(
              label: _busy
                  ? (_resetting ? 'Requesting reset\u2026' : 'Signing in\u2026')
                  : 'Sign in',
              size: UiSize.lg,
              loading: _busy,
              onPressed: _busy ? null : () => unawaited(_submit()),
            ),
            if (!_fixture) ...<Widget>[
              SizedBox(height: ui.space.s4),
              const CaveatText(
                label:
                    'No account or no collection access? Ask your '
                    'collection administrator.',
                why:
                    'This app cannot create accounts or assign roles. '
                    'Both are managed by your collection administrator.',
              ),
              // Sign-in is raised before any collection exists, so the
              // collection document cannot be read here. The build stamp is
              // the only source there is, and this is where it earns its keep
              // (pass criterion 10.3).
              SizedBox(height: ui.space.s2),
              const AdministratorContactLine(),
              SizedBox(height: ui.space.s2),
              Align(
                alignment: AlignmentDirectional.centerStart,
                child: UiButton(
                  label: 'Reset password',
                  variant: UiButtonVariant.ghost,
                  onPressed: _busy
                      ? null
                      : () => unawaited(_submit(reset: true)),
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

/// Explicit local fixture access. Never used as a Firebase failure fallback.
/// The bearer stays in memory and is entered by the developer, not baked into a build.
class LocalFixtureSession implements SessionAccess {
  LocalFixtureSession({required Uri baseUrl, http.Client? client})
    : _baseUrl = baseUrl,
      _client = client ?? http.Client() {
    if (!['localhost', '127.0.0.1', '::1', '10.0.2.2'].contains(baseUrl.host)) {
      throw const ApiFailure(
        'Test access requires a local API.',
        code: 'configuration',
      );
    }
  }
  final Uri _baseUrl;
  final http.Client _client;
  String? _bearer;
  String _userId = '';
  int _generation = 0;
  final _controller = StreamController<bool>.broadcast();
  @override
  Stream<bool> get changes => _controller.stream;
  @override
  bool get signedIn => _bearer != null;
  @override
  String get userId => _userId;
  @override
  String get displayName => 'Test reviewer';
  @override
  Future<String?> token() async => _bearer;
  @override
  Future<void> signIn(String email, String password) async {
    final generation = ++_generation;
    final wasSignedIn = signedIn;
    _bearer = null;
    _userId = '';
    if (wasSignedIn) _controller.add(false);
    if (password.isEmpty) {
      throw const ApiFailure(
        'Enter the local server fixture token.',
        code: 'unauthenticated',
      );
    }
    final probe = ApiSpecimenRepository(
      baseUrl: _baseUrl,
      client: _client,
      token: () async => password,
    );
    try {
      final result = await probe.request('GET', '/v1/session');
      if (generation != _generation) return;
      if (result['mode'] != 'synthetic' ||
          result['user_id'] is! String ||
          (result['user_id'] as String).isEmpty ||
          result['memberships'] is! List ||
          (result['memberships'] as List).any((row) => row is! Map)) {
        throw const ApiFailure(
          'The local server did not return a usable test session. Check the demo configuration.',
          code: 'invalid_session',
        );
      }
      _userId = result['user_id'] as String;
      _bearer = password;
      _controller.add(true);
    } on ApiFailure catch (error) {
      if (generation != _generation) return;
      if (error.status == 401 || error.status == 403) {
        throw const ApiFailure(
          'The local server rejected the fixture token. Check the token and try again.',
          code: 'unauthenticated',
          status: 401,
        );
      }
      if (['network', 'timeout'].contains(error.code) ||
          (error.status ?? 0) >= 500) {
        throw const ApiFailure(
          'The test server is unavailable and you are not signed in. Start or reconnect the demo server, then try again.',
          code: 'server_unavailable',
        );
      }
      if (error.code == 'invalid_session') rethrow;
      throw const ApiFailure(
        'The local server could not check this test session. Check the demo configuration.',
        code: 'invalid_session',
      );
    }
  }

  @override
  Future<void> signOut() async {
    ++_generation;
    _bearer = null;
    _userId = '';
    _controller.add(false);
  }

  void dispose() {
    ++_generation;
    _client.close();
    _controller.close();
  }

  @override
  Future<void> resetPassword(String email) async =>
      throw UnsupportedError('Local fixture access has no password reset.');
}

String authErrorMessage(Object error, {bool reset = false}) {
  final action = reset ? 'Password reset' : 'Sign-in';
  if (error is FirebaseAuthException) {
    return switch (error.code) {
      'network-request-failed' =>
        '$action could not reach the sign-in service. Check your connection and retry.',
      'too-many-requests' =>
        'Too many attempts. Wait a few minutes before trying again.',
      'operation-not-allowed' =>
        '$action is not enabled for this app. Ask your administrator to enable it.',
      'invalid-email' => 'Enter an address like name@fieldmuseum.org.',
      'user-disabled' => 'This account cannot sign in. Ask your administrator.',
      _ =>
        '$action could not be completed. Check your account details or contact your administrator.',
    };
  }
  return '$action could not be completed. Check your connection and retry.';
}
