import 'dart:io';
import 'package:crypto/crypto.dart';
import 'dart:convert';
import 'package:file_selector/file_selector.dart';
import 'package:path_provider/path_provider.dart';

Future<XFile> retainDraftFile(XFile file, String owner, String id) async {
  final root = await getApplicationSupportDirectory();
  final namespace = sha256.convert(utf8.encode(owner)).toString();
  final directory = Directory('${root.path}/intake/$namespace');
  await directory.create(recursive: true);
  final path = '${directory.path}/$id';
  await file.saveTo('$path.part');
  await File('$path.part').rename(path);
  return XFile(path, name: file.name, mimeType: file.mimeType);
}

Future<XFile?> restoreDraftFile(String path) async {
  final root = await getApplicationSupportDirectory();
  if (!path.startsWith('${root.path}/intake/')) return null;
  return await File(path).exists() ? XFile(path) : null;
}

Future<void> releaseDraftFile(String path) async {
  final file = await restoreDraftFile(path);
  if (file != null) await File(path).delete();
}

bool get hasDurableLocalFiles => true;

void setDraftLeaveWarning(bool enabled) {}
