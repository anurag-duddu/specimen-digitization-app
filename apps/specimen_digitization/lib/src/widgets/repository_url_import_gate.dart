/// The capability gate for importing from a repository URL.
///
/// This is intentionally presentation-only. It accepts neither a URL nor a
/// callback, so showing the future capability cannot become an arbitrary
/// client-side fetch. Intake can replace this widget only when a secure
/// server-side repository resolver exists behind an explicit application
/// contract.
library;

import 'package:flutter/widgets.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../models.dart';
import '../sources.dart';

/// An honest placeholder for repository URL import.
///
/// The gate has no interactive affordance. In particular, it does not render
/// an editable field or expose a submit callback while the server capability
/// is absent.
class RepositoryUrlImportGate extends StatelessWidget {
  const RepositoryUrlImportGate({super.key});

  /// The capability being described.
  static const String title = 'Repository URL import';

  /// Its current availability.
  static const String status = 'Not available yet';

  /// The capability that must exist before intake can offer the import.
  static const String explanation =
      'A secure server-side repository resolver must be connected before '
      'this app can import from a URL.';

  /// The client-side security boundary, stated explicitly.
  static const String fetchBoundary =
      'This app does not fetch repository URLs from this device.';

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    return Semantics(
      container: true,
      child: Surface(
        hairline: true,
        padding: EdgeInsetsDirectional.all(ui.space.s4),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            Text(title, style: ui.type.label.copyWith(color: ui.color.ink)),
            SizedBox(height: ui.space.s1),
            Text(
              status,
              style: ui.type.body.copyWith(color: ui.color.inkSecondary),
            ),
            SizedBox(height: ui.space.s2),
            Text(
              explanation,
              style: ui.type.bodySmall.copyWith(color: ui.color.inkSecondary),
            ),
            SizedBox(height: ui.space.s1),
            Text(
              fetchBoundary,
              style: ui.type.bodySmall.copyWith(color: ui.color.inkSecondary),
            ),
          ],
        ),
      ),
    );
  }
}

/// Only registered storage URLs can be resolved by the current API. A Drive
/// link is recognized for a useful capability answer, never fetched here.
enum RepositoryLocationKind { registeredStorage, drive, unsupported }

RepositoryLocationKind repositoryLocationKind(String value) {
  final Uri? uri = Uri.tryParse(value.trim());
  if (uri == null ||
      uri.userInfo.isNotEmpty ||
      uri.hasQuery ||
      uri.hasFragment) {
    return RepositoryLocationKind.unsupported;
  }
  if (uri.scheme == 'gs' &&
      uri.host.isNotEmpty &&
      uri.pathSegments.where((s) => s.isNotEmpty).isNotEmpty) {
    return RepositoryLocationKind.registeredStorage;
  }
  if (uri.scheme == 'https' &&
      (uri.host == 'drive.google.com' || uri.host == 'www.drive.google.com') &&
      uri.pathSegments.length >= 3 &&
      uri.pathSegments[0] == 'drive' &&
      uri.pathSegments[1] == 'folders' &&
      uri.pathSegments[2].isNotEmpty) {
    return RepositoryLocationKind.drive;
  }
  return RepositoryLocationKind.unsupported;
}

/// Resolves a pasted storage location against the collection's registered
/// sources. No arbitrary URL or bucket is fetched from the device.
class RepositoryUrlIntake extends StatefulWidget {
  const RepositoryUrlIntake({
    super.key,
    required this.scope,
    required this.repository,
    required this.onBrowseSources,
    this.userId,
  });

  final CollectionScope scope;
  final SourceRepository? repository;
  final VoidCallback? onBrowseSources;

  /// Invalidates a checked location if the signed-in operator changes.
  final String? userId;

  @override
  State<RepositoryUrlIntake> createState() => _RepositoryUrlIntakeState();
}

class _RepositoryUrlIntakeState extends State<RepositoryUrlIntake> {
  final TextEditingController _url = TextEditingController();
  bool _checking = false;
  String? _message;
  RegisteredSource? _match;
  int _request = 0;

  @override
  void didUpdateWidget(covariant RepositoryUrlIntake oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.scope.key != widget.scope.key ||
        oldWidget.userId != widget.userId ||
        !identical(oldWidget.repository, widget.repository)) {
      _request++;
      _url.clear();
      _checking = false;
      _match = null;
      _message = null;
    }
  }

  @override
  void dispose() {
    _url.dispose();
    super.dispose();
  }

  Future<void> _resolve() async {
    final int request = ++_request;
    final String value = _url.text.trim();
    setState(() {
      _checking = false;
      _message = null;
      _match = null;
    });
    final RepositoryLocationKind kind = repositoryLocationKind(value);
    if (kind == RepositoryLocationKind.drive) {
      setState(
        () => _message = 'Google Drive is not connected for this collection.',
      );
      return;
    }
    if (kind != RepositoryLocationKind.registeredStorage) {
      setState(
        () => _message =
            'Enter a registered gs://bucket/prefix or a Google Drive folder link.',
      );
      return;
    }
    final SourceRepository? repository = widget.repository;
    if (repository == null) {
      setState(() => _message = 'Storage source browsing is unavailable here.');
      return;
    }
    setState(() => _checking = true);
    try {
      final Uri uri = Uri.parse(value);
      final String prefix = uri.path.startsWith('/')
          ? uri.path.substring(1)
          : uri.path;
      final List<RegisteredSource> sources = await repository.sources(
        widget.scope,
      );
      if (!mounted || request != _request) return;
      final RegisteredSource? match = sources
          .where(
            (source) =>
                source.bucket == uri.host &&
                (source.prefix == prefix ||
                    source.prefix == '$prefix/' ||
                    (source.prefix.endsWith('/') &&
                        source.prefix.substring(0, source.prefix.length - 1) ==
                            prefix)),
          )
          .firstOrNull;
      setState(() {
        _match = match;
        _message = match == null
            ? 'This folder is not registered for this collection. Ask an administrator to connect it.'
            : match.inventory == null
            ? 'Registered source found. No inventory snapshot yet.'
            : 'Registered source found. Latest inventory: ${match.inventory!.objectCount} items.';
      });
    } on ApiFailure catch (error) {
      if (mounted && request == _request) {
        setState(() => _message = error.message);
      }
    } catch (_) {
      if (mounted && request == _request) {
        setState(
          () => _message =
              'Could not check this folder. Try again when collection access is available.',
        );
      }
    } finally {
      if (mounted && request == _request) {
        setState(() => _checking = false);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        Text('Check a folder before importing.', style: ui.type.body),
        SizedBox(height: ui.space.s2),
        UiField(
          key: const ValueKey<String>('intake-repository-url'),
          label: 'Folder location',
          controller: _url,
          hintText: 'gs://bucket/prefix or Drive folder link',
          autocorrect: false,
          onSubmitted: (_) => _resolve(),
          onChanged: (_) => setState(() {
            _request++;
            _checking = false;
            _message = null;
            _match = null;
          }),
        ),
        SizedBox(height: ui.space.s2),
        Align(
          alignment: AlignmentDirectional.centerStart,
          child: Wrap(
            spacing: ui.space.s2,
            runSpacing: ui.space.s2,
            children: <Widget>[
              UiButton(
                key: const ValueKey<String>('intake-check-location'),
                label: _checking ? 'Checking location' : 'Check location',
                variant: UiButtonVariant.secondary,
                onPressed: _checking ? null : _resolve,
              ),
              if (_match != null && widget.onBrowseSources != null)
                UiButton(
                  label: 'Review source',
                  variant: UiButtonVariant.secondary,
                  onPressed: widget.onBrowseSources,
                ),
            ],
          ),
        ),
        if (_message != null) ...<Widget>[
          SizedBox(height: ui.space.s2),
          Semantics(
            liveRegion: true,
            child: Text(_message!, style: ui.type.bodySmall),
          ),
        ],
      ],
    );
  }
}
