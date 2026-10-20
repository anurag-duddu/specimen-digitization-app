/// Transport boundary for private drafts and frozen submissions.
library;

import 'dart:typed_data';
import '../../models.dart';

abstract interface class BulkIntakeRepository {
  Future<Json> intakeRequest(
    CollectionScope scope,
    String method,
    String path, {
    Json? body,
    Map<String, String>? query,
    Uint8List? bytes,
    int? offset,
  });

  Future<Uint8List> intakePreview(
    CollectionScope scope,
    String itemId, {
    bool full = false,
  });
}

class IntakeDraft {
  const IntakeDraft(this.data);
  final Json data;
  String get id => data['id'] as String;
  int get revision => (data['revision'] as num).toInt();
  bool get editable => data['state'] == 'draft';
}

class IntakeDraftItem {
  const IntakeDraftItem(this.data);
  final Json data;
  String get id => data['id'] as String;
  String get name => textOf(data['filename'], 'Photo');
  String get state => textOf(data['state'], 'waiting');
  bool get saved => state == 'ready';
  bool get removed => data['removed'] == true;
  bool get included => data['included'] != false;
  bool get sensitive => data['photo_sensitive'] == true;
  bool get canSubmit => included && !removed && state != 'needs_attention';
  String? get error =>
      data['error'] is Map ? textOf((data['error'] as Map)['message']) : null;
}

class IntakeSubmission {
  const IntakeSubmission(this.data);
  final Json data;
  String get id => data['id'] as String;
  int get total => (data['total'] as num).toInt();
  Map<String, dynamic> get counts => data['counts'] is Map
      ? Map<String, dynamic>.from(data['counts'])
      : const {};
  bool get active => [
    'waiting',
    'transferring',
    'checking',
  ].any((key) => ((counts[key] as num?) ?? 0) > 0);
}

class IntakeSubmissionItem {
  const IntakeSubmissionItem(this.data);
  final Json data;
  String get itemId => data['item_id'] as String;
  String get state => textOf(data['state'], 'waiting');
  String get name => textOf(data['filename'], 'Photo');
  double? get progress {
    final size = (data['size_bytes'] as num?)?.toDouble();
    final offset = (data['offset'] as num?)?.toDouble();
    return state == 'transferring' && size != null && size > 0 && offset != null
        ? (offset / size).clamp(0, 1)
        : null;
  }
}

class IntakeProviderConnection {
  const IntakeProviderConnection(this.data);
  final Json data;
  String get id => data['id'] as String;
  String get provider => data['provider'] as String;
  bool get connected => data['state'] == 'connected';
}
