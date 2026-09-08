import 'dart:async';
import 'package:flutter/material.dart';
import 'auth.dart';
import 'intake.dart';
import 'models.dart';
import 'workbench.dart';
import 'search_filters.dart';

class CollectionWorkspace extends StatefulWidget {
  const CollectionWorkspace({
    super.key,
    required this.repository,
    required this.session,
    this.mode = 'production',
  });
  final SpecimenRepository repository;
  final SessionAccess session;
  final String mode;
  @override
  State<CollectionWorkspace> createState() => _CollectionWorkspaceState();
}

class _CollectionWorkspaceState extends State<CollectionWorkspace> {
  List<CollectionScope> _scopes = [];
  CollectionScope? _scope;
  List<Specimen> _items = [];
  Specimen? _selected;
  String _query = '';
  Map<String, String> _filters = {};
  String? _nextCursor;
  final _seenCursors = <String>{};
  bool _loadingMore = false;
  String _filter = '';
  String? _error;
  bool _loading = true;
  bool _mutating = false;
  int _page = 0;
  int _generation = 0;
  Timer? _poll;
  Timer? _search;
  final _searchController = TextEditingController();
  @override
  void initState() {
    super.initState();
    _initialize();
    _poll = Timer.periodic(const Duration(seconds: 20), (_) {
      if (!_mutating &&
          !_loading &&
          _scope != null &&
          _page == 0 &&
          _selected == null &&
          _seenCursors.isEmpty &&
          !_loadingMore) {
        _refresh(quiet: true);
      }
    });
  }

  @override
  void dispose() {
    _poll?.cancel();
    _search?.cancel();
    _searchController.dispose();
    super.dispose();
  }

  Future<void> _initialize() async {
    try {
      final scopes = await widget.repository.scopes();
      if (!mounted) return;
      setState(() {
        _scopes = scopes;
        _scope = scopes.firstOrNull;
        _loading = false;
      });
      if (_scope != null) await _refresh();
    } catch (e) {
      if (mounted) {
        setState(() {
          _error = _message(e);
          _loading = false;
        });
      }
    }
  }

  String _message(Object error) => error is ApiFailure
      ? error.message
      : 'The service could not be reached. Check your connection and retry.';
  Future<void> _refresh({bool quiet = false}) async {
    final scope = _scope;
    if (scope == null) return;
    final generation = ++_generation;
    _nextCursor = null;
    _seenCursors.clear();
    _loadingMore = false;
    if (!quiet) {
      setState(() {
        _loading = true;
        _error = null;
      });
    }
    try {
      final page = await widget.repository.specimenPage(
        scope,
        filters: _activeFilters,
      );
      final items = page.items;
      final selected = _selected == null
          ? null
          : await widget.repository.specimen(scope, _selected!.id);
      if (mounted && generation == _generation) {
        setState(() {
          _items = items;
          _nextCursor = page.nextCursor;
          _selected = selected;
          _loading = false;
          _error = null;
        });
      }
    } catch (e) {
      if (mounted && generation == _generation) {
        setState(() {
          _error = _message(e);
          _loading = false;
        });
      }
    }
  }

  Map<String, String> get _activeFilters => {
    ..._filters,
    if (_query.trim().isNotEmpty) 'specimen_id': _query.trim(),
    if (_filter.isNotEmpty)
      (['cleared', 'needs_human_review', 'deferred'].contains(_filter)
              ? 'disposition'
              : 'state'):
          _filter,
  };
  Future<void> _loadMore() async {
    final scope = _scope;
    final cursor = _nextCursor;
    if (scope == null || cursor == null || _loadingMore || _loading) return;
    final generation = _generation;
    setState(() {
      _loadingMore = true;
      _error = null;
    });
    try {
      final page = await widget.repository.specimenPage(
        scope,
        filters: _activeFilters,
        cursor: cursor,
      );
      if (!mounted || generation != _generation) return;
      if (_seenCursors.contains(cursor) ||
          page.nextCursor == cursor ||
          (page.nextCursor != null && _seenCursors.contains(page.nextCursor))) {
        throw const ApiFailure(
          'Page cursor repeated. Refresh the queue.',
          code: 'pagination',
        );
      }
      final ids = _items.map((s) => s.id).toSet();
      if (page.items.any((s) => !ids.add(s.id))) {
        throw const ApiFailure(
          'Records changed across pages. Refresh the queue.',
          code: 'pagination',
        );
      }
      setState(() {
        _items.addAll(page.items);
        _seenCursors.add(cursor);
        _nextCursor = page.nextCursor;
      });
    } catch (e) {
      if (mounted && generation == _generation) {
        setState(() {
          _error = '${_message(e)} Refresh the queue to restart this search.';
          _nextCursor = null;
        });
      }
    } finally {
      if (mounted && generation == _generation) {
        setState(() => _loadingMore = false);
      }
    }
  }

  Future<void> _open(Specimen s) async {
    final generation = ++_generation;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final item = await widget.repository.specimen(_scope!, s.id);
      if (mounted && generation == _generation) {
        setState(() {
          _selected = item;
          _loading = false;
        });
      }
    } catch (e) {
      if (mounted && generation == _generation) {
        setState(() {
          _error = _message(e);
          _loading = false;
        });
      }
    }
  }

  // Retain a mutation key for an uncertain response; identical retries reconcile on the server.
  final Map<String, String> _mutationKeys = {};
  Future<void> _mutate(Json? change, String? retryReason) async {
    if (_selected == null || _mutating) return;
    final current = _selected!;
    final payload =
        '${current.id}:${current.revision}:${change ?? retryReason}';
    final key = _mutationKeys.putIfAbsent(
      payload,
      () => 'review-${DateTime.now().microsecondsSinceEpoch}',
    );
    setState(() {
      _mutating = true;
      _error = null;
    });
    try {
      final result = change != null
          ? await widget.repository.review(_scope!, current, change, key)
          : await widget.repository.retry(_scope!, current, retryReason!, key);
      if (mounted) {
        setState(() {
          _selected = result;
          _mutationKeys.remove(payload);
        });
      }
    } catch (e) {
      if (mounted) {
        setState(
          () => _error = e is ApiFailure && e.conflict
              ? 'This record changed while you were reviewing. Your decision was not saved. Refresh evidence and compare the current version before trying again.'
              : _message(e),
        );
      }
    } finally {
      if (mounted) setState(() => _mutating = false);
    }
  }

  Color _color(String? disposition) => switch (disposition) {
    'cleared' => const Color(0xff14513d),
    'needs_human_review' => const Color(0xff754300),
    'deferred' => const Color(0xff594d7c),
    _ => const Color(0xff374b60),
  };
  Widget _queue() => ListView(
    padding: const EdgeInsets.all(24),
    children: [
      Text(
        'Collection queue',
        style: Theme.of(context).textTheme.headlineMedium,
      ),
      const SizedBox(height: 8),
      const Text(
        'Review the evidence. Resolve uncertainty. Keep every decision traceable.',
      ),
      const SizedBox(height: 24),
      TextField(
        controller: _searchController,
        decoration: const InputDecoration(
          labelText: 'Search specimens',
          hintText: 'Exact specimen ID; use Filters for other criteria',
          prefixIcon: Icon(Icons.search),
        ),
        onChanged: (q) {
          _query = q;
          ++_generation;
          setState(() {
            _nextCursor = null;
            _loadingMore = false;
          });
          _search?.cancel();
          _search = Timer(const Duration(milliseconds: 350), _refresh);
        },
      ),
      const SizedBox(height: 16),
      Wrap(
        spacing: 8,
        runSpacing: 8,
        children:
            {
                  '': 'All records',
                  'needs_human_review': 'Needs human review',
                  'cleared': 'Cleared',
                  'deferred': 'Deferred',
                  'processing_blocked': 'Processing blocked',
                  'running': 'Processing',
                }.entries
                .map(
                  (e) => FilterChip(
                    label: Text(e.value),
                    selected: _filter == e.key,
                    onSelected: (_) {
                      setState(() => _filter = e.key);
                      _refresh();
                    },
                  ),
                )
                .toList(),
      ),
      Align(
        alignment: Alignment.centerLeft,
        child: OutlinedButton.icon(
          icon: const Icon(Icons.filter_list),
          label: Text('Filters (${_filters.length})'),
          onPressed: () async {
            final values = await showDialog<Map<String, String>>(
              context: context,
              builder: (_) => SearchFilters(initial: _filters),
            );
            if (values != null && mounted) {
              setState(() => _filters = values);
              _refresh();
            }
          },
        ),
      ),
      const SizedBox(height: 20),
      Text(
        '${_items.length} matching records loaded',
        style: Theme.of(context).textTheme.labelLarge,
      ),
      const SizedBox(height: 8),
      if (!_loading && _items.isEmpty)
        Card(
          child: Padding(
            padding: const EdgeInsets.all(32),
            child: Column(
              children: [
                const Icon(Icons.inventory_2_outlined, size: 40),
                const SizedBox(height: 16),
                Text(
                  _filter.isEmpty && _query.isEmpty && _filters.isEmpty
                      ? 'Your collection starts with a photograph'
                      : 'No records match these filters',
                  style: Theme.of(context).textTheme.titleLarge,
                ),
                const SizedBox(height: 8),
                const Text(
                  'Upload photographs or adjust your search. Completed results and processing blocks appear here.',
                ),
                const SizedBox(height: 16),
                FilledButton(
                  onPressed: () => setState(() => _page = 1),
                  child: const Text('Add photographs'),
                ),
              ],
            ),
          ),
        ),
      ..._items.map(
        (s) => Card(
          child: ListTile(
            contentPadding: const EdgeInsets.symmetric(
              horizontal: 20,
              vertical: 12,
            ),
            leading: Icon(
              s.disposition == 'cleared'
                  ? Icons.verified_outlined
                  : Icons.description_outlined,
              color: _color(s.disposition),
            ),
            title: Text(
              s.title,
              style: Theme.of(context).textTheme.titleMedium,
            ),
            subtitle: Padding(
              padding: const EdgeInsets.only(top: 8),
              child: Text(
                '${s.status}\nProfile ${s.profile} · ${textOf(s.data['updated_at'], textOf(s.data['created_at']))}\nRisk: ${s.data['risk'] == null ? 'Unmeasured' : '${s.data['risk']} / 100'}${s.data['risk_calibrated'] == true ? '' : ' · Uncalibrated'}',
              ),
            ),
            trailing: const Icon(Icons.chevron_right),
            onTap: () => _open(s),
          ),
        ),
      ),
      if (_nextCursor != null)
        OutlinedButton(
          onPressed: _loadingMore || _loading ? null : _loadMore,
          child: Text(_loadingMore ? 'Loading more…' : 'Load more records'),
        ),
    ],
  );
  @override
  Widget build(BuildContext context) => LayoutBuilder(
    builder: (context, constraints) {
      final wide = constraints.maxWidth >= 800;
      final historyScope = _scope;
      final historySpecimen = _selected;
      final body = _scope == null
          ? SingleChildScrollView(
              child: Padding(
                padding: const EdgeInsets.all(24),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    const Icon(Icons.lock_outline, size: 40),
                    const SizedBox(height: 16),
                    const Text(
                      'No collection access is available. Ask your administrator to grant a collection role.',
                    ),
                    TextButton(
                      onPressed: _loading ? null : _initialize,
                      child: const Text('Check access again'),
                    ),
                  ],
                ),
              ),
            )
          : _page == 1
          ? IntakeScreen(
              key: ValueKey(_scope!.key),
              repository: widget.repository,
              scope: _scope!,
              userId: widget.session.userId,
              onComplete: () => _refresh(quiet: true),
            )
          : _selected == null
          ? _queue()
          : Column(
              children: [
                Align(
                  alignment: Alignment.centerLeft,
                  child: TextButton.icon(
                    onPressed: () => setState(() => _selected = null),
                    icon: const Icon(Icons.arrow_back),
                    label: const Text('Back to queue'),
                  ),
                ),
                Expanded(
                  child: ReviewWorkbench(
                    key: ValueKey('${_scope!.key}:${_selected!.id}'),
                    specimen: _selected!,
                    loadArtifact: (artifact) => widget.repository.artifact(
                      historyScope!,
                      historySpecimen!,
                      artifact,
                    ),
                    loadHistoryPage: (after, through) =>
                        widget.repository.historyPage(
                          historyScope!,
                          historySpecimen!.id,
                          afterRevision: after,
                          throughRevision: through,
                        ),
                    loadHistoricalRevision: (revision, runId, runSha256) =>
                        widget.repository.historicalSpecimen(
                          historyScope!,
                          historySpecimen!.id,
                          revision,
                          runId: runId,
                          runSha256: runSha256,
                        ),
                    collections: _scopes,
                    canReview: _scope!.permissions.any(
                      (p) => ['reviewer', 'manager', 'admin'].contains(p),
                    ),
                    canOperate: _scope!.permissions.any(
                      (p) => [
                        'operator',
                        'reviewer',
                        'manager',
                        'admin',
                      ].contains(p),
                    ),
                    busy:
                        _mutating ||
                        (_selected!.disposition != null &&
                            ![
                              'cleared',
                              'needs_human_review',
                              'deferred',
                            ].contains(_selected!.disposition)),
                    onChange: (c) => _mutate(c, null),
                    onRetry: (r) => _mutate(null, r),
                    onRefresh: _refresh,
                  ),
                ),
              ],
            );
      return Scaffold(
        appBar: AppBar(
          title: const Text('Specimen Digitization'),
          actions: [
            IconButton(
              onPressed: _loading ? null : _refresh,
              tooltip: 'Refresh collection',
              icon: const Icon(Icons.refresh),
            ),
            IconButton(
              onPressed: () async {
                try {
                  await widget.session.signOut();
                } catch (_) {
                  if (mounted) {
                    setState(() => _error = 'Sign-out failed. Try again.');
                  }
                }
              },
              tooltip: 'Sign out',
              icon: const Icon(Icons.logout),
            ),
          ],
        ),
        bottomNavigationBar: wide
            ? null
            : NavigationBar(
                selectedIndex: _page,
                onDestinationSelected: (p) => setState(() => _page = p),
                destinations: const [
                  NavigationDestination(
                    icon: Icon(Icons.inventory_2_outlined),
                    label: 'Queue',
                  ),
                  NavigationDestination(
                    icon: Icon(Icons.add_photo_alternate_outlined),
                    label: 'Intake',
                  ),
                ],
              ),
        body: Column(
          children: [
            if (widget.repository.mode != 'production')
              Container(
                width: double.infinity,
                color: const Color(0xffffe7a3),
                padding: const EdgeInsets.all(12),
                child: Text(
                  '${widget.repository.mode.toUpperCase()} ENVIRONMENT — fixture results are not real model processing or museum-approved records.',
                  style: const TextStyle(color: Color(0xff483500)),
                ),
              ),
            if (widget.repository.blockers.isNotEmpty)
              Padding(
                padding: const EdgeInsets.all(12),
                child: Text(
                  'Runtime blocked: ${widget.repository.blockers.map((b) => labelOf(b.toString())).join('; ')}. Contact the collection administrator.',
                ),
              ),
            if (_scopes.isNotEmpty)
              Padding(
                padding: const EdgeInsets.symmetric(
                  horizontal: 24,
                  vertical: 8,
                ),
                child: Row(
                  children: [
                    Expanded(
                      child: DropdownButtonFormField<String>(
                        initialValue: _scope?.key,
                        isExpanded: true,
                        decoration: const InputDecoration(
                          labelText: 'Authorized collection',
                        ),
                        items: _scopes
                            .map(
                              (s) => DropdownMenuItem(
                                value: s.key,
                                child: Text(s.name),
                              ),
                            )
                            .toList(),
                        onChanged: _mutating
                            ? null
                            : (key) {
                                setState(() {
                                  _scope = _scopes.firstWhere(
                                    (s) => s.key == key,
                                  );
                                  _selected = null;
                                  _items = [];
                                });
                                _refresh();
                              },
                      ),
                    ),
                    if (wide)
                      Padding(
                        padding: const EdgeInsets.only(left: 24),
                        child: Text(widget.session.displayName),
                      ),
                  ],
                ),
              ),
            if (_error != null)
              MaterialBanner(
                content: Semantics(liveRegion: true, child: Text(_error!)),
                leading: const Icon(Icons.info_outline),
                actions: [
                  TextButton(
                    onPressed: _scope == null ? _initialize : _refresh,
                    child: const Text('Retry / refresh'),
                  ),
                ],
              ),
            if (_loading || _mutating)
              const LinearProgressIndicator(
                semanticsLabel: 'Loading collection data',
              ),
            Expanded(
              child: Row(
                children: [
                  if (wide)
                    NavigationRail(
                      selectedIndex: _page,
                      labelType: NavigationRailLabelType.all,
                      onDestinationSelected: (p) => setState(() => _page = p),
                      destinations: const [
                        NavigationRailDestination(
                          icon: Icon(Icons.inventory_2_outlined),
                          label: Text('Queue'),
                        ),
                        NavigationRailDestination(
                          icon: Icon(Icons.add_photo_alternate_outlined),
                          label: Text('Intake'),
                        ),
                      ],
                    ),
                  Expanded(child: body),
                ],
              ),
            ),
          ],
        ),
      );
    },
  );
}
