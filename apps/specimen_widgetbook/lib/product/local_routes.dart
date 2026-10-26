import 'package:flutter/widgets.dart';
import 'package:go_router/go_router.dart';

/// Keeps a production router's navigation inside a catalog preview.
///
/// GoRouter's `routerNeglect` still reports a replacement URL to the platform.
/// This provider forwards its navigation and refresh notifications, retains the
/// parsed route locally, and deliberately never reports to SystemNavigator.
class PreviewRouteInformationProvider extends RouteInformationProvider
    with ChangeNotifier {
  PreviewRouteInformationProvider(this.source)
    : _sourceValue = source.value,
      _value = source.value {
    source.addListener(_forward);
    // GoRouteInformationProvider registers for browser route events when its
    // first listener attaches. The outer Widgetbook router owns those events.
    WidgetsBinding.instance.removeObserver(source);
  }

  final GoRouteInformationProvider source;
  RouteInformation _sourceValue;
  RouteInformation _value;

  @override
  RouteInformation get value => _value;

  void _forward() {
    final next = source.value;
    if (!identical(next, _sourceValue)) {
      _sourceValue = next;
      _value = next;
    }
    // A refresh can retain source.value. Keep the latest parsed route after a
    // redirect or pop rather than restoring the old navigation request.
    notifyListeners();
  }

  @override
  void routerReportsNewRouteInformation(
    RouteInformation routeInformation, {
    RouteInformationReportingType type = RouteInformationReportingType.none,
  }) {
    _value = routeInformation;
  }

  @override
  void dispose() {
    source.removeListener(_forward);
    super.dispose();
  }
}
