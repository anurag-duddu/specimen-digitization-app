import 'dart:async';
import 'dart:math' as math;
import 'dart:typed_data';

import 'package:flutter/widgets.dart';
import 'package:specimen_ui/specimen_ui.dart';

// Intake uses whole-image previews; the Queue keeps its small thumbnail.
class IntakePhoto extends StatefulWidget {
  const IntakePhoto({super.key, required this.bytes, required this.side});

  final Uint8List? bytes;
  final double side;

  static const String viewLabel = 'View photo';

  @override
  State<IntakePhoto> createState() => _IntakePhotoState();
}

class _IntakePhotoState extends State<IntakePhoto> {
  Uint8List? get bytes => widget.bytes;
  double get side => widget.side;
  final _providers = <ImageProvider<Object>>{};

  void _evictPreviews() {
    for (final provider in _providers) {
      unawaited(provider.evict());
    }
    _providers.clear();
  }

  @override
  void didUpdateWidget(covariant IntakePhoto oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (!identical(oldWidget.bytes, bytes)) _evictPreviews();
  }

  @override
  void dispose() {
    _evictPreviews();
    super.dispose();
  }

  Widget _image(BuildContext context, double width, {bool semantic = false}) {
    final ui = context.ui;
    final placeholder = Center(
      child: Text(
        'Preview unavailable',
        textAlign: TextAlign.center,
        style: ui.type.bodySmall.copyWith(color: ui.color.inkSecondary),
      ),
    );
    if (bytes == null) return placeholder;
    final provider = ResizeImage.resizeIfNeeded(
      math.max(1, (width * MediaQuery.devicePixelRatioOf(context)).ceil()),
      null,
      MemoryImage(bytes!),
    );
    _providers.add(provider);
    return Image(
      image: provider,
      fit: BoxFit.contain,
      gaplessPlayback: true,
      excludeFromSemantics: !semantic,
      semanticLabel: semantic ? 'Selected photograph' : null,
      errorBuilder: (_, _, _) =>
          const Center(child: Text('Preview unavailable')),
    );
  }

  void _view(BuildContext context) {
    UiDialog.showAdaptive<void>(
      context: context,
      title: 'Photo preview',
      dismissLabel: 'Close preview',
      body: (context) => AspectRatio(
        aspectRatio: 4 / 3,
        child: Surface(
          role: SurfaceRole.matte,
          radius: context.ui.shape.inner,
          child: LayoutBuilder(
            builder: (context, constraints) =>
                _image(context, constraints.maxWidth, semantic: true),
          ),
        ),
      ),
      primaryAction: (context) => UiButton(
        label: 'Close preview',
        autofocus: true,
        onPressed: () => Navigator.of(context).pop(),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final visual = SizedBox.square(
      dimension: side,
      child: Surface(
        role: SurfaceRole.matte,
        radius: context.ui.shape.inner,
        clip: true,
        child: ExcludeSemantics(child: _image(context, side)),
      ),
    );
    if (bytes == null) {
      return Semantics(
        label: 'Preview unavailable',
        excludeSemantics: true,
        child: visual,
      );
    }
    return UiTooltip(
      message: IntakePhoto.viewLabel,
      child: Pressable(
        semanticsLabel: IntakePhoto.viewLabel,
        onPressed: () => _view(context),
        radius: context.ui.shape.inner,
        builder: (context, states) => visual,
      ),
    );
  }
}
