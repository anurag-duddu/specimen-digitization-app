/// Composable content and navigation, using synthetic collection examples.
library;

import 'package:flutter/widgets.dart';
import '../../../specimen_ui.dart';
import '../gallery_shell.dart';

/// The content pattern family.
const contentPatternsPage = GalleryPage(
  id: 'content-patterns',
  title: 'Content and journeys',
  summary:
      'Breadcrumbs, progress steps, activity, messages and copyable source. Synthetic examples.',
  builder: buildContentPatternsPage,
  maxGlassPanes: 0,
);

/// Builds interactive content patterns.
Widget buildContentPatternsPage(BuildContext context) =>
    const _ContentPatterns();

class _ContentPatterns extends StatefulWidget {
  const _ContentPatterns();
  @override
  State<_ContentPatterns> createState() => _ContentPatternsState();
}

class _ContentPatternsState extends State<_ContentPatterns> {
  String _action = 'No example action yet';
  int _step = 1;
  UiMessageState _delivery = UiMessageState.failed;
  void _record(String value) => setState(() => _action = value);

  @override
  Widget build(BuildContext context) {
    final ui = context.ui;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        GallerySection(
          title: 'Breadcrumbs / hierarchy',
          child: UiBreadcrumbs(
            items: [
              UiBreadcrumb(
                label: 'Collections',
                onSelected: () => _record('Collections opened'),
              ),
              UiBreadcrumb(
                label: 'Entomology',
                onSelected: () => _record('Entomology opened'),
              ),
              const UiBreadcrumb(label: 'FMNH 118402'),
            ],
          ),
        ),
        GallerySection(
          title: 'Progress steps / controlled journey',
          child: UiSteps(
            steps: [
              for (var i = 0; i < 3; i++)
                UiStep(
                  label: [
                    'Choose source',
                    'Describe specimen',
                    'Review details',
                  ][i],
                  description: [
                    'Select photographs for this record.',
                    'Read the evidence and complete the fields.',
                    'Check the record before saving.',
                  ][i],
                  state: i < _step
                      ? UiStepState.complete
                      : i == _step
                      ? UiStepState.current
                      : UiStepState.upcoming,
                  onSelected: () => setState(() => _step = i),
                ),
            ],
          ),
        ),
        const GallerySection(
          title: 'Activity / a readable audit trail',
          child: UiActivityFeed(
            entries: [
              UiActivityEntry(
                title: 'Maya corrected the collection date',
                timeLabel: 'Today, 10:42 AM',
                actor: 'Maya Chen',
                description:
                    'Read the final digit from the original label photograph.',
              ),
              UiActivityEntry(
                title: 'Source photographs added',
                timeLabel: 'Today, 10:36 AM',
                actor: 'Alex Rivera',
                description:
                    'Three images, including the reverse of the label.',
              ),
            ],
          ),
        ),
        GallerySection(
          title: 'Messages / delivery and recovery',
          child: Column(
            children: [
              const UiMessage(
                author: 'Maya Chen',
                body:
                    'The reverse label includes the collection date. I added that photograph for review.',
                timeLabel: '10:42 AM',
              ),
              SizedBox(height: ui.space.s3),
              UiMessage(
                author: 'You',
                body: 'I will compare it with the original transcription.',
                timeLabel: '10:43 AM',
                outgoing: true,
                state: _delivery,
                onRetry: () => setState(() {
                  _delivery = UiMessageState.sent;
                  _action = 'Synthetic message sent';
                }),
              ),
            ],
          ),
        ),
        const GallerySection(
          title: 'Code snippets / literal source',
          child: UiCodeSnippet(
            label: 'Example occurrence JSON',
            code:
                '{\n  "catalogNumber": "FMNH 118402",\n  "basisOfRecord": "PreservedSpecimen"\n}',
          ),
        ),
        GallerySection(
          title: 'Inline call to action / composed from existing controls',
          child: Surface(
            radius: ui.shape.tile,
            hairline: true,
            padding: EdgeInsets.all(ui.space.s6),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'A clearer source makes a better record.',
                  style: ui.type.titleLarge,
                ),
                SizedBox(height: ui.space.s2),
                Text(
                  'Add another photograph when a detail is obscured.',
                  style: ui.type.body,
                ),
                SizedBox(height: ui.space.s4),
                UiButton(
                  label: 'Add photograph',
                  leading: UiIcons.add,
                  variant: UiButtonVariant.secondary,
                  onPressed: () =>
                      _record('Synthetic photograph chooser opened'),
                ),
              ],
            ),
          ),
        ),
        Semantics(
          liveRegion: true,
          child: Text(_action, style: ui.type.bodySmall),
        ),
      ],
    );
  }
}
