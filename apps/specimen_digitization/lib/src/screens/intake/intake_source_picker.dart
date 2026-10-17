/// Source-specific acquisition ends by adding photos to the shared draft.
library;

import 'intake_timing.dart';
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
    this.authSessionFactory,
  });
  final BulkIntakeController controller;
  final String provider;
  final String? initialSourceId;
  final IntakeAuthSession Function()? authSessionFactory;
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
  bool busy = false, includeSubfolders = false, polling = false;
  bool administratorDetailsCopied = false;
  Timer? timer;
  IntakeAuthSession? authSession, pickerSession;
  String? recoveryAction;
  Future<void> Function()? retryAction, reconnectAction;
  String? connectingProvider, failedProvider;
  BulkIntakeController get c => widget.controller;
  String providerName(String provider) =>
      provider == 'google_drive' ? 'Google Drive' : 'Dropbox';
  Json? get activeConnection =>
      connections.where((row) => row['id'] == connectionId).firstOrNull;
  String get defaultAccess =>
      widget.provider == 'google_drive' ? 'files' : 'folders';
  IntakeAuthSession newAuthSession() =>
      widget.authSessionFactory?.call() ?? IntakeAuthSession();
  @override
  void initState() {
    super.initState();
    unawaited(load());
    timer = Timer.periodic(intakePollInterval, (_) => poll());
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
      administratorDetailsCopied = false;
    });
    retryAction = action;
    try {
      await action();
    } catch (e) {
      if (mounted) {
        setState(() {
          message = c.message(e);
          recoveryAction = e is ApiFailure
              ? (e.details['action'] as String? ?? 'retry')
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
      if (mounted) {
        setState(() {
          connections = rows;
          for (final name in ['google_drive', 'dropbox']) {
            final available = connectedAccounts(name);
            if (available.length == 1) {
              linkAccounts[name] = available.single['id'] as String;
            }
          }
        });
      }
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
      final available = connections
          .where((row) => row['state'] == 'connected')
          .toList();
      // Never choose between multiple provider accounts on the user's behalf.
      connectionId ??= available.length == 1
          ? available.single['id'] as String
          : available.isEmpty
          ? (connections
                    .where((row) => row['state'] != 'disconnected')
                    .lastOrNull?['id']
                as String?)
          : null;
      final active = activeConnection;
      if (active != null) connectionError(active);
    });
    if (activeConnection?['state'] == 'connected' &&
        activeConnection?['access'] == 'folders') {
      folder = '';
      await browse();
    }
  });

  void connectionError(Json row) {
    if (row['state'] != 'connected' && row['error'] is Map) {
      message = textOf((row['error'] as Map)['message']);
      recoveryAction = (row['error'] as Map)['action'] as String?;
      failedProvider = row['provider'] as String;
    }
  }

  void rememberConnection(Json row, {bool showError = true}) {
    connections.removeWhere((existing) => existing['id'] == row['id']);
    connections.add(row);
    connectionId = row['id'] as String;
    if (showError) connectionError(row);
  }

  Future<void> retryConnection() async {
    if (reconnectAction != null) return reconnectAction!();
    final row = activeConnection;
    return connect(
      row?['access'] as String? ?? defaultAccess,
      provider: row?['provider'] as String? ?? failedProvider,
      reconnectId: row?['account_id'] != null ? row!['id'] as String : null,
    );
  }

  Future<void> chooseAccount(String id) => run(() async {
    closePicker();
    connectionId = id;
    reconnectAction = null;
    folder = null;
    cursor = null;
    parents.clear();
    entries = [];
    if (activeConnection?['access'] == 'folders') {
      folder = '';
      await browse();
    }
  });

  Future<void> connect(
    String access, {
    String? provider,
    String? reconnectId,
  }) => run(() async {
    closePicker();
    final name = provider ?? widget.provider;
    failedProvider = name;
    connectingProvider = name;
    reconnectAction = () =>
        connect(access, provider: name, reconnectId: reconnectId);
    final session = newAuthSession();
    authSession = session;
    final proof = intakeClientId() + intakeClientId();
    try {
      final result = await c.call(
        'POST',
        '/connections',
        body: {
          'provider': name,
          'access': access,
          'session_proof': proof,
          'return_origin': ?session.returnOrigin,
          'reconnect_id': ?reconnectId,
        },
      );
      if (!mounted) return;
      setState(() => rememberConnection(result, showError: false));
      final continueToPicker =
          name == 'google_drive' &&
          access == 'files' &&
          widget.provider != 'url';
      final response = await session.authenticate(
        result['authorization_url'] as String,
        keepOpen: continueToPicker,
      );
      if (!mounted) return;
      final completed = await c.call(
        'POST',
        '/connections/complete',
        body: {...response, 'session_proof': proof},
      );
      if (!mounted) return;
      setState(() => rememberConnection(completed));
      if (completed['state'] == 'connected') {
        reconnectAction = null;
        folder = null;
        cursor = null;
        parents.clear();
        entries = [];
        if (widget.provider == 'url') {
          linkAccounts[name] = completed['id'] as String;
        } else if (continueToPicker) {
          pickerSession?.close();
          pickerSession = session;
          // If Picker setup fails, retry selection using the connected account.
          retryAction = pick;
          try {
            await openPicker(session);
          } catch (_) {
            pickerSession = null;
            rethrow;
          }
        } else {
          folder = '';
          retryAction = browse;
          await browse();
        }
      }
    } finally {
      if (!identical(pickerSession, session)) session.close();
      authSession = null;
      connectingProvider = null;
    }
  });

  Future<void> poll() async {
    if (busy || polling || connectionId == null) return;
    polling = true;
    final requestedConnection = connectionId;
    try {
      final result = await c.call('GET', '/connections/$requestedConnection');
      if (!mounted || busy || connectionId != requestedConnection) return;
      final wasConnected = connections.any(
        (row) => row['id'] == connectionId && row['state'] == 'connected',
      );
      setState(() {
        final changed = activeConnection?['state'] != result['state'];
        connections.removeWhere((row) => row['id'] == connectionId);
        connections.add(result);
        if (changed) connectionError(result);
      });
      if (result['state'] == 'connected' && !wasConnected) {
        setState(() {
          message = null;
          recoveryAction = null;
          reconnectAction = null;
        });
        if (widget.provider == 'url') {
          linkAccounts[result['provider'] as String] = result['id'] as String;
        } else if (result['access'] == 'folders') {
          folder = '';
          await run(browse);
        }
      }
      if (pickerId != null) {
        final requestedPicker = pickerId;
        final picker = await c.call(
          'GET',
          '/connections/$requestedConnection/picker/$requestedPicker',
        );
        if (!mounted ||
            busy ||
            connectionId != requestedConnection ||
            pickerId != requestedPicker) {
          return;
        }
        if (picker['state'] == 'selected') {
          closePicker();
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
    } finally {
      polling = false;
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

  void closePicker() {
    pickerId = null;
    pickerSession?.close();
    pickerSession = null;
  }

  Future<void> picker() => run(pick);

  Future<void> pick() async {
    closePicker();
    pickerSession = newAuthSession();
    try {
      await openPicker(pickerSession!);
    } catch (_) {
      pickerSession?.close();
      pickerSession = null;
      rethrow;
    }
  }

  Future<void> openPicker(IntakeAuthSession session) async {
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
    if (!mounted || !identical(pickerSession, session)) return;
    pickerId = result['id'] as String;
    await session.openPicker(result['url'] as String);
  }

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
      folder ??= '';
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
        selected[selectionKey(item)] = item;
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
    if (id == connectionId) closePicker();
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

  // Provider-local IDs (for example Dropbox paths) can repeat across accounts.
  String selectionKey(Json row) {
    final source = row['source'] is Map ? row['source'] as Map : const {};
    return jsonEncode([
      source['provider'],
      source['connection_id'],
      source['source_id'],
      row['id'],
    ]);
  }

  List<Json> connectedAccounts(String provider) => connections
      .where(
        (row) => row['provider'] == provider && row['state'] == 'connected',
      )
      .toList();

  String accountLabel(Json row) {
    final label = textOf(
      row['account_label'],
      providerName(row['provider'] as String),
    );
    final repeated =
        connectedAccounts(row['provider'] as String)
            .where((other) => other['account_label'] == row['account_label'])
            .length >
        1;
    return repeated
        ? '$label · ${row['access'] == 'folders' ? 'Folders' : 'Selected photos'}'
        : label;
  }

  Widget accountChoice(
    String provider,
    String? value,
    ValueChanged<String> onChanged,
  ) {
    final available = connectedAccounts(provider);
    return UiSelect<String>(
      label: '${providerName(provider)} account',
      options: [
        for (final row in available)
          UiSelectOption(value: row['id'] as String, label: accountLabel(row)),
      ],
      value: available.any((row) => row['id'] == value) ? value : null,
      placeholder: 'Choose an account',
      onChanged: busy ? null : onChanged,
    );
  }

  Future<void> copyAdministratorDetails() async {
    final name = failedProvider ?? widget.provider;
    await Clipboard.setData(
      ClipboardData(
        text:
            'Photo intake connection: ${providerName(name)}. Collection: ${c.scope.name}. '
            'Reported issue: $message '
            'Please review the application configuration and organization app-access policy. '
            '${name == 'google_drive' ? 'Google selected photos use drive.file; folder browsing uses drive.readonly. Google verification and institutional approval are separate. ' : ''}'
            'The app imports copies and does not modify provider originals.',
      ),
    );
    if (mounted) setState(() => administratorDetailsCopied = true);
  }

  @override
  Widget build(BuildContext context) {
    final ui = context.ui;
    final cloud =
        widget.provider == 'google_drive' || widget.provider == 'dropbox';
    final connected =
        activeConnection?['state'] == 'connected' &&
        recoveryAction != 'connect';
    final available = cloud ? connectedAccounts(widget.provider) : <Json>[];
    final connectionFailed =
        reconnectAction != null ||
        (activeConnection != null && !connected) ||
        recoveryAction == 'connect';
    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (widget.provider == 'url') ...[
          for (final provider in ['google_drive', 'dropbox']) ...[
            if (connectedAccounts(provider).isNotEmpty)
              accountChoice(
                provider,
                linkAccounts[provider],
                (id) => setState(() => linkAccounts[provider] = id),
              ),
            UiButton(
              label: connectedAccounts(provider).isEmpty
                  ? 'Connect ${providerName(provider)}'
                  : 'Use another ${providerName(provider)} account',
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
          if (!connected && available.isEmpty) ...[
            Text(
              'Connect ${providerName(widget.provider)} to choose photos for this batch.',
              style: ui.type.body,
            ),
            SizedBox(height: ui.space.s2),
            Text(
              'Your account stays connected for next time. Only photos you choose are imported; originals stay in place.',
              style: ui.type.bodySmall,
            ),
            SizedBox(height: ui.space.s4),
          ],
          if (available.length > 1 || (available.isNotEmpty && !connected))
            accountChoice(widget.provider, connectionId, chooseAccount),
          if (connected) ...[
            const Align(
              alignment: AlignmentDirectional.centerStart,
              child: UiChip(label: 'Connected'),
            ),
            SizedBox(height: ui.space.s2),
            if (available.length == 1)
              Text(accountLabel(activeConnection!), style: ui.type.body),
            SizedBox(height: ui.space.s3),
            Wrap(
              spacing: ui.space.s2,
              runSpacing: ui.space.s2,
              children: [
                if (widget.provider == 'google_drive')
                  UiButton(
                    label: 'Choose photos',
                    onPressed: busy ? null : picker,
                  ),
                if (activeConnection?['access'] != 'folders')
                  UiButton(
                    label: 'Browse folders',
                    variant: UiButtonVariant.secondary,
                    onPressed: busy ? null : folderAccess,
                  ),
                UiButton(
                  label: 'Use another account',
                  variant: UiButtonVariant.ghost,
                  onPressed: busy ? null : () => connect(defaultAccess),
                ),
                UiButton(
                  label: 'Disconnect',
                  variant: UiButtonVariant.ghost,
                  onPressed: busy ? null : () => disconnect(connectionId!),
                ),
              ],
            ),
          ] else if (!connectionFailed)
            UiButton(
              label: available.isEmpty
                  ? 'Connect ${providerName(widget.provider)}'
                  : 'Use another account',
              onPressed: busy ? null : () => connect(defaultAccess),
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
        ],
        for (final account in connections.where(
          (row) =>
              row['state'] != 'connected' &&
              row['state'] != 'disconnected' &&
              row['account_id'] != null &&
              row['id'] != connectionId,
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
        if (connectingProvider != null)
          Padding(
            padding: EdgeInsets.symmetric(vertical: ui.space.s3),
            child: Text(
              'Connecting to ${providerName(connectingProvider!)}…',
              style: ui.type.bodySmall,
            ),
          ),
        if (message != null)
          Padding(
            padding: EdgeInsets.symmetric(vertical: ui.space.s3),
            child: Semantics(
              liveRegion: true,
              child: Text(message!, style: ui.type.bodySmall),
            ),
          ),
        if (recoveryAction == 'administrator') ...[
          Text(
            'Share these details with your administrator, then retry when access is available.',
            style: ui.type.bodySmall,
          ),
          UiButton(
            label: administratorDetailsCopied
                ? 'Administrator details copied'
                : 'Copy administrator details',
            leading: UiIcons.copy,
            variant: UiButtonVariant.secondary,
            onPressed: busy ? null : copyAdministratorDetails,
          ),
        ],
        if (recoveryAction == 'file_access')
          Text(
            'Ask the file owner for download access, use an account with access, or choose another source. Your other selections are retained.',
            style: ui.type.bodySmall,
          ),
        if (connectionFailed && !busy) ...[
          UiButton(label: 'Retry connection', onPressed: retryConnection),
          if (activeConnection?['account_id'] != null)
            UiButton(
              label: 'Use another account',
              variant: UiButtonVariant.ghost,
              onPressed: () => connect(
                activeConnection!['access'] as String,
                provider: activeConnection!['provider'] as String,
              ),
            ),
        ] else if (message != null &&
            retryAction != null &&
            (recoveryAction == 'retry' || recoveryAction == 'administrator'))
          UiButton(
            label: 'Retry',
            variant: UiButtonVariant.secondary,
            onPressed: busy ? null : () => run(retryAction!),
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
        if (!busy && folder != null && entries.isEmpty)
          Text('No photos in this folder.', style: ui.type.bodySmall),
        if (entries.isNotEmpty)
          SizedBox(
            height: mathHeight(context),
            child: ListView.builder(
              itemCount: entries.length,
              itemBuilder: (context, index) {
                final row = entries[index];
                final id = row['id'] as String;
                final key = selectionKey(row);
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
                      value: selected.containsKey(key),
                      onChanged: row['supported'] != true
                          ? null
                          : (value) => setState(() {
                              if (value &&
                                  selected.length + c.visible.length >= 500) {
                                message =
                                    'This batch is full. Choose fewer photos.';
                                return;
                              }
                              value
                                  ? selected[key] = row
                                  : selected.remove(key);
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
        if (entries.isNotEmpty || selected.isNotEmpty)
          UiButton(
            label:
                'Add ${selected.length} ${selected.length == 1 ? 'photo' : 'photos'}',
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
