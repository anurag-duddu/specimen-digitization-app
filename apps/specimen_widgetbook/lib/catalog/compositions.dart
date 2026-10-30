import 'dart:math' as math;

import 'package:flutter/widgets.dart';
import 'package:specimen_ui/specimen_ui.dart';
import 'package:widgetbook/widgetbook.dart';

import '../story.dart';

/// Working compositions for primitives that need a host, state or viewport.
List<WidgetbookComponent> get compositionComponents => [
  WidgetbookComponent(
    name: 'UiCollapsingHeader',
    useCases: [
      story(
        'Scroll-bound evidence header',
        'Scroll the example to collapse its source region. The header remains attached to the same scroll; reduced motion does not disable direct manipulation. The marked region is a synthetic placeholder, never specimen evidence.',
        (_) => const _ScrollExample(collapsing: true),
      ),
    ],
  ),
  WidgetbookComponent(
    name: 'UiStickyBar',
    useCases: [
      story(
        'Pinned section navigation',
        'Scroll until the tabs meet the top. Their ground becomes opaque while pinned. The extent follows the tab type scale; selecting a tab updates the visible section.',
        (_) => const _ScrollExample(collapsing: false),
      ),
    ],
  ),
  WidgetbookComponent(
    name: 'UiWorkspaceHeader',
    useCases: [
      story(
        'Collection and destinations',
        'The collection context remains visible above navigation on compact windows. Wide windows put the same context and measured tab strip in a row. Tabs share one controlled selection with the content below.',
        (_) => const _WorkspaceExample(),
      ),
    ],
  ),
  WidgetbookComponent(
    name: 'UiImportWorkspace',
    useCases: [
      story(
        'Source selection and private draft',
        'Choose a source from the wide rail or compact selector, then add a synthetic photo. The browser owns its scrolling content and persistent footer. Closing retains the local story draft; no files or services are accessed.',
        (_) => const _ImportExample(),
      ),
    ],
  ),
  WidgetbookComponent(
    name: 'UiModalActions',
    useCases: [
      story(
        'Primary secondary and tertiary actions',
        'One primary action names the result. Secondary cancels; a tertiary action has lower emphasis. The real modal action composition stacks when words cannot fit, including at 200% text.',
        (_) => ActionExample(
          builder: (_, report) => UiModalActions(
            primary: UiButton(
              label: 'Save changes',
              onPressed: () => report('Synthetic changes saved'),
            ),
            secondary: UiButton(
              label: 'Cancel',
              variant: UiButtonVariant.secondary,
              onPressed: () => report('Cancelled'),
            ),
            tertiary: [
              UiButton(
                label: 'View original',
                variant: UiButtonVariant.ghost,
                onPressed: () => report('Original requested'),
              ),
            ],
          ),
        ),
      ),
      story(
        'Dismiss only',
        'A read-only modal can have only a closing action. It does not manufacture a primary save action.',
        (_) => ActionExample(
          builder: (_, report) => UiModalActions(
            secondary: UiButton(
              label: 'Close details',
              variant: UiButtonVariant.secondary,
              onPressed: () => report('Details closed'),
            ),
          ),
        ),
      ),
    ],
  ),
  WidgetbookComponent(
    name: 'UiTabView',
    useCases: [
      story(
        'Manual activation and pane changes',
        'Arrow keys move tab focus; Enter or Space selects a pane. UiTabs and UiTabView share one notifier. The pane cross-fades and honours the global reduced-motion setting.',
        (_) => const _TabExample(),
      ),
      story(
        'Empty pane collection',
        'An empty collection renders no panel content. The host should provide an empty state when absence needs explanation.',
        (_) => const _TabExample(empty: true),
      ),
    ],
  ),
  for (final framed in [false, true])
    WidgetbookComponent(
      name: framed ? 'UiFieldFrame' : 'UiFieldBox',
      useCases: [
        story(
          framed
              ? 'Label editor validation and counter'
              : 'Custom editor shell',
          framed
              ? 'The frame owns the visible label, helper or error, and counter. The inner FieldCore owns editing and its accessible name; the same resolved style and states reach both frame and box. Enter an identifier or toggle the error and disabled knobs.'
              : 'This low-level shell supplies the field edge and focus treatment around a real native editor. Prefer UiField in product screens; compose the primitive only when a custom editor needs the same control contract.',
          (_) => _FieldExample(framed: framed),
        ),
      ],
    ),
];

const _tabs = [UiTab(label: 'Overview'), UiTab(label: 'Labels')];

/// A bounded component viewport inside the outer story's documentation scroll.
class _ExampleViewport extends StatelessWidget {
  const _ExampleViewport({required this.child});
  final Widget child;

  @override
  Widget build(BuildContext context) => LayoutBuilder(
    builder: (context, constraints) {
      final double height = math.max(
        context.ui.space.paneDetailMin,
        math.min(640, MediaQuery.sizeOf(context).height * 0.7),
      );
      return SizedBox(
        height: height,
        child: MediaQuery(
          data: MediaQuery.of(context).copyWith(
            size: Size(constraints.maxWidth, height),
            padding: EdgeInsets.zero,
            viewPadding: EdgeInsets.zero,
          ),
          child: Surface(hairline: true, child: child),
        ),
      );
    },
  );
}

class _ScrollExample extends StatefulWidget {
  const _ScrollExample({required this.collapsing});
  final bool collapsing;
  @override
  State<_ScrollExample> createState() => _ScrollExampleState();
}

class _ScrollExampleState extends State<_ScrollExample> {
  final _selected = ValueNotifier<int>(0);
  @override
  void dispose() {
    _selected.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => _ExampleViewport(
    child: Builder(
      builder: (context) {
        final ui = context.ui;
        final tabStyle = UiTabStyle.resolve(
          ui,
          textScaler: MediaQuery.textScalerOf(context),
        );
        final tabs = UiTabs(
          tabs: _tabs,
          selected: _selected,
          semanticsLabel: 'Example record sections',
        );
        return CustomScrollView(
          primary: false,
          slivers: [
            if (widget.collapsing)
              UiCollapsingHeader(
                primary: true,
                content: Surface(
                  role: SurfaceRole.matte,
                  child: Center(
                    child: Padding(
                      padding: EdgeInsets.all(ui.space.s4),
                      child: Text(
                        'Synthetic source region',
                        textAlign: TextAlign.center,
                        style: ui.type.title.copyWith(color: ui.color.ink),
                      ),
                    ),
                  ),
                ),
                chrome: [tabs],
              )
            else ...[
              SliverToBoxAdapter(
                child: Padding(
                  padding: EdgeInsets.all(ui.space.s4),
                  child: const UiSectionHeader(
                    title: 'Synthetic record',
                    supporting: 'Scroll to pin the section navigation.',
                  ),
                ),
              ),
              UiStickyBar(extent: tabStyle.outerHeight, child: tabs),
            ],
            SliverToBoxAdapter(
              child: ValueListenableBuilder<int>(
                valueListenable: _selected,
                builder: (context, selected, _) => Column(
                  children: [
                    for (var i = 1; i <= 12; i++)
                      UiListRow(
                        title: selected == 0
                            ? 'Synthetic record detail $i'
                            : 'Synthetic label annotation $i',
                        subtitle:
                            'Scroll content remains under the same header.',
                      ),
                  ],
                ),
              ),
            ),
          ],
        );
      },
    ),
  );
}

class _WorkspaceExample extends StatefulWidget {
  const _WorkspaceExample();
  @override
  State<_WorkspaceExample> createState() => _WorkspaceExampleState();
}

class _WorkspaceExampleState extends State<_WorkspaceExample> {
  final _selected = ValueNotifier<int>(0);
  String _receipt = 'Choose a destination or collection.';
  @override
  void dispose() {
    _selected.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final ui = context.ui;
    const tabs = [UiTab(label: 'Specimens'), UiTab(label: 'Intake')];
    final style = UiTabStyle.resolve(
      ui,
      textScaler: MediaQuery.textScalerOf(context),
    );
    Widget identity() => UiButton(
      label: 'Entomology',
      leading: UiIcons.collection,
      variant: UiButtonVariant.ghost,
      onPressed: () => setState(() => _receipt = 'Collection context opened'),
    );
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        UiWorkspaceHeader(
          identity: identity(),
          compactIdentity: identity(),
          navigationWidth: style.intrinsicWidth(context, tabs),
          navigation: UiTabs(
            tabs: tabs,
            selected: _selected,
            semanticsLabel: 'Example workspace destinations',
            onSelected: (index) =>
                setState(() => _receipt = '${tabs[index].label} selected'),
          ),
          actions: [
            UiIconButton(
              icon: UiIcons.help,
              semanticsLabel: 'Open workspace help',
              onPressed: () =>
                  setState(() => _receipt = 'Workspace help opened'),
            ),
          ],
        ),
        SizedBox(height: ui.space.s4),
        Semantics(liveRegion: true, child: Text(_receipt)),
      ],
    );
  }
}

class _ImportExample extends StatefulWidget {
  const _ImportExample();
  @override
  State<_ImportExample> createState() => _ImportExampleState();
}

class _ImportExampleState extends State<_ImportExample> {
  static const _sources = [
    UiImportSource('files', 'Local files', UiIcons.uploadFile),
    UiImportSource('collection', 'Registered source', UiIcons.collection),
  ];
  String _source = 'files';
  int _photos = 0;
  bool _open = true;

  @override
  Widget build(BuildContext context) {
    final ui = context.ui;
    if (!_open) {
      return Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Draft retained: $_photos synthetic photos.'),
          UiButton(
            label: 'Reopen source browser',
            onPressed: () => setState(() => _open = true),
          ),
        ],
      );
    }
    return _ExampleViewport(
      child: UiImportWorkspace(
        sources: _sources,
        source: _source,
        onSourceChanged: (value) => setState(() => _source = value),
        onClose: () => setState(() => _open = false),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Expanded(
              child: ListView(
                primary: false,
                padding: EdgeInsets.all(ui.space.s4),
                children: [
                  Text(
                    _source == 'files'
                        ? 'Synthetic local file browser'
                        : 'Synthetic registered source browser',
                    style: ui.type.title,
                  ),
                  SizedBox(height: ui.space.s3),
                  Semantics(
                    liveRegion: true,
                    child: Text('$_photos photos in this private story draft.'),
                  ),
                  for (var i = 1; i <= _photos; i++)
                    UiListRow(title: 'example-photo-$i.jpg'),
                ],
              ),
            ),
            Padding(
              padding: EdgeInsets.all(ui.space.s3),
              child: UiButton(
                label: 'Add sample photo',
                onPressed: () => setState(() => _photos++),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _TabExample extends StatefulWidget {
  const _TabExample({this.empty = false});
  final bool empty;
  @override
  State<_TabExample> createState() => _TabExampleState();
}

class _TabExampleState extends State<_TabExample> {
  final _selected = ValueNotifier<int>(0);
  @override
  void dispose() {
    _selected.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: [
      if (!widget.empty)
        UiTabs(
          tabs: _tabs,
          selected: _selected,
          semanticsLabel: 'Example details',
        ),
      SizedBox(height: context.ui.space.s4),
      UiTabView(
        selected: _selected,
        children: widget.empty
            ? []
            : const [
                UiEmptyState(
                  icon: UiIcons.record,
                  title: 'Synthetic specimen overview',
                  body: 'Select Labels to inspect the other panel.',
                ),
                UiEmptyState(
                  icon: UiIcons.record,
                  title: 'No transcribed labels',
                  body: 'This empty state explains what is absent.',
                ),
              ],
      ),
    ],
  );
}

class _FieldExample extends StatefulWidget {
  const _FieldExample({required this.framed});
  final bool framed;
  @override
  State<_FieldExample> createState() => _FieldExampleState();
}

class _FieldExampleState extends State<_FieldExample> {
  final _controller = TextEditingController(text: 'EXAMPLE-001');
  final _focus = FocusNode();
  @override
  void initState() {
    super.initState();
    _focus.addListener(_refresh);
  }

  void _refresh() => setState(() {});
  @override
  void dispose() {
    _focus.removeListener(_refresh);
    _focus.dispose();
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final error = context.knobs.boolean(label: 'Validation error');
    final disabled = context.knobs.boolean(label: 'Disabled');
    final states = <WidgetState>{
      if (error) WidgetState.error,
      if (disabled) WidgetState.disabled,
      if (_focus.hasFocus) WidgetState.focused,
    };
    final style = UiInputStyle.resolve(
      context.ui,
      UiFieldShape.box,
      textScaler: MediaQuery.textScalerOf(context),
    );
    final box = UiFieldBox(
      style: style,
      states: states,
      focusRing: _focus.hasFocus,
      leading: UiIcons.record,
      child: FieldCore(
        semanticsLabel: 'Example identifier',
        controller: _controller,
        focusNode: _focus,
        enabled: !disabled,
        style: style.text,
        onChanged: (_) => setState(() {}),
      ),
    );
    if (!widget.framed) return box;
    return UiFieldFrame(
      style: style,
      states: states,
      label: 'Example identifier',
      message: error
          ? 'This identifier is already present in the synthetic draft.'
          : disabled
          ? 'Editing is unavailable while this example is disabled.'
          : 'Use the identifier printed on the specimen label.',
      isError: error,
      counter: '${_controller.text.length} characters',
      child: box,
    );
  }
}
