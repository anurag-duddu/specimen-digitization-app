import Flutter
import UIKit
import AuthenticationServices

@main
@objc class AppDelegate: FlutterAppDelegate, FlutterImplicitEngineDelegate {
  private var intakeAuth: IntakeAuthChannel?
  override func application(
    _ application: UIApplication,
    didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?
  ) -> Bool {
    return super.application(application, didFinishLaunchingWithOptions: launchOptions)
  }

  // With the UIScene lifecycle the Flutter engine exists only after UIKit has created
  // the scene, so plugins register here instead of in didFinishLaunchingWithOptions.
  func didInitializeImplicitFlutterEngine(_ engineBridge: FlutterImplicitEngineBridge) {
    GeneratedPluginRegistrant.register(with: engineBridge.pluginRegistry)
    if let registrar = engineBridge.pluginRegistry.registrar(forPlugin: "IntakeAuth") {
      intakeAuth = IntakeAuthChannel(messenger: registrar.messenger())
    }
  }
}

// Custom-scheme authentication is available before iOS 15. The newer HTTPS
// callback initializer requires iOS 17.4 and is unnecessary for our API bridge.
final class IntakeAuthChannel: NSObject, ASWebAuthenticationPresentationContextProviding {
  private let channel: FlutterMethodChannel
  private var session: ASWebAuthenticationSession?
  private var pendingID: String?
  private var pendingResult: FlutterResult?
  private var anchor: UIWindow?

  init(messenger: FlutterBinaryMessenger) {
    channel = FlutterMethodChannel(name: "specimen/intake_auth", binaryMessenger: messenger)
    super.init()
    channel.setMethodCallHandler { [weak self] call, result in
      self?.handle(call, result: result)
    }
  }

  private func handle(_ call: FlutterMethodCall, result: @escaping FlutterResult) {
    guard let args = call.arguments as? [String: String], let id = args["id"] else {
      result(FlutterError(code: "invalid_request", message: "Invalid connection request.", details: nil))
      return
    }
    if call.method == "cancel" {
      if pendingID == id {
        let current = session
        finish(id: id, error: "cancelled")
        current?.cancel()
      }
      result(nil)
      return
    }
    guard call.method == "authenticate" else { result(FlutterMethodNotImplemented); return }
    guard pendingID == nil else {
      result(FlutterError(code: "busy", message: "A connection is already open.", details: nil))
      return
    }
    guard let raw = args["url"], let url = URL(string: raw),
          url.scheme == "https", url.host != nil, url.user == nil, url.password == nil,
          let expected = args["state"], !expected.isEmpty,
          let parts = URLComponents(url: url, resolvingAgainstBaseURL: false),
          parts.queryItems?.filter({ $0.name == "state" }).map({ $0.value }) == [expected] else {
      result(FlutterError(code: "invalid_request", message: "Invalid connection request.", details: nil))
      return
    }
    anchor = UIApplication.shared.connectedScenes
      .compactMap { $0 as? UIWindowScene }
      .filter { $0.activationState == .foregroundActive }
      .flatMap { $0.windows }
      .first { $0.isKeyWindow }
    guard anchor != nil else {
      result(FlutterError(code: "unavailable", message: "No active application window.", details: nil))
      return
    }
    pendingID = id
    pendingResult = result
    let current = ASWebAuthenticationSession(url: url, callbackURLScheme: "specimenintake") {
      [weak self] callback, error in
      DispatchQueue.main.async {
        guard let self = self, self.pendingID == id else { return }
        let authError = error as NSError?
        if authError?.domain == ASWebAuthenticationSessionErrorDomain &&
           authError?.code == ASWebAuthenticationSessionError.Code.canceledLogin.rawValue {
          self.finish(id: id, error: "cancelled")
        } else if error != nil {
          self.finish(id: id, error: "unavailable")
        } else if let callback = callback,
                  IntakeAuthCallback.matches(callback, expected: expected) {
          self.finish(id: id, value: callback.absoluteString)
        } else {
          self.finish(id: id, error: "invalid_callback")
        }
      }
    }
    current.presentationContextProvider = self
    current.prefersEphemeralWebBrowserSession = false
    session = current
    if !current.start() { finish(id: id, error: "unavailable") }
  }

  private func finish(id: String, value: String? = nil, error: String? = nil) {
    guard pendingID == id else { return }
    let result = pendingResult
    pendingID = nil
    pendingResult = nil
    session = nil
    anchor = nil
    if let error = error {
      result?(FlutterError(code: error, message: "Account connection ended.", details: nil))
    } else {
      result?(value)
    }
  }

  func presentationAnchor(for session: ASWebAuthenticationSession) -> ASPresentationAnchor {
    // The anchor is retained until completion; start() is gated on its presence.
    return anchor ?? ASPresentationAnchor()
  }
}

enum IntakeAuthCallback {
  static func matches(_ url: URL, expected: String) -> Bool {
    guard !expected.isEmpty, url.scheme == "specimenintake", url.host == "oauth",
          url.path == "/callback", url.port == nil, url.user == nil, url.password == nil,
          url.query == nil, let fragment = URLComponents(url: url, resolvingAgainstBaseURL: false)?.fragment,
          let fields = URLComponents(string: "https://callback.invalid/?" + fragment)?.queryItems else {
      return false
    }
    return fields.filter { $0.name == "state" }.map { $0.value } == [expected]
  }
}
