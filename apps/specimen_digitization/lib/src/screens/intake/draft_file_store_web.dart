import 'dart:js_interop';
import 'package:web/web.dart' as web;
import 'package:file_selector/file_selector.dart';

/// A browser File handle lasts only for this page. A server ACK is the durable
/// save; restored metadata explicitly asks for reselection until that ACK.
Future<XFile> retainDraftFile(XFile file, String owner, String id) async =>
    file;
Future<XFile?> restoreDraftFile(String path) async => null;
Future<void> releaseDraftFile(String path) async {}
bool get hasDurableLocalFiles => false;

JSFunction? _leaveListener;
void setDraftLeaveWarning(bool enabled) {
  if (!enabled) {
    if (_leaveListener != null) {
      web.window.removeEventListener('beforeunload', _leaveListener!);
    }
    _leaveListener = null;
    return;
  }
  if (_leaveListener != null) return;
  _leaveListener = ((web.BeforeUnloadEvent event) {
    event.preventDefault();
    event.returnValue = '';
  }).toJS;
  web.window.addEventListener('beforeunload', _leaveListener!);
}
