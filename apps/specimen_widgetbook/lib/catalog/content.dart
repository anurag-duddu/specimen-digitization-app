import 'package:flutter/widgets.dart';
import 'package:specimen_ui/specimen_ui.dart';
import 'package:widgetbook/widgetbook.dart';
import '../story.dart';

List<WidgetbookComponent> get contentComponents => [
  WidgetbookComponent(
    name: 'UiSelectionArea',
    useCases: [
      story(
        'Native evidence selection',
        'Select across paragraphs with a mouse, or long press on touch. Platform handles, magnifier and context menu come from the native Flutter selection infrastructure. Product copy commands remain available separately.',
        (_) => const UiSelectionArea(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text('Original label text'),
              Text(
                'Field Museum specimen, example catalogue record. The wording is preserved exactly as recorded.',
              ),
            ],
          ),
        ),
      ),
    ],
  ),
  WidgetbookComponent(
    name: 'UiSelectableText',
    useCases: [
      story(
        'Read-only text',
        'Use for a single selectable string without editable-field semantics. Native selection gestures adapt to the chosen platform.',
        (_) => const UiSelectableText('FMNH EXAMPLE-001 · Preserved specimen'),
      ),
    ],
  ),
  WidgetbookComponent(
    name: 'UiActivityFeed',
    useCases: [
      for (final divider in UiActivityDivider.values)
        for (final compact in [false, true])
          for (final supporting in ['None', 'File', 'Labels', 'Text'])
            story(
              '${divider.name} · ${compact ? 'compact' : 'regular'} · $supporting',
              'Notification and message events can carry attachments, labels or quoted text. Unread is named and actions are caller-owned.',
              (_) => ActionExample(
                builder: (_, report) => UiActivityFeed(
                  divider: divider,
                  compact: compact,
                  entries: [
                    UiActivityEntry(
                      title: 'Alex added collection evidence',
                      timeLabel: 'Today, 10:42',
                      actor: 'Alex Morgan',
                      unread: true,
                      supporting: supporting == 'None'
                          ? null
                          : supporting == 'File'
                          ? UiButton(
                              label: 'Original label.jpg · 2 MB',
                              variant: UiButtonVariant.secondary,
                              onPressed: () => report('Open attachment'),
                            )
                          : Text(
                              supporting == 'Labels'
                                  ? 'Botany · Original label · Verified'
                                  : '“Keep the original locality wording.”',
                            ),
                      actions: [
                        UiButton(
                          label: 'Review',
                          variant: UiButtonVariant.ghost,
                          onPressed: () => report('Review requested'),
                        ),
                      ],
                    ),
                    const UiActivityEntry(
                      title: 'Sam imported the record',
                      timeLabel: 'Today, 10:30',
                      actor: 'Sam Lee',
                    ),
                  ],
                ),
              ),
            ),
      story(
        'Chronological events',
        'The caller owns ordering and human-readable timestamps. Keep actors, actions and supporting detail textual. This feed is synthetic.',
        (_) => const UiActivityFeed(
          entries: [
            UiActivityEntry(
              title: 'Corrected catalogue number',
              timeLabel: 'Today, 10:42',
              actor: 'Alex Morgan',
              description: 'Confirmed against the original specimen label.',
            ),
            UiActivityEntry(
              title: 'Images uploaded',
              timeLabel: 'Today, 10:30',
              actor: 'Sam Lee',
            ),
          ],
        ),
      ),
      story(
        'Empty',
        'An empty feed explains that no event has occurred.',
        (_) => const UiActivityFeed(entries: []),
      ),
    ],
  ),
  WidgetbookComponent(
    name: 'UiMessage',
    useCases: [
      for (final outgoing in [false, true])
        for (final attachment in [false, true])
          for (final reactions in [false, true])
            story(
              '${outgoing ? 'Sent' : 'Received'} · ${attachment ? 'attachment' : 'text'} · ${reactions ? 'reactions' : 'plain'}',
              'Attachments retain real open actions and reactions are controlled by the host. This example stores reaction state locally.',
              (_) => _MessageDetails(
                outgoing: outgoing,
                attachment: attachment,
                reactions: reactions,
              ),
            ),
      story(
        'Writing',
        'Typing is a named status, never a fabricated delivered message.',
        (_) => const UiMessage(
          author: 'Alex Morgan',
          body: '',
          timeLabel: 'Now',
          writing: true,
        ),
      ),
      for (final outgoing in [false, true])
        for (final state in UiMessageState.values)
          story(
            '${outgoing ? 'Outgoing' : 'Incoming'} · ${state.name}',
            'Messages use selectable text and explicit delivery status. Retry belongs to the host. The example only updates a local action receipt.',
            (_) => ActionExample(
              builder: (_, report) => UiMessage(
                author: outgoing ? 'You' : 'Alex Morgan',
                body:
                    'The locality is visible in the second photograph. Please keep the original wording in the evidence field.',
                timeLabel: '10:42',
                outgoing: outgoing,
                state: state,
                onRetry: state == UiMessageState.failed
                    ? () => report('Retry requested')
                    : null,
              ),
            ),
          ),
    ],
  ),
  WidgetbookComponent(
    name: 'UiCodeSnippet',
    useCases: [
      for (final theme in UiCodeTheme.values)
        for (final tone in UiCodeTone.values)
          for (final numbers in [false, true])
            story(
              '${theme.name} · ${tone.name} · ${numbers ? 'line numbers' : 'plain'}',
              'Source text is copied verbatim; decorative line numbers never enter the clipboard. The explicit theme remains isolated to this panel.',
              (_) => UiCodeSnippet(
                label: 'Example occurrence JSON',
                code: '{\n  "catalogNumber": "EXAMPLE-001"\n}',
                theme: theme,
                tone: tone,
                lineNumbers: numbers,
              ),
            ),
      story(
        'System clipboard',
        'Literal, selectable source text. Copy reports completion and failure. Content is never evaluated. This story uses the device clipboard.',
        (_) => const UiCodeSnippet(
          label: 'Synthetic occurrence JSON',
          code:
              '{\n  "catalogNumber": "EXAMPLE-001",\n  "basisOfRecord": "PreservedSpecimen"\n}',
        ),
      ),
      story(
        'Clipboard failure',
        'Failure remains visible with a retry action; the document stays selectable for native copy.',
        (_) => UiCodeSnippet(
          label: 'Synthetic source',
          code: 'EXAMPLE-001',
          onCopy: (_) async =>
              throw StateError('Synthetic clipboard unavailable'),
        ),
      ),
    ],
  ),
  WidgetbookComponent(
    name: 'Inline call to action',
    useCases: [
      story(
        'Contextual next step',
        'Compose a neutral surface, heading, short supporting text and one named action. Reserve the hero gradient for brand moments.',
        (context) => ActionExample(
          builder: (_, report) => Surface(
            hairline: true,
            radius: context.ui.shape.tile,
            padding: EdgeInsets.all(context.ui.space.s4),
            child: UiSectionHeader(
              title: 'Complete the source evidence',
              supporting:
                  'Add the reverse label before reviewing this specimen.',
              actions: [
                UiButton(
                  label: 'Add source image',
                  onPressed: () => report('Source chooser requested'),
                ),
              ],
            ),
          ),
        ),
      ),
    ],
  ),
  WidgetbookComponent(
    name: 'Section footer',
    useCases: [
      story(
        'Supporting detail and actions',
        'Use a divider and a responsive button row. Keep record-level actions next to the content they affect.',
        (_) => ActionExample(
          builder: (_, report) => Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const UiHairline(),
              const Text('Your corrections remain a draft until saved.'),
              UiButtonRow(
                primary: UiButton(
                  label: 'Save draft',
                  onPressed: () => report('Saved draft'),
                ),
                secondary: UiButton(
                  label: 'Discard changes',
                  variant: UiButtonVariant.secondary,
                  onPressed: () => report('Discarded synthetic changes'),
                ),
              ),
            ],
          ),
        ),
      ),
    ],
  ),
];

class _MessageDetails extends StatefulWidget {
  const _MessageDetails({
    required this.outgoing,
    required this.attachment,
    required this.reactions,
  });
  final bool outgoing, attachment, reactions;
  @override
  State<_MessageDetails> createState() => _MessageDetailsState();
}

class _MessageDetailsState extends State<_MessageDetails> {
  bool selected = false;
  String status = '';
  @override
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: [
      UiMessage(
        author: widget.outgoing ? 'You' : 'Alex Morgan',
        body: widget.attachment
            ? ''
            : 'Please compare the locality with the original label.',
        timeLabel: '10:42',
        outgoing: widget.outgoing,
        attachments: widget.attachment
            ? [
                UiMessageAttachment(
                  name: 'Original label.jpg',
                  detail: 'JPEG · 2 MB',
                  preview: const UiIcon(
                    UiIcons.sources,
                    size: UiIconSize.display,
                  ),
                  onOpen: () =>
                      setState(() => status = 'Opened attachment locally'),
                ),
              ]
            : [],
        reactions: widget.reactions
            ? [
                UiMessageReaction(
                  label: 'Helpful',
                  count: selected ? 2 : 1,
                  selected: selected,
                  onPressed: () => setState(() => selected = !selected),
                ),
                const UiMessageReaction(label: 'Acknowledged', count: 0),
              ]
            : [],
      ),
      if (status.isNotEmpty) Text(status),
    ],
  );
}
