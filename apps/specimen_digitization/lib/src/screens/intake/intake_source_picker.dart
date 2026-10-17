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
      if (mounted) {
        setState(() {
          folder = null;
          cursor = null;
          parents.clear();
          entries = [];
        });
      }
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
    closePicker();
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
    linkAccounts.removeWhere((_, value) => value == id);
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

  List<Json> recoverableAccounts(String provider) => connections
      .where(
        (row) =>
            row['provider'] == provider &&
            row['state'] != 'connected' &&
            row['state'] != 'disconnected' &&
            row['account_id'] != null,
      )
      .toList();

  Future<void> connectLinkProvider(String provider) {
    final known = recoverableAccounts(provider);
    return known.length == 1
        ? connect(
            known.single['access'] as String,
            provider: provider,
            reconnectId: known.single['id'] as String,
          )
        : connect('folders', provider: provider);
  }

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

  Set<String> get linkedProviders => {
    for (final value in links.text.split(RegExp(r'\s+')))
      if ([
        'drive.google.com',
        'docs.google.com',
      ].contains(Uri.tryParse(value)?.host))
        'google_drive'
      else if ([
        'dropbox.com',
        'www.dropbox.com',
      ].contains(Uri.tryParse(value)?.host))
        'dropbox',
  };

  Widget connectionOptions(
    String provider, {
    String? selectedId,
  }) => UiMenuTrigger(
    semanticsLabel: '${providerName(provider)} options',
    items: [
      if (widget.provider != 'url' &&
          provider == 'google_drive' &&
          activeConnection?['state'] == 'connected')
        UiMenuItem(
          label: folder == null ? 'Browse folders' : 'Choose photos',
          onSelected: busy
              ? null
              : () => unawaited(folder == null ? folderAccess() : picker()),
        ),
      UiMenuItem(
        label: 'Use another account',
        onSelected: busy
            ? null
            : () => unawaited(
                connect(
                  widget.provider == 'url' ? 'folders' : defaultAccess,
                  provider: provider,
                ),
              ),
      ),
      for (final account in connections.where(
        (row) =>
            row['provider'] == provider &&
            row['state'] != 'connected' &&
            row['state'] != 'disconnected' &&
            row['account_id'] != null &&
            row['id'] != selectedId,
      ))
        UiMenuItem(
          label: 'Reconnect ${textOf(account['account_label'], 'account')}',
          onSelected: busy
              ? null
              : () => unawaited(
                  connect(
                    account['access'] as String,
                    provider: provider,
                    reconnectId: account['id'] as String,
                  ),
                ),
        ),
      if (selectedId != null)
        UiMenuItem(
          label: 'Disconnect',
          onSelected: busy ? null : () => unawaited(disconnect(selectedId)),
        ),
      for (final account in connections.where(
        (row) =>
            row['provider'] == provider &&
            row['state'] == 'disconnected' &&
            row['error'] is Map,
      ))
        UiMenuItem(
          label:
              'Retry disconnecting ${textOf(account['account_label'], 'account')}',
          onSelected: busy
              ? null
              : () => unawaited(disconnect(account['id'] as String)),
        ),
    ],
  );

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
          UiField(
            label: 'Photo or folder links',
            controller: links,
            onChanged: (_) => setState(() {}),
            minLines: 2,
            maxLines: 5,
            helpText:
                'One direct image, Drive, Dropbox, or registered storage link per line.',
          ),
          for (final provider in linkedProviders) ...[
            SizedBox(height: ui.space.s3),
            if (connectedAccounts(provider).isEmpty &&
                recoverableAccounts(provider).length == 1)
              Text(
                accountLabel(recoverableAccounts(provider).single),
                style: ui.type.bodySmall,
              ),
            if (connectedAccounts(provider).isEmpty &&
                !(connectionFailed && failedProvider == provider))
              Align(
                alignment: AlignmentDirectional.centerStart,
                child: UiButton(
                  label:
                      '${recoverableAccounts(provider).length == 1 ? 'Reconnect' : 'Connect'} ${providerName(provider)}',
                  variant: UiButtonVariant.secondary,
                  onPressed: busy ? null : () => connectLinkProvider(provider),
                ),
              )
            else if (connectedAccounts(provider).isNotEmpty)
              Row(
                children: [
                  Expanded(
                    child:
                        connectedAccounts(provider).length == 1 &&
                            connectedAccounts(provider).single['id'] ==
                                linkAccounts[provider]
                        ? Text(
                            '${providerName(provider)} · ${accountLabel(connectedAccounts(provider).single)}',
                            style: ui.type.bodySmall,
                          )
                        : accountChoice(
                            provider,
                            linkAccounts[provider],
                            (id) => setState(() => linkAccounts[provider] = id),
                          ),
                  ),
                  connectionOptions(
                    provider,
                    selectedId: linkAccounts[provider],
                  ),
                ],
              ),
            if (connectedAccounts(provider).isEmpty &&
                recoverableAccounts(provider).isNotEmpty)
              Align(
                alignment: AlignmentDirectional.centerEnd,
                child: connectionOptions(
                  provider,
                  selectedId: recoverableAccounts(provider).length == 1
                      ? recoverableAccounts(provider).single['id'] as String
                      : null,
                ),
              ),
          ],
          SizedBox(height: ui.space.s3),
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
          if (!connected && available.isEmpty && !connectionFailed) ...[
            Text(
              'Import photos from ${providerName(widget.provider)}.',
              style: ui.type.body,
            ),
            SizedBox(height: ui.space.s4),
          ],
          if (available.isNotEmpty ||
              activeConnection?['account_id'] != null) ...[
            Row(
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      if (available.length > 1 ||
                          (available.isNotEmpty && !connected))
                        accountChoice(
                          widget.provider,
                          connectionId,
                          chooseAccount,
                        )
                      else
                        Text(
                          accountLabel(activeConnection!),
                          style: ui.type.body,
                        ),
                      if (connected)
                        Text('Connected', style: ui.type.bodySmall),
                    ],
                  ),
                ),
                connectionOptions(widget.provider, selectedId: connectionId),
              ],
            ),
            SizedBox(height: ui.space.s3),
          ],
          if (connected && widget.provider == 'google_drive' && folder == null)
            UiButton(
              label: 'Choose photos',
              variant: entries.isEmpty && selected.isEmpty
                  ? UiButtonVariant.primary
                  : UiButtonVariant.secondary,
              onPressed: busy ? null : picker,
            )
          else if (!connected && !connectionFailed && available.isEmpty)
            UiButton(
              label: 'Connect ${providerName(widget.provider)}',
              onPressed: busy ? null : () => connect(defaultAccess),
            ),
          if (available.isEmpty &&
              activeConnection?['account_id'] == null &&
              connections.any(
                (row) => row['state'] == 'disconnected' && row['error'] is Map,
              ))
            Align(
              alignment: AlignmentDirectional.centerEnd,
              child: connectionOptions(widget.provider),
            ),
        ],
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
        if (recoveryAction == 'file_access')
          Text(
            'Ask the owner for access or choose another photo.',
            style: ui.type.bodySmall,
          ),
        if (connectionFailed && !busy) ...[
          UiButton(label: 'Retry connection', onPressed: retryConnection),
        ] else if (message != null &&
            retryAction != null &&
            (recoveryAction == 'retry' || recoveryAction == 'administrator'))
          UiButton(
            label: 'Retry',
            variant: UiButtonVariant.secondary,
            onPressed: busy ? null : () => run(retryAction!),
          ),
        if (recoveryAction == 'administrator')
          UiDisclosure(
            title: 'Administrator help',
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'Share the details, then retry after access is restored.',
                  style: ui.type.bodySmall,
                ),
                SizedBox(height: ui.space.s2),
                UiButton(
                  label: administratorDetailsCopied
                      ? 'Administrator details copied'
                      : 'Copy administrator details',
                  leading: UiIcons.copy,
                  variant: UiButtonVariant.secondary,
                  onPressed: busy ? null : copyAdministratorDetails,
                ),
              ],
            ),
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
        if (sourceId != null || folder != null)
          UiDisclosure(
            title: 'Folder options',
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                UiCheckbox(
                  label: 'Include subfolders',
                  value: includeSubfolders,
                  onChanged: (value) =>
                      setState(() => includeSubfolders = value),
                ),
                UiButton(
                  label: 'Select folder photos',
                  variant: UiButtonVariant.secondary,
                  onPressed: busy ? null : selectFolder,
                ),
              ],
            ),
          ),
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
      ],
    );
  }

  double mathHeight(BuildContext context) =>
      (MediaQuery.sizeOf(context).height * .32).clamp(160, 360);
}
