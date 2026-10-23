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
import 'intake_picker_host.dart';

class IntakeSourcePicker extends StatefulWidget {
  const IntakeSourcePicker({
    super.key,
    required this.controller,
    required this.provider,
    this.initialSourceId,
    this.authSessionFactory,
    this.pickerHost = const IntakePickerHost(),
    this.active = true,
    this.onBusyChanged,
    this.showHeading = true,
  });
  final BulkIntakeController controller;
  final String provider;
  final String? initialSourceId;
  final bool active;
  final bool showHeading;
  final ValueChanged<bool>? onBusyChanged;
  final IntakeAuthSession Function()? authSessionFactory;
  final IntakePickerHost pickerHost;
  @override
  State<IntakeSourcePicker> createState() => _IntakeSourcePickerState();
}

// Controller identity is owner/collection scoped. Weak keys cannot leak a
// pending selection into a new signed-in user's controller or retain it forever.
final _sourceMemory = Expando<Map<String, Json>>('intake-source-selections');

class _IntakeSourcePickerState extends State<IntakeSourcePicker>
    with WidgetsBindingObserver {
  final links = TextEditingController();
  final filter = TextEditingController();
  final pickerFocus = FocusNode(debugLabel: 'Choose Drive photos');
  String phase = 'Loading account…';
  int generation = 0;
  bool foreground = true;
  String folderLabel = 'All files';
  List<Json> connections = [], entries = [], sources = [];
  final Map<String, Json> selected = {};
  final Map<String, String> admissionIdentities = {};
  final Map<String, String> linkAccounts = {};
  final List<(String, String)> parents = [];
  String? connectionId, sourceId, folder, cursor, pickerId, message;
  String? inlinePickerUrl;
  int frameGeneration = 0;
  int? focusReturnGeneration;
  ({String connectionId, String pickerId, String accountId})? selectionToResume;
  bool busy = false, includeSubfolders = false, polling = false;
  bool administratorDetailsCopied = false;
  Timer? timer;
  IntakeAuthSession? authSession;
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
    foreground = isVisible(WidgetsBinding.instance.lifecycleState);
    WidgetsBinding.instance.addObserver(this);
    c.addListener(controllerChanged);
    restoreSource();
    unawaited(load());
    timer = Timer.periodic(intakePollInterval, (_) => poll());
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    c.removeListener(controllerChanged);
    detachInlinePicker();
    retainSource();
    timer?.cancel();
    authSession?.close();
    pickerFocus.dispose();
    links.dispose();
    filter.dispose();
    super.dispose();
  }

  @override
  void didUpdateWidget(covariant IntakeSourcePicker oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.active != oldWidget.active) {
      generation++;
      if (!widget.active) {
        detachInlinePicker();
        authSession?.close();
      }
      if (widget.active) unawaited(poll());
    }
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    foreground = isVisible(state);
    if (foreground) unawaited(poll());
  }

  // Inactive also covers a visible desktop window without keyboard focus and
  // transient system sheets. Only hidden/paused views should stop reconciling.
  static bool isVisible(AppLifecycleState? state) =>
      state != AppLifecycleState.hidden &&
      state != AppLifecycleState.paused &&
      state != AppLifecycleState.detached;

  void controllerChanged() {
    if (mounted) setState(() {});
  }

  int newSelectionCount(Iterable<Json> rows) {
    final admitted = c.items
        .map((item) => item.data['client_id'])
        .whereType<String>()
        .toSet();
    return rows
        .map(retainAdmission)
        .where(
          (row) =>
              row['client_id'] == null || !admitted.contains(row['client_id']),
        )
        .length;
  }

  String get memoryKey =>
      '${c.sourceContextKey}:${widget.provider}:${widget.initialSourceId ?? ''}';

  void retainSource() {
    final memory = _sourceMemory[c] ??= {};
    memory[memoryKey] = {
      'connection_id': connectionId,
      'account_id': activeConnection?['account_id'],
      'source_id': sourceId,
      'folder': folder,
      'folder_label': folderLabel,
      'cursor': cursor,
      'picker_id': pickerId,
      'entries': entries,
      'selected': selected.values.toList(),
      'admission_identities': Map.of(admissionIdentities),
      'links': links.text,
      'link_accounts': Map.of(linkAccounts),
      'filter': filter.text,
      'parents': [
        for (final parent in parents) [parent.$1, parent.$2],
      ],
      if (selectionToResume case final retained?)
        'resume': {
          'connection_id': retained.connectionId,
          'picker_id': retained.pickerId,
          'account_id': retained.accountId,
        },
    };
  }

  void restoreSource() {
    final saved = _sourceMemory[c]?[memoryKey];
    if (saved == null) return;
    connectionId = saved['connection_id'] as String?;
    sourceId = saved['source_id'] as String?;
    folder = saved['folder'] as String?;
    folderLabel = saved['folder_label'] as String? ?? 'All files';
    cursor = saved['cursor'] as String?;
    pickerId = saved['picker_id'] as String?;
    entries = objects(saved['entries']);
    for (final row in objects(saved['selected'])) {
      selected[selectionKey(row)] = row;
    }
    admissionIdentities.addAll(
      Map<String, String>.from(saved['admission_identities'] as Map? ?? {}),
    );
    links.text = saved['links'] as String? ?? '';
    filter.text = saved['filter'] as String? ?? '';
    linkAccounts.addAll(
      Map<String, String>.from(saved['link_accounts'] as Map? ?? {}),
    );
    for (final parent in saved['parents'] as List? ?? []) {
      parents.add((parent[0] as String, parent[1] as String));
    }
    if (saved['resume'] case final Map retained) {
      selectionToResume = (
        connectionId: retained['connection_id'] as String,
        pickerId: retained['picker_id'] as String,
        accountId: retained['account_id'] as String,
      );
    }
  }

  Future<void> run(
    Future<void> Function() action, {
    String label = 'Loading photos…',
  }) async {
    if (busy) return;
    final epoch = ++generation;
    setState(() {
      busy = true;
      phase = label;
      message = null;
      recoveryAction = null;
      administratorDetailsCopied = false;
    });
    widget.onBusyChanged?.call(true);
    retryAction = action;
    try {
      await action();
    } catch (e) {
      if (mounted && generation == epoch) {
        setState(() {
          message = c.message(e);
          recoveryAction = e is ApiFailure
              ? (e.details['action'] as String? ?? 'retry')
              : 'retry';
        });
      }
    } finally {
      if (mounted) {
        setState(() => busy = false);
        widget.onBusyChanged?.call(false);
        restorePickerFocus();
      }
    }
  }

  Future<void> load() => run(() async {
    if (widget.provider == 'url') {
      final replies = await Future.wait([
        for (final name in ['google_drive', 'dropbox'])
          c.call('GET', '/connections', query: {'provider': name}),
      ]);
      final rows = [for (final reply in replies) ...objects(reply['items'])];
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
      if (mounted) {
        setState(() {
          sources = objects(result['items']);
          if (sourceId != null &&
              !sources.any((row) => row['id'] == sourceId)) {
            sourceId = null;
            folder = null;
            entries = [];
            parents.clear();
          }
        });
      }
      if (sourceId != null ||
          sources.any((row) => row['id'] == widget.initialSourceId)) {
        sourceId ??= widget.initialSourceId;
        folder ??= '';
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
      if (connectionId != null &&
          !connections.any((row) => row['id'] == connectionId)) {
        connectionId = null;
        closePicker();
        entries = [];
        selected.clear();
        parents.clear();
        folder = null;
      }
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
      folder ??= '';
      await browse();
    } else if (pickerId != null) {
      await refreshSelection();
    }
  }, label: 'Loading account…');

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
  }) => run(
    () => connectAccount(access, provider: provider, reconnectId: reconnectId),
  );

  Future<void> connectAccount(
    String access, {
    String? provider,
    String? reconnectId,
    IntakeAuthSession? initiatingSession,
  }) async {
    final epoch = generation;
    final controller = c;
    final contextKey = c.sourceContextKey;
    final retained = selectionToResume;
    final resumeSelection =
        retained != null &&
        reconnectId == retained.connectionId &&
        connectionId == retained.connectionId &&
        activeConnection?['account_id'] == retained.accountId;
    closePicker(keepSelection: resumeSelection);
    if (resumeSelection) pickerId = retained.pickerId;
    final name = provider ?? widget.provider;
    failedProvider = name;
    connectingProvider = name;
    phase = 'Connecting to ${providerName(name)}…';
    reconnectAction = () =>
        connect(access, provider: name, reconnectId: reconnectId);
    final session = initiatingSession ?? newAuthSession();
    authSession = session;
    bool current() =>
        mounted &&
        widget.active &&
        generation == epoch &&
        identical(c, controller) &&
        c.sourceContextKey == contextKey &&
        identical(authSession, session);
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
      if (!current()) return;
      setState(() => rememberConnection(result, showError: false));
      final continueToPicker =
          name == 'google_drive' &&
          access == 'files' &&
          widget.provider != 'url';
      final nativePicker = continueToPicker && session.returnOrigin == null;
      if (nativePicker) pickerId = result['picker_id'] as String?;
      final response = await session.authenticate(
        result['authorization_url'] as String,
      );
      // Consent owns its popup; file selection has a separate inline lifetime.
      session.close();
      if (!current()) return;
      final completed = await c.call(
        'POST',
        '/connections/complete',
        body: {...response, 'session_proof': proof},
      );
      if (!current()) return;
      setState(() => rememberConnection(completed));
      if (completed['state'] == 'connected') {
        reconnectAction = null;
        folder = null;
        cursor = null;
        parents.clear();
        if (widget.provider != 'url') entries = [];
        if (resumeSelection &&
            completed['id'] == retained.connectionId &&
            completed['account_id'] == retained.accountId) {
          pickerId = retained.pickerId;
          await refreshSelection();
        } else if (widget.provider == 'url') {
          linkAccounts[name] = completed['id'] as String;
        } else if (nativePicker) {
          retryAction = pick;
          if (completed['selection'] is Map) {
            await updateSelection(
              Map<String, dynamic>.from(completed['selection'] as Map),
            );
          }
        } else if (continueToPicker) {
          // If Picker setup fails, retry selection using the connected account.
          retryAction = pick;
          await openPicker();
        } else {
          folder = '';
          retryAction = browse;
          await browse();
        }
      }
    } on ApiFailure catch (failure) {
      if (failure.code != 'authorization_cancelled') rethrow;
      if (!current()) return;
      final cancelledConnection = connectionId;
      Json? confirmed;
      if (cancelledConnection != null) {
        try {
          confirmed = await c.call('GET', '/connections/$cancelledConnection');
        } catch (_) {
          // The initiating request may have changed the server's authorization
          // state. Keep that last confirmed state, never restore stale Connected.
        }
      }
      if (!current()) return;
      setState(() {
        closePicker(keepSelection: resumeSelection);
        if (resumeSelection) pickerId = retained.pickerId;
        if (confirmed != null) {
          rememberConnection(confirmed, showError: false);
        }
        if (activeConnection?['state'] == 'connected') {
          reconnectAction = null;
        }
        message = null;
        recoveryAction = null;
      });
    } finally {
      session.close();
      if (identical(authSession, session)) {
        authSession = null;
        connectingProvider = null;
      }
    }
  }

  void applySelection(Json picker) {
    clearInlinePicker();
    closePicker();
    if (!mounted) return;
    setState(() {
      message = null;
      recoveryAction = null;
      retryAction = pick;
      entries = objects(picker['items']);
      selectReturnedPhotos(entries);
      final failures = objects(picker['failures']);
      if (failures.isNotEmpty) {
        final availableCount = entries.length;
        entries = [
          ...entries,
          for (final row in failures)
            {
              ...row,
              'filename': row['filename'] ?? row['id'],
              'supported': false,
            },
        ];
        message =
            '$availableCount available · ${failures.length} need access or another selection. Available photos are retained.';
      }
    });
  }

  Future<void> updateSelection(Json picker) async {
    if (!mounted) return;
    if (const ['cancelled', 'expired'].contains(picker['state'])) {
      clearInlinePicker();
      closePicker();
      setState(() {});
      return;
    }
    final retained = selectionToResume;
    final error = picker['error'];
    if (picker['state'] == 'failed') {
      // Stop polling the failed authorization while retaining the original
      // selection for another attempt with the same provider account.
      clearInlinePicker();
      closePicker(keepSelection: retained != null);
      setState(() {
        message = error is Map
            ? textOf(error['message'])
            : 'The connection could not be completed. Try again.';
        recoveryAction = error is Map ? error['action'] as String? : 'connect';
        failedProvider = widget.provider;
        retryAction = pick;
      });
      return;
    }
    if (retained != null &&
        pickerId != retained.pickerId &&
        connectionId == retained.connectionId &&
        activeConnection?['account_id'] == retained.accountId &&
        activeConnection?['state'] == 'connected' &&
        ['authorized', 'selecting', 'selected'].contains(picker['state'])) {
      // A lost reconnect reply may recover through the new native OAuth
      // session. Resume the original IDs rather than its new Picker selection.
      pickerId = retained.pickerId;
      await refreshSelection();
      return;
    }
    if (picker['state'] == 'selected') {
      applySelection(picker);
      return;
    }
    if (picker['progress'] is! Map) return;
    if (inlinePickerUrl != null) setState(clearInlinePicker);
    final progress = picker['progress'] as Map;
    final account = activeConnection?['account_id'];
    if (connectionId != null && pickerId != null && account is String) {
      selectionToResume = (
        connectionId: connectionId!,
        pickerId: pickerId!,
        accountId: account,
      );
    }
    setState(() {
      message = error is Map
          ? textOf(error['message'])
          : 'Checking ${progress['processed']} of ${progress['total']} photos…';
      recoveryAction = error is Map ? error['action'] as String? : null;
      failedProvider = widget.provider;
      retryAction = retrySelection;
    });
  }

  Future<void> retrySelection() async {
    final requestedConnection = connectionId;
    final requestedPicker = pickerId;
    final requestedGeneration = generation;
    if (requestedConnection == null || requestedPicker == null) return;
    final Json result;
    try {
      // A long-lived client can outlast a runtime upgrade. Probe the retry
      // contract instead of trusting capabilities cached before that upgrade.
      result = await c.call(
        'POST',
        '/connections/$requestedConnection/picker/$requestedPicker/retry',
      );
    } on ApiFailure catch (error) {
      if (error.status != 404 && error.status != 405) rethrow;
      if (mounted &&
          connectionId == requestedConnection &&
          pickerId == requestedPicker &&
          generation == requestedGeneration) {
        await refreshSelection();
      }
      return;
    }
    if (!mounted ||
        connectionId != requestedConnection ||
        pickerId != requestedPicker ||
        generation != requestedGeneration) {
      return;
    }
    await updateSelection(result);
  }

  Future<void> refreshSelection() async {
    final requestedConnection = connectionId;
    final requestedPicker = pickerId;
    final requestedGeneration = generation;
    if (requestedConnection == null || requestedPicker == null) return;
    final picker = await c.call(
      'GET',
      '/connections/$requestedConnection/picker/$requestedPicker',
    );
    if (!mounted ||
        connectionId != requestedConnection ||
        pickerId != requestedPicker ||
        generation != requestedGeneration) {
      return;
    }
    await updateSelection(picker);
  }

  Future<void> poll() async {
    if (!widget.active ||
        !foreground ||
        busy ||
        polling ||
        connectionId == null ||
        !(ModalRoute.of(context)?.isCurrent ?? true)) {
      return;
    }
    if (pickerId == null &&
        activeConnection?['state'] != 'needs_authorization') {
      return;
    }
    polling = true;
    final requestedConnection = connectionId;
    final requestedGeneration = generation;
    try {
      if (activeConnection?['state'] == 'connected' && pickerId != null) {
        await refreshSelection();
        return;
      }
      final result = await c.call('GET', '/connections/$requestedConnection');
      if (!mounted ||
          busy ||
          connectionId != requestedConnection ||
          generation != requestedGeneration) {
        return;
      }
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
        await refreshSelection();
      }
    } catch (_) {
      /* Keep the confirmed connection state while offline. */
    } finally {
      polling = false;
    }
  }

  Future<void> browse({String? after}) async {
    phase = after == null ? 'Loading folder…' : 'Loading more photos…';
    final requestedConnection = connectionId,
        requestedSource = sourceId,
        requestedFolder = folder;
    final path = sourceId != null
        ? '/sources/$sourceId/browse'
        : '/connections/$connectionId/browse';
    final result = await c.call(
      'POST',
      path,
      body: {'folder': folder ?? '', 'cursor': ?after},
    );
    if (mounted &&
        connectionId == requestedConnection &&
        sourceId == requestedSource &&
        folder == requestedFolder) {
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

  void closePicker({bool keepSelection = false}) {
    detachInlinePicker();
    pickerId = null;
    if (!keepSelection) selectionToResume = null;
  }

  void clearInlinePicker() {
    final hadFrame = inlinePickerUrl != null;
    inlinePickerUrl = null;
    if (!hadFrame) return;
    frameGeneration++;
    focusReturnGeneration = frameGeneration;
    restorePickerFocus();
  }

  void restorePickerFocus() {
    final epoch = focusReturnGeneration;
    if (epoch == null) return;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted &&
          widget.active &&
          !busy &&
          frameGeneration == epoch &&
          focusReturnGeneration == epoch &&
          pickerFocus.canRequestFocus) {
        focusReturnGeneration = null;
        pickerFocus.requestFocus();
      }
    });
  }

  void detachInlinePicker() {
    if (inlinePickerUrl == null) return;
    final connection = connectionId, id = pickerId;
    clearInlinePicker();
    focusReturnGeneration = null;
    // A close/source switch revokes only an uncommitted chooser. Keep its
    // handle until the next authenticated read settles any lost selection ACK.
    if (connection != null && id != null) {
      unawaited(
        c
            .call('POST', '/connections/$connection/picker/$id/cancel')
            .then<void>((_) {}, onError: (Object _) {}),
      );
    }
  }

  Future<bool> settleInlinePicker(
    String action, {
    String? failureMessage,
  }) async {
    final connection = connectionId, id = pickerId, epoch = generation;
    if (connection == null || id == null) return true;
    if (mounted) setState(clearInlinePicker);
    Json reply;
    try {
      reply = await c.call(
        action == 'selected' ? 'GET' : 'POST',
        '/connections/$connection/picker/$id${action == 'selected' ? '' : '/cancel'}',
      );
    } catch (_) {
      // A selection/cancel may have committed before its reply disappeared.
      reply = await c.call('GET', '/connections/$connection/picker/$id');
    }
    if (!mounted ||
        connectionId != connection ||
        pickerId != id ||
        generation != epoch) {
      return false;
    }
    if (const ['selecting', 'selected', 'failed'].contains(reply['state'])) {
      await updateSelection(reply);
      return false;
    }
    if (!const ['cancelled', 'expired'].contains(reply['state'])) {
      throw const ApiFailure(
        'Could not confirm the Drive selection. Retry to check the saved selection.',
        details: {'action': 'retry'},
      );
    }
    closePicker();
    setState(() {
      message = failureMessage;
      recoveryAction = failureMessage == null ? null : 'retry';
      retryAction = pick;
    });
    return true;
  }

  void inlineEvent(String action, int epoch, String id) {
    if (!mounted ||
        !widget.active ||
        frameGeneration != epoch ||
        pickerId != id ||
        action == 'ready') {
      return;
    }
    unawaited(
      run(() async {
        await settleInlinePicker(
          action,
          failureMessage: action == 'error'
              ? 'Google Drive could not finish this selection. Retry to choose photos.'
              : null,
        );
      }, label: 'Checking Drive selection…'),
    );
  }

  Future<void> picker() => run(pick);

  Future<void> pick() async {
    if (widget.pickerHost.returnOrigin == null) {
      closePicker();
      final session = newAuthSession();
      // Native Picker is part of the provider's system-browser consent flow.
      // Reconnect preserves the account that owns any already selected photos.
      return connectAccount(
        'files',
        provider: 'google_drive',
        reconnectId: activeConnection?['access'] == 'files'
            ? connectionId
            : null,
        initiatingSession: session,
      );
    }
    if (pickerId != null && !await settleInlinePicker('cancelled')) return;
    await openPicker();
    if (mounted) {
      setState(() {
        folder = null;
        cursor = null;
        parents.clear();
      });
    }
  }

  Future<void> openPicker() async {
    final existing = connections
        .where(
          (row) => row['id'] == connectionId && row['state'] == 'connected',
        )
        .firstOrNull;
    if (existing == null) {
      throw const ApiFailure('Connect Google Drive first.', code: 'connect');
    }
    final connection = existing['id'] as String, epoch = generation;
    final origin = widget.pickerHost.returnOrigin;
    final result = await c.call(
      'POST',
      '/connections/$connection/picker',
      body: {'return_origin': origin},
    );
    if (!mounted ||
        !widget.active ||
        connectionId != connection ||
        generation != epoch) {
      return;
    }
    final id = result['id'] as String, url = result['url'] as String;
    final uri = Uri.tryParse(url);
    final secure =
        uri != null &&
        (uri.scheme == 'https' ||
            (uri.scheme == 'http' &&
                const ['127.0.0.1', 'localhost', '::1'].contains(uri.host)));
    if (origin == null ||
        uri == null ||
        !secure ||
        uri.host.isEmpty ||
        uri.userInfo.isNotEmpty ||
        uri.path != '/v1/intake/picker' ||
        uri.queryParametersAll['embed_origin']?.singleOrNull != origin ||
        uri.queryParametersAll['picker_id']?.singleOrNull != id) {
      throw const ApiFailure(
        'Drive selection is being updated. Try again shortly.',
        details: {'action': 'retry'},
      );
    }
    setState(() {
      pickerId = id;
      inlinePickerUrl = url;
      frameGeneration++;
      focusReturnGeneration = null;
      retryAction = pick;
    });
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
      selectReturnedPhotos(entries);
      message =
          '${result['discovered']} found · ${result['unsupported']} unsupported · ${result['inaccessible']} inaccessible';
    });
  });

  String? linkProvider(String value) {
    final host = Uri.tryParse(value)?.host;
    return ['drive.google.com', 'docs.google.com'].contains(host)
        ? 'google_drive'
        : ['dropbox.com', 'www.dropbox.com'].contains(host)
        ? 'dropbox'
        : null;
  }

  Future<List<Json>> checkLink(String value) async {
    final account = linkAccounts[linkProvider(value)];
    try {
      final result = await c.call(
        'POST',
        '/resolve',
        body: {'url': value, 'connection_id': ?account},
      );
      return [
        for (final row in objects(result['items']))
          {...row, 'link_url': value, 'link_account_id': account},
      ];
    } catch (e) {
      return [
        {
          'id': value,
          'filename': value,
          'supported': false,
          'link_url': value,
          'link_account_id': account,
          'error': e is ApiFailure
              ? {...e.details, 'message': c.message(e), 'code': e.code}
              : {'message': c.message(e), 'action': 'retry'},
          'retry_url': value,
        },
      ];
    }
  }

  Future<void> retryLink(Json failed) => run(() async {
    final value = failed['retry_url'] as String;
    final error = failed['error'];
    final provider = linkProvider(value);
    if (error is Map && error['action'] == 'connect' && provider != null) {
      final account = linkAccounts[provider];
      final known = connections
          .where((row) => row['id'] == account)
          .firstOrNull;
      await connectAccount(
        known?['access'] as String? ?? 'folders',
        provider: provider,
        reconnectId: account,
      );
      if (!mounted) return;
    }
    final rows = await checkLink(value);
    if (!mounted) return;
    setState(() {
      final index = entries.indexOf(failed);
      if (index >= 0) {
        entries.removeAt(index);
        entries.insertAll(index, rows);
      }
      selectReturnedPhotos(rows);
    });
  }, label: 'Checking link…');

  Future<void> resolveLinks() => run(() async {
    final values = links.text
        .split(RegExp(r'\s+'))
        .where((value) => value.isNotEmpty)
        .toSet()
        .toList();
    if (values.isEmpty || values.length > 500) {
      throw const ApiFailure(
        'Enter one supported link per line, within the batch limit.',
        code: 'link_limit',
      );
    }
    bool currentLink(Json row) {
      final url = row['link_url'];
      return url is String &&
          values.contains(url) &&
          row['link_account_id'] == linkAccounts[linkProvider(url)];
    }

    setState(() {
      entries.removeWhere((row) => !currentLink(row));
      selected.removeWhere((_, row) => !currentLink(row));
    });
    final previous = List<Json>.of(entries);
    var checked = 0;
    for (final value in values) {
      final retained = previous
          .where(
            (row) =>
                row['link_url'] == value &&
                row['retry_url'] == null &&
                row['link_account_id'] == linkAccounts[linkProvider(value)],
          )
          .toList();
      // Existing successes retain client IDs and explicit deselections. Only
      // new/failed links need another request or automatic selection.
      if (retained.isNotEmpty) {
        checked++;
        continue;
      }
      final rows = await checkLink(value);
      if (!mounted) return;
      setState(() {
        checked++;
        phase = 'Checking $checked of ${values.length} links…';
        entries.removeWhere((row) => row['retry_url'] == value);
        entries.addAll(rows);
        selectReturnedPhotos(rows);
      });
    }
  }, label: 'Checking links…');

  Future<void> addSelected() => run(() async {
    if (newSelectionCount(selected.values) > 500 - c.visible.length) {
      throw const ApiFailure(
        'This batch is full. Choose fewer photos.',
        code: 'batch_limit',
      );
    }
    final photos = selected.values
        .map(
          (row) => <String, dynamic>{
            'client_id': row['client_id'] ??= admissionIdentities.putIfAbsent(
              sourceIdentity(row),
              intakeClientId,
            ),
            'filename': row['filename'],
            'media_type': row['media_type'] ?? 'application/octet-stream',
            'source': row['source'],
            'photo_sensitive': false,
          },
        )
        .toList();
    await c.addSource(photos);
    // The controller may reconcile a persisted admission from an earlier app
    // session. Keep its exact IDs when these provider rows are selected again.
    for (final photo in photos) {
      admissionIdentities[sourceIdentity(photo)] = photo['client_id'] as String;
    }
    for (final row in selected.values) {
      retainAdmission(row);
    }
    if (mounted && c.error == null) {
      selected.clear();
      entries = [];
      closePicker();
      Navigator.of(context).pop();
    } else if (mounted) {
      setState(() => message = c.error);
    }
  }, label: 'Adding photos to your draft…');

  void selectReturnedPhotos(List<Json> rows) {
    for (final row in rows.where(
      (row) => row['supported'] == true && row['kind'] != 'folder',
    )) {
      selected[selectionKey(row)] = retainAdmission(row);
    }
    if (newSelectionCount(selected.values) + c.visible.length > 500) {
      message =
          'Choose ${newSelectionCount(selected.values) + c.visible.length - 500} fewer photos to fit this batch.';
    }
  }

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
    phase = 'Loading photo preview…';
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
  String sourceIdentity(Json row) {
    Object? canonical(Object? value) {
      if (value is Map) {
        final keys = value.keys.cast<String>().toList()..sort();
        return {for (final key in keys) key: canonical(value[key])};
      }
      if (value is List) return value.map(canonical).toList();
      return value;
    }

    return jsonEncode(
      canonical({
        'source': row['source'],
        'filename': row['filename'],
        'media_type': row['media_type'] ?? 'application/octet-stream',
      }),
    );
  }

  Json retainAdmission(Json row) {
    bool removed(String? id) =>
        id != null &&
        c.items.any((item) => item.removed && item.data['client_id'] == id);
    if (removed(row['client_id'] as String?)) row.remove('client_id');
    final id =
        c.retainedSourceClientId({
          'filename': row['filename'],
          'media_type': row['media_type'] ?? 'application/octet-stream',
          'source': row['source'],
          'photo_sensitive': false,
        }) ??
        admissionIdentities[sourceIdentity(row)];
    if (id != null && !removed(id)) row['client_id'] = id;
    if (removed(admissionIdentities[sourceIdentity(row)])) {
      admissionIdentities.remove(sourceIdentity(row));
    }
    return row;
  }

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
    final connectionIntro =
        cloud &&
        !connected &&
        available.isEmpty &&
        !connectionFailed &&
        !busy &&
        message == null;
    final header = Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: connectionIntro
          ? CrossAxisAlignment.center
          : CrossAxisAlignment.stretch,
      children: [
        if (connectionIntro) ...[
          const UiIcon(UiIcons.cloudUpload, size: UiIconSize.display),
          SizedBox(height: ui.space.s4),
        ],
        if (widget.showHeading)
          Semantics(
            header: true,
            child: Text(
              widget.provider == 'url'
                  ? 'Import links'
                  : widget.provider == 'storage'
                  ? 'Registered storage'
                  : providerName(widget.provider),
              style: ui.type.title,
            ),
          ),
        if (widget.showHeading) SizedBox(height: ui.space.s4),
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
          if (sources.isNotEmpty)
            UiSelect<String>(
              label: 'Storage location',
              placeholder: 'Choose a location',
              value: sourceId,
              options: [
                for (final source in sources)
                  UiSelectOption(
                    value: source['id'] as String,
                    label: textOf(source['label'], 'Storage'),
                  ),
              ],
              onChanged: busy
                  ? null
                  : (id) => run(() async {
                      sourceId = id;
                      folder = '';
                      folderLabel = textOf(
                        sources.firstWhere((row) => row['id'] == id)['label'],
                        'Storage',
                      );
                      parents.clear();
                      filter.clear();
                      entries = [];
                      await browse();
                    }, label: 'Loading storage photos…'),
            ),
        ] else ...[
          if (!connected && available.isEmpty && !connectionFailed) ...[
            Text(
              'Import photos from ${providerName(widget.provider)}.',
              style: ui.type.body,
              textAlign: connectionIntro ? TextAlign.center : null,
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
              focusNode: pickerFocus,
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
        if (parents.isNotEmpty || folder != null)
          Wrap(
            crossAxisAlignment: WrapCrossAlignment.center,
            children: [
              if (parents.isNotEmpty)
                UiButton(
                  label: 'Back to ${parents.last.$2}',
                  leading: UiIcons.back,
                  variant: UiButtonVariant.ghost,
                  onPressed: busy
                      ? null
                      : () => run(() async {
                          final parent = parents.removeLast();
                          folder = parent.$1;
                          folderLabel = parent.$2;
                          filter.clear();
                          await browse();
                        }),
                ),
              Text(folderLabel, style: ui.type.bodySmall),
            ],
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
                  onChanged: busy
                      ? null
                      : (value) => setState(() => includeSubfolders = value),
                ),
                UiButton(
                  label: 'Select folder photos',
                  variant: UiButtonVariant.secondary,
                  onPressed: busy ? null : selectFolder,
                ),
              ],
            ),
          ),
        if (entries.isNotEmpty) ...[
          SizedBox(height: ui.space.s3),
          UiField(
            label: 'Filter loaded files',
            controller: filter,
            onChanged: (_) => setState(() {}),
            helpText: cursor == null
                ? null
                : 'More files are available. This filters loaded files only.',
          ),
          Wrap(
            spacing: ui.space.s2,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: [
              UiButton(
                label: 'Select visible photos',
                leading: UiIcons.selectAll,
                variant: UiButtonVariant.ghost,
                onPressed: busy ? null : selectVisible,
              ),
              if (selected.isNotEmpty)
                UiButton(
                  label: 'Clear selection',
                  variant: UiButtonVariant.ghost,
                  onPressed: busy ? null : () => setState(selected.clear),
                ),
              Text(
                '${entries.where((row) => row['kind'] != 'folder' && row['supported'] == true).length} available · ${entries.where((row) => row['kind'] != 'folder' && row['supported'] != true).length} unavailable',
                style: ui.type.bodySmall,
              ),
            ],
          ),
        ],
        if (busy) ...[
          SizedBox(height: ui.space.s2),
          Semantics(
            liveRegion: true,
            child: Text(phase, style: ui.type.bodySmall),
          ),
          SizedBox(height: ui.space.s2),
          UiProgress.bar(semanticsLabel: phase),
        ],
      ],
    );
    return LayoutBuilder(
      builder: (context, constraints) {
        final rows = visibleEntries;
        final workspaceHeight = constraints.hasBoundedHeight
            ? constraints.maxHeight
            : MediaQuery.sizeOf(context).height * .78;
        final scrollingFooter =
            constraints.hasBoundedHeight &&
            constraints.maxHeight < ui.space.paneDetailMin;
        if (inlinePickerUrl case final url? when widget.active) {
          final epoch = frameGeneration, id = pickerId!;
          return SizedBox(
            height: workspaceHeight,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Padding(
                  padding: EdgeInsets.all(ui.space.s3),
                  child: Wrap(
                    spacing: ui.space.s3,
                    runSpacing: ui.space.s2,
                    alignment: WrapAlignment.spaceBetween,
                    crossAxisAlignment: WrapCrossAlignment.center,
                    children: [
                      Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            accountLabel(activeConnection!),
                            style: ui.type.bodySmall,
                          ),
                          Text('Connected', style: ui.type.bodySmall),
                        ],
                      ),
                      UiButton(
                        label: selected.isEmpty
                            ? 'Cancel choosing photos'
                            : 'Back to selected photos',
                        leading: UiIcons.back,
                        variant: UiButtonVariant.secondary,
                        onPressed: () => run(() async {
                          await settleInlinePicker('cancelled');
                        }, label: 'Checking Drive selection…'),
                      ),
                    ],
                  ),
                ),
                Expanded(
                  child: widget.pickerHost.buildFrame(
                    url: url,
                    pickerId: id,
                    onEvent: (action) => inlineEvent(action, epoch, id),
                    onFailure: (problem) {
                      if (!mounted ||
                          !widget.active ||
                          frameGeneration != epoch ||
                          pickerId != id) {
                        return;
                      }
                      unawaited(
                        run(() async {
                          await settleInlinePicker(
                            'error',
                            failureMessage: problem,
                          );
                        }, label: 'Checking Drive selection…'),
                      );
                    },
                  ),
                ),
              ],
            ),
          );
        }
        final hasSelection = entries.isNotEmpty || selected.isNotEmpty;
        return SizedBox(
          height: workspaceHeight,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Expanded(
                child: CustomScrollView(
                  key: const ValueKey('source-files'),
                  slivers: [
                    if (connectionIntro)
                      SliverToBoxAdapter(
                        child: ConstrainedBox(
                          constraints: BoxConstraints(
                            minHeight: workspaceHeight,
                          ),
                          child: Center(
                            child: Padding(
                              padding: EdgeInsets.all(ui.space.s6),
                              child: header,
                            ),
                          ),
                        ),
                      )
                    else
                      SliverPadding(
                        padding: EdgeInsets.all(ui.space.s4),
                        sliver: SliverToBoxAdapter(child: header),
                      ),
                    if (rows.isNotEmpty)
                      SliverPadding(
                        padding: EdgeInsets.symmetric(horizontal: ui.space.s4),
                        sliver: SliverList.builder(
                          itemCount: rows.length,
                          itemBuilder: (context, index) => fileRow(rows[index]),
                        ),
                      ),
                    if (!busy &&
                        rows.isEmpty &&
                        (folder != null || entries.isNotEmpty))
                      SliverPadding(
                        padding: EdgeInsets.all(ui.space.s6),
                        sliver: SliverToBoxAdapter(
                          child: Text(
                            filter.text.isNotEmpty
                                ? 'No loaded files match this filter.'
                                : 'No photos in this folder.',
                            style: ui.type.body,
                          ),
                        ),
                      ),
                    if (cursor != null)
                      SliverToBoxAdapter(
                        child: Padding(
                          padding: EdgeInsets.all(ui.space.s4),
                          child: UiButton(
                            label: 'Load more files',
                            variant: UiButtonVariant.ghost,
                            onPressed: busy
                                ? null
                                : () => run(
                                    () => browse(after: cursor),
                                    label: 'Loading more photos…',
                                  ),
                          ),
                        ),
                      ),
                    if (hasSelection && scrollingFooter)
                      SliverToBoxAdapter(child: selectionFooter()),
                  ],
                ),
              ),
              if (hasSelection && !scrollingFooter) selectionFooter(),
            ],
          ),
        );
      },
    );
  }

  Widget selectionFooter() {
    final ui = context.ui;
    final count = Semantics(
      liveRegion: c.addingSources,
      child: Text(
        c.addingSources
            ? c.sourceAddLabel
            : '${selected.length} selected · ${500 - c.visible.length} spaces in this batch',
        style: ui.type.bodySmall,
      ),
    );
    final action = UiButton(
      label:
          'Add ${selected.length} ${selected.length == 1 ? 'photo' : 'photos'}',
      onPressed:
          busy ||
              selected.isEmpty ||
              newSelectionCount(selected.values) + c.visible.length > 500
          ? null
          : addSelected,
    );
    return Container(
      decoration: BoxDecoration(
        border: Border(top: BorderSide(color: ui.color.boundary)),
      ),
      padding: EdgeInsets.all(ui.space.s4),
      child: LayoutBuilder(
        builder: (context, constraints) =>
            constraints.maxWidth >= ui.space.dialogMax &&
                MediaQuery.textScalerOf(context).scale(1) < 1.5
            ? Row(
                children: [
                  Expanded(child: count),
                  action,
                ],
              )
            : Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                mainAxisSize: MainAxisSize.min,
                children: [
                  count,
                  SizedBox(height: ui.space.s2),
                  action,
                ],
              ),
      ),
    );
  }

  List<Json> get visibleEntries {
    final query = filter.text.trim().toLowerCase();
    return query.isEmpty
        ? entries
        : entries
              .where(
                (row) => textOf(row['filename']).toLowerCase().contains(query),
              )
              .toList();
  }

  void selectVisible() => setState(() {
    final next = {...selected};
    for (final row in visibleEntries.where(
      (row) => row['kind'] != 'folder' && row['supported'] == true,
    )) {
      next[selectionKey(row)] = retainAdmission(row);
    }
    if (newSelectionCount(next.values) + c.visible.length > 500) {
      message = 'Choose fewer photos or narrow this folder to fit the batch.';
      return;
    }
    selected
      ..clear()
      ..addAll(next);
  });

  String sourceError(dynamic error) => error is Map
      ? textOf(error['message'], 'This photo is unavailable.')
      : textOf(error);

  Widget fileRow(Json row) {
    final ui = context.ui;
    final name = textOf(
      row['filename'],
      row['kind'] == 'folder' ? 'Folder' : 'Photo',
    );
    if (row['kind'] == 'folder') {
      return UiListRow(
        title: name,
        leading: const UiIcon(UiIcons.source),
        onPressed: busy
            ? null
            : () => run(() async {
                if (row['connection_id'] != null) {
                  connectionId = row['connection_id'] as String;
                }
                if (row['source_id'] != null) {
                  sourceId = row['source_id'] as String;
                }
                parents.add((folder ?? '', folderLabel));
                folder = row['id'] as String;
                folderLabel = name;
                filter.clear();
                await browse();
              }, label: 'Loading folder…'),
      );
    }
    final key = selectionKey(row);
    final supported = row['supported'] == true;
    final detail = row['error'] != null
        ? sourceError(row['error'])
        : 'Unsupported file';
    return Container(
      decoration: BoxDecoration(
        border: Border(bottom: BorderSide(color: ui.color.boundary)),
      ),
      padding: EdgeInsets.symmetric(vertical: ui.space.s2),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                UiCheckbox(
                  label: name,
                  value: selected.containsKey(key),
                  disabledReason: supported
                      ? null
                      : row['error'] == null
                      ? 'Unsupported file'
                      : sourceError(row['error']),
                  onChanged: !supported || busy
                      ? null
                      : (value) => setState(() {
                          if (value &&
                              newSelectionCount(
                                        {...selected, key: row}.values,
                                      ) +
                                      c.visible.length >
                                  500) {
                            message =
                                'This batch is full. Choose fewer photos.';
                          } else {
                            value
                                ? selected[key] = retainAdmission(row)
                                : selected.remove(key);
                          }
                        }),
                ),
                if (!supported)
                  Padding(
                    padding: EdgeInsetsDirectional.only(
                      start: ui.space.targetMin,
                    ),
                    child: Text(
                      detail,
                      style: ui.type.bodySmall.copyWith(
                        color: ui.color.inkSecondary,
                      ),
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
              ],
            ),
          ),
          if (!supported && row['retry_url'] is String && row['error'] is Map)
            UiButton(
              label: (row['error'] as Map)['action'] == 'connect'
                  ? 'Reconnect'
                  : 'Retry',
              semanticsLabel: 'Retry $name',
              variant: UiButtonVariant.ghost,
              onPressed: busy ? null : () => retryLink(row),
            ),
          if (supported && row['source'] is Map)
            UiIconButton(
              icon: UiIcons.show,
              semanticsLabel: 'Preview $name',
              onPressed: busy ? null : () => preview(row),
            ),
        ],
      ),
    );
  }
}
