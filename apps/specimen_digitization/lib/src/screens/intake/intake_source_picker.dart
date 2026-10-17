/// Source-specific acquisition ends by adding photos to the shared draft.
library;

import 'dart:async';
import 'dart:convert';
import 'package:flutter/widgets.dart';
import 'package:flutter/services.dart';
import 'package:specimen_ui/specimen_ui.dart';
import '../../models.dart';
import '../../widgets/product_modal.dart';
import 'bulk_intake_controller.dart';
import 'intake_auth_session.dart';

class IntakeSourcePicker extends StatefulWidget {
  const IntakeSourcePicker({
    super.key,
    required this.controller,
    required this.provider,
    this.initialSourceId,
  });
  final BulkIntakeController controller;
  final String provider;
  final String? initialSourceId;
  @override
  State<IntakeSourcePicker> createState() => _IntakeSourcePickerState();
}

class _IntakeSourcePickerState extends State<IntakeSourcePicker> {
  final links = TextEditingController();
  List<Json> connections = [], entries = [], sources = [];
  final Map<String, Json> selected = {};
  final Map<String, String> linkAccounts = {};
  final List<(String, String)> parents = [];
  String? connectionId, sourceId, folder, cursor, pickerId, message;
  bool busy = false, includeSubfolders = false, configured = true;
  Timer? timer;
  IntakeAuthSession? authSession, pickerSession;
  String? recoveryAction;
  BulkIntakeController get c => widget.controller;
  @override
  void initState() {
    super.initState();
    unawaited(load());
    timer = Timer.periodic(const Duration(seconds: 3), (_) => poll());
  }

  @override
  void dispose() {
    timer?.cancel();
    authSession?.close();
    pickerSession?.close();
    links.dispose();
    super.dispose();
  }

  Future<void> run(Future<void> Function() action) async {
    if (busy) return;
    setState(() {
      busy = true;
      message = null;
      recoveryAction = null;
    });
    try {
      await action();
    } catch (e) {
      if (mounted) {
        setState(() {
          message = c.message(e);
          recoveryAction = e is ApiFailure
              ? e.details['action'] as String?
              : 'retry';
        });
      }
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  Future<void> load() => run(() async {
    if (widget.provider == 'url') {
      final rows = <Json>[];
      for (final name in ['google_drive', 'dropbox']) {
        final result = await c.call(
          'GET',
          '/connections',
          query: {'provider': name},
        );
        rows.addAll(objects(result['items']));
      }
      if (mounted) setState(() => connections = rows);
      return;
    }
    if (widget.provider == 'storage') {
      final result = await c.call('GET', '/sources');
      if (mounted) setState(() => sources = objects(result['items']));
      if (widget.initialSourceId != null) {
        sourceId = widget.initialSourceId;
        folder = '';
        await browse();
      }
      return;
    }
    final result = await c.call(
      'GET',
      '/connections',
      query: {'provider': widget.provider},
    );
    if (!mounted) return;
    setState(() {
      connections = objects(result['items']);
      configured = result['configured'] == true;
      connectionId ??=
          connections
                  .where((row) => row['state'] == 'connected')
                  .firstOrNull?['id']
              as String?;
    });
    if (connectionId != null && widget.provider == 'dropbox') await browse();
  });

  Future<void> connect(
    String access, {
    String? provider,
    String? reconnectId,
  }) => run(() async {
    final session = IntakeAuthSession();
    authSession = session;
    final proof = intakeClientId() + intakeClientId();
    try {
      final result = await c.call(
        'POST',
        '/connections',
        body: {
          'provider': provider ?? widget.provider,
          'access': access,
          'session_proof': proof,
          'return_origin': ?session.returnOrigin,
          'reconnect_id': ?reconnectId,
        },
      );
      connectionId = result['id'] as String;
      final response = await session.authenticate(
        result['authorization_url'] as String,
      );
      if (!mounted) return;
      await c.call(
        'POST',
        '/connections/complete',
        body: {...response, 'session_proof': proof},
      );
      await poll();
    } finally {
      session.close();
      authSession = null;
    }
  });

  Future<void> poll() async {
    if (busy || connectionId == null) return;
    try {
      final result = await c.call('GET', '/connections/$connectionId');
      if (!mounted) return;
      final wasConnected = connections.any(
        (row) => row['id'] == connectionId && row['state'] == 'connected',
      );
      setState(() {
        connections.removeWhere((row) => row['id'] == connectionId);
        connections.add(result);
      });
      if (result['state'] == 'connected' && !wasConnected) {
        setState(() => message = 'Connected. Choose photos to review.');
        if (widget.provider == 'url') {
          linkAccounts[result['provider'] as String] = result['id'] as String;
        } else if (result['access'] == 'folders') {
          await run(browse);
        }
      } else if (result['error'] is Map) {
        setState(() {
          message = textOf((result['error'] as Map)['message']);
          recoveryAction = (result['error'] as Map)['action'] as String?;
        });
      }
      if (pickerId != null) {
        final picker = await c.call(
          'GET',
          '/connections/$connectionId/picker/$pickerId',
        );
        if (picker['state'] == 'selected') {
          pickerId = null;
          pickerSession?.close();
          if (mounted) {
            setState(() {
              entries = objects(picker['items']);
              final failures = objects(picker['failures']);
              if (failures.isNotEmpty) {
                message =
                    '${entries.length} available · ${failures.length} need access or another selection. Available photos are retained.';
              }
            });
          }
        }
      }
    } catch (_) {
      /* Keep the confirmed connection state while offline. */
    }
  }

  Future<void> browse({String? after}) async {
    final path = sourceId != null
        ? '/sources/$sourceId/browse'
        : '/connections/$connectionId/browse';
    final result = await c.call(
      'POST',
      path,
      body: {'folder': folder ?? '', 'cursor': ?after},
    );
    if (mounted) {
      setState(() {
        entries = [
          ...(after == null ? <Json>[] : entries),
          ...objects(result['items']),
        ];
        cursor = result['next_cursor'] as String?;
        message = result['message'] as String?;
      });
    }
  }

  Future<void> picker() => run(() async {
    pickerSession?.close();
    pickerSession = IntakeAuthSession();
    final existing = connections
        .where(
          (row) => row['id'] == connectionId && row['state'] == 'connected',
        )
        .firstOrNull;
    if (existing == null) {
      throw const ApiFailure('Connect Google Drive first.', code: 'connect');
    }
    connectionId = existing['id'] as String;
    final result = await c.call('POST', '/connections/$connectionId/picker');
    pickerId = result['id'] as String;
    await pickerSession!.openPicker(result['url'] as String);
  });

  Future<void> folderAccess() async {
    final existing = connections
        .where(
          (row) =>
              row['id'] == connectionId &&
              row['state'] == 'connected' &&
              row['access'] == 'folders',
        )
        .firstOrNull;
    if (existing == null) {
      await connect('folders');
    } else {
      connectionId = existing['id'] as String;
      await run(browse);
    }
  }

  Future<void> selectFolder() => run(() async {
    final path = sourceId != null
        ? '/sources/$sourceId/select-folder'
        : '/connections/$connectionId/select-folder';
    final result = await c.call(
      'POST',
      path,
      body: {
        'folder': folder ?? '',
        'recursive': includeSubfolders,
        'limit': 500 - c.visible.length,
      },
    );
    if (!mounted) return;
    setState(() {
      entries = objects(result['items']);
      selected.clear();
      for (final item in entries.where((row) => row['supported'] == true)) {
        selected[item['id'] as String] = item;
      }
      message =
          '${result['discovered']} found · ${result['unsupported']} unsupported · ${result['inaccessible']} inaccessible';
    });
  });

  Future<void> resolveLinks() => run(() async {
    final values = links.text
        .split(RegExp(r'\s+'))
        .where((value) => value.isNotEmpty)
        .toList();
    if (values.isEmpty || values.length > 500 - c.visible.length) {
      throw const ApiFailure(
        'Enter one supported link per line, within the batch limit.',
        code: 'link_limit',
      );
    }
    final rows = <Json>[];
    for (final value in values) {
      try {
        final host = Uri.tryParse(value)?.host;
        final provider = ['drive.google.com', 'docs.google.com'].contains(host)
            ? 'google_drive'
            : ['dropbox.com', 'www.dropbox.com'].contains(host)
            ? 'dropbox'
            : null;
        final result = await c.call(
          'POST',
          '/resolve',
          body: {'url': value, 'connection_id': ?linkAccounts[provider]},
        );
        rows.addAll(objects(result['items']));
      } catch (e) {
        rows.add({
          'id': value,
          'filename': value,
          'supported': false,
          'error': c.message(e),
        });
      }
    }
    if (mounted) {
      setState(() {
        entries = rows;
        selected.clear();
      });
    }
  });

  Future<void> addSelected() => run(() async {
    final photos = selected.values
        .map(
          (row) => <String, dynamic>{
            'client_id': row['client_id'] ??= intakeClientId(),
            'filename': row['filename'],
            'media_type': row['media_type'] ?? 'application/octet-stream',
            'source': row['source'],
            'photo_sensitive': false,
          },
        )
        .toList();
    await c.addSource(photos);
    if (mounted && c.error == null) {
      Navigator.of(context).pop();
    } else if (mounted) {
      setState(() => message = c.error);
    }
  });

  Future<void> disconnect(String id) => run(() async {
    final result = await c.call('POST', '/connections/$id/disconnect');
    connections.removeWhere((row) => row['id'] == id);
    connections.add(result);
    if (result['error'] is Map) {
      message = textOf((result['error'] as Map)['message']);
    }
    if (connectionId == id) {
      connectionId = null;
      entries = [];
      selected.clear();
    }
  });

  Future<void> preview(Json row) => run(() async {
    final result = await c.call(
      'POST',
      '/source-preview',
      body: Map<String, dynamic>.from(row['source'] as Map),
    );
    if (!mounted) return;
    await showProductModal<void>(
      context: context,
      title: textOf(row['filename'], 'Photo preview'),
      body: (context) => SizedBox(
        height: MediaQuery.sizeOf(context).height * .55,
        child: InteractiveViewer(
          child: Image.memory(
            base64Decode(result['image'] as String),
            fit: BoxFit.contain,
            semanticLabel: textOf(row['filename'], 'Photo preview'),
          ),
        ),
      ),
    );
  });

  @override
  Widget build(BuildContext context) {
    final ui = context.ui;
    final connected = connections.any(
      (row) => row['id'] == connectionId && row['state'] == 'connected',
    );
    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (widget.provider == 'url') ...[
          for (final provider in ['google_drive', 'dropbox']) ...[
            for (final account in connections.where(
              (row) =>
                  row['provider'] == provider && row['state'] == 'connected',
            ))
              UiCheckbox(
                label:
                    '${provider == 'google_drive' ? 'Google Drive' : 'Dropbox'} · ${textOf(account['account_label'], 'Account')} · ${account['access'] == 'folders' ? 'Folders' : 'Selected files'}',
                value: linkAccounts[provider] == account['id'],
                onChanged: busy
                    ? null
                    : (_) => setState(
                        () => linkAccounts[provider] = account['id'] as String,
                      ),
              ),
            UiButton(
              label:
                  'Connect ${provider == 'google_drive' ? 'Google Drive' : 'Dropbox'} for links and folders',
              variant: UiButtonVariant.ghost,
              onPressed: busy
                  ? null
                  : () => connect('folders', provider: provider),
            ),
          ],
          UiField(
            label: 'Photo or folder links',
            controller: links,
            minLines: 2,
            maxLines: 5,
            helpText:
                'One direct image, Drive, Dropbox, or registered storage link per line.',
          ),
          UiButton(
            label: 'Review links',
            onPressed: busy ? null : resolveLinks,
            variant: UiButtonVariant.secondary,
          ),
        ] else if (widget.provider == 'storage') ...[
          if (sources.isEmpty && !busy)
            const Text(
              'No storage locations are registered for this collection. Ask your administrator or choose another source.',
            ),
          for (final source in sources)
            UiButton(
              label: textOf(source['label'], 'Storage'),
              variant: UiButtonVariant.secondary,
              onPressed: busy
                  ? null
                  : () => run(() async {
                      sourceId = source['id'] as String;
                      folder = '';
                      await browse();
                    }),
            ),
        ] else ...[
          if (!configured)
            const Text(
              'This provider needs administrator setup. File upload and camera capture remain available.',
            ),
          if (configured && !connected)
            UiButton(
              label: 'Connect account',
              onPressed: busy
                  ? null
                  : () => connect(
                      widget.provider == 'google_drive' ? 'files' : 'folders',
                    ),
            ),
          for (final connection in connections.where(
            (row) => row['state'] == 'disconnected' && row['error'] is Map,
          ))
            UiButton(
              label:
                  'Retry disconnecting ${textOf(connection['account_label'], 'account')}',
              variant: UiButtonVariant.secondary,
              onPressed: busy
                  ? null
                  : () => disconnect(connection['id'] as String),
            ),
          for (final connection in connections.where(
            (row) => row['state'] == 'connected',
          ))
            UiCheckbox(
              label: textOf(connection['account_label'], widget.provider),
              value: connectionId == connection['id'],
              onChanged: busy
                  ? null
                  : (_) => run(() async {
                      connectionId = connection['id'] as String;
                      folder = '';
                      parents.clear();
                      entries = [];
                      if (connection['access'] == 'folders') await browse();
                    }),
            ),
          if (connected)
            Wrap(
              spacing: ui.space.s2,
              children: [
                if (widget.provider == 'google_drive')
                  UiButton(
                    label: 'Choose Drive files',
                    variant: UiButtonVariant.secondary,
                    onPressed: busy ? null : picker,
                  ),
                UiButton(
                  label: 'Browse folders',
                  variant: UiButtonVariant.secondary,
                  onPressed: busy ? null : folderAccess,
                ),
                UiButton(
                  label: 'Change account',
                  variant: UiButtonVariant.ghost,
                  onPressed: busy
                      ? null
                      : () => connect(
                          widget.provider == 'google_drive'
                              ? 'files'
                              : 'folders',
                        ),
                ),
                UiButton(
                  label: 'Disconnect',
                  variant: UiButtonVariant.ghost,
                  onPressed: busy ? null : () => disconnect(connectionId!),
                ),
              ],
            ),
        ],
        if (message != null)
          Padding(
            padding: EdgeInsets.symmetric(vertical: ui.space.s3),
            child: Text(message!, style: ui.type.bodySmall),
          ),
        for (final account in connections.where(
          (row) => row['state'] != 'connected' && row['account_id'] != null,
        ))
          UiButton(
            label:
                'Reconnect ${textOf(account['account_label'], 'account')} to resume imports',
            variant: UiButtonVariant.secondary,
            onPressed: busy
                ? null
                : () => connect(
                    account['access'] as String,
                    provider: account['provider'] as String,
                    reconnectId: account['id'] as String,
                  ),
          ),
        if (recoveryAction == 'administrator' || !configured)
          UiButton(
            label: 'Copy administrator instructions',
            leading: UiIcons.copy,
            variant: UiButtonVariant.secondary,
            onPressed: () async {
              await Clipboard.setData(
                ClipboardData(
                  text:
                      'Photo intake connection: ${widget.provider}. Collection: ${c.scope.name}. '
                      'Please review the application OAuth client and organization app-access policy. '
                      'Google selected files use drive.file; folder browsing requests drive.readonly. '
                      'Google verification and institutional approval are separate. '
                      'The app imports copies only and does not modify provider originals. '
                      'Reported issue: ${message ?? 'Provider setup is unavailable.'}',
                ),
              );
              if (mounted) {
                setState(() => message = 'Administrator instructions copied.');
              }
            },
          ),
        if (recoveryAction == 'file_access')
          const Text(
            'Ask the file owner for download access, reconnect the account with access, or choose another source. Your other selections are retained.',
          ),
        if (recoveryAction == 'connect' && widget.provider != 'url')
          UiButton(
            label: 'Sign in again',
            variant: UiButtonVariant.secondary,
            onPressed: busy
                ? null
                : () => connect(
                    widget.provider == 'google_drive' ? 'files' : 'folders',
                  ),
          ),
        if (recoveryAction == 'retry')
          UiButton(
            label: 'Retry',
            variant: UiButtonVariant.secondary,
            onPressed: busy
                ? null
                : widget.provider == 'url'
                ? resolveLinks
                : connectionId != null || sourceId != null
                ? () => run(() => browse())
                : load,
          ),
        if (parents.isNotEmpty)
          UiButton(
            label: 'Back to ${parents.last.$2}',
            leading: UiIcons.back,
            variant: UiButtonVariant.ghost,
            onPressed: busy
                ? null
                : () => run(() async {
                    folder = parents.removeLast().$1;
                    await browse();
                  }),
          ),
        if (sourceId != null || folder != null) ...[
          UiCheckbox(
            label: 'Include subfolders',
            value: includeSubfolders,
            onChanged: (value) => setState(() => includeSubfolders = value),
          ),
          UiButton(
            label: 'Select folder photos',
            variant: UiButtonVariant.secondary,
            onPressed: busy ? null : selectFolder,
          ),
        ],
        if (entries.isNotEmpty)
          SizedBox(
            height: mathHeight(context),
            child: ListView.builder(
              itemCount: entries.length,
              itemBuilder: (context, index) {
                final row = entries[index];
                final id = row['id'] as String;
                if (row['kind'] == 'folder') {
                  return UiButton(
                    label: textOf(row['filename'], 'Folder'),
                    leading: UiIcons.source,
                    variant: UiButtonVariant.ghost,
                    onPressed: busy
                        ? null
                        : () => run(() async {
                            if (row['connection_id'] != null) {
                              connectionId = row['connection_id'] as String;
                            }
                            if (row['source_id'] != null) {
                              sourceId = row['source_id'] as String;
                            }
                            parents.add((folder ?? '', 'folder'));
                            folder = id;
                            await browse();
                          }),
                  );
                }
                return Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    UiCheckbox(
                      label: textOf(row['filename'], 'Photo'),
                      value: selected.containsKey(id),
                      onChanged: row['supported'] != true
                          ? null
                          : (value) => setState(() {
                              if (value &&
                                  selected.length + c.visible.length >= 500) {
                                message =
                                    'This batch is full. Choose fewer photos.';
                                return;
                              }
                              value ? selected[id] = row : selected.remove(id);
                            }),
                      disabledReason: row['supported'] == true
                          ? null
                          : textOf(row['error'], 'Unsupported file'),
                    ),
                    if (row['error'] != null)
                      Text(textOf(row['error']), style: ui.type.bodySmall),
                    if (row['supported'] == true && row['source'] is Map)
                      UiButton(
                        label: 'Preview',
                        variant: UiButtonVariant.ghost,
                        onPressed: busy ? null : () => preview(row),
                      ),
                  ],
                );
              },
            ),
          ),
        if (cursor != null)
          UiButton(
            label: 'Load more files',
            variant: UiButtonVariant.ghost,
            onPressed: busy ? null : () => run(() => browse(after: cursor)),
          ),
        if (busy) const UiProgress.bar(semanticsLabel: 'Loading source'),
        if (entries.isNotEmpty)
          UiButton(
            label: 'Add ${selected.length} photos',
            onPressed: busy || selected.isEmpty ? null : addSelected,
          ),
        SizedBox(height: ui.space.s2),
        Text(
          'Selected photos are copied into your private draft. Originals stay in their source.',
          style: ui.type.bodySmall,
        ),
      ],
    );
  }

  double mathHeight(BuildContext context) =>
      (MediaQuery.sizeOf(context).height * .32).clamp(160, 360);
}
