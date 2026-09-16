/// The navigation family (10 sections 4.4 and 6).
///
/// The page the shell is judged on: if a disc stops reading as the current
/// destination, if a rail clips a word, or if the page frame stops holding its
/// chrome clear of the safe area, it shows here before it shows on a screen.
library;

import 'package:flutter/widgets.dart';

import '../../../specimen_ui.dart';
import '../gallery_shell.dart';

/// The two destinations the application ships with today.
const List<UiNavDestination> _two = <UiNavDestination>[
  UiNavDestination(label: 'Queue', icon: UiIcons.queue),
  UiNavDestination(label: 'Intake', icon: UiIcons.intake),
];

/// The three it grows to once sources has a screen of its own.
const List<UiNavDestination> _three = <UiNavDestination>[
  UiNavDestination(label: 'Queue', icon: UiIcons.queue),
  UiNavDestination(label: 'Intake', icon: UiIcons.intake),
  UiNavDestination(label: 'Sources', icon: UiIcons.sources),
];

/// The most a pill may hold.
const List<UiNavDestination> _five = <UiNavDestination>[
  UiNavDestination(label: 'Queue', icon: UiIcons.queue),
  UiNavDestination(label: 'Intake', icon: UiIcons.intake),
  UiNavDestination(label: 'Sources', icon: UiIcons.sources),
  UiNavDestination(label: 'Help', icon: UiIcons.help),
  UiNavDestination(label: 'Account', icon: UiIcons.account),
];

/// The navigation family's page, as the shell lists it.
///
/// Eight frosted panes rather than the four a product window is held to
/// (09 section 3.3): three pills, the sidebar, the top bar with its scrolled
/// fill, and the frame's own action bar and pill. A specimen sheet states its
/// own number out loud, and the frame's own test asserts that the frame alone
/// is three.
const GalleryPage navigationPage = GalleryPage(
  id: 'navigation',
  title: 'Navigation',
  summary: 'The pill, the rail, the sidebar, the top bar and the frame.',
  builder: buildNavigationPage,
  maxGlassPanes: 8,
);

/// Builds the navigation page.
Widget buildNavigationPage(BuildContext context) {
  final UiThemeData ui = context.ui;
  return Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: <Widget>[
      GallerySection(
        title: 'UiPillNav',
        child: Wrap(
          spacing: ui.space.s4,
          runSpacing: ui.space.s4,
          children: <Widget>[
            const GallerySpecimen(
              label: 'two destinations',
              child: _OverFields(
                width: 152,
                height: 104,
                child: _Pill(destinations: _two, initial: 0),
              ),
            ),
            const GallerySpecimen(
              label: 'three destinations',
              child: _OverFields(
                width: 200,
                height: 104,
                child: _Pill(destinations: _three, initial: 1),
              ),
            ),
            const GallerySpecimen(
              label: 'five destinations',
              note: 'the most a capsule holds',
              child: _OverFields(
                width: 296,
                height: 104,
                child: _Pill(destinations: _five, initial: 2),
              ),
            ),
          ],
        ),
      ),
      GallerySection(
        title: 'UiRail, UiSidebar and UiScaffold',
        child: Wrap(
          spacing: ui.space.s4,
          runSpacing: ui.space.s4,
          children: <Widget>[
            const GallerySpecimen(
              label: 'rail, collapsed',
              note: 'medium windows',
              child: _OverFields(
                width: 88,
                height: 300,
                child: _Rail(initial: 0),
              ),
            ),
            const GallerySpecimen(
              label: 'rail, extended',
              note: 'expanded windows',
              child: _OverFields(
                width: 104,
                height: 300,
                child: _Rail(initial: 1, extended: true),
              ),
            ),
            const GallerySpecimen(
              label: 'sidebar',
              note: 'large windows, 280 dp',
              child: _OverFields(
                width: 280,
                height: 300,
                padded: false,
                child: _Sidebar(),
              ),
            ),
            GallerySpecimen(
              label: 'scaffold',
              note: 'sky.home, a top bar, an action bar and a pill',
              child: Squircle.clip(
                radius: ui.shape.tile,
                child: const SizedBox(
                  width: 316,
                  height: 300,
                  child: _Sample(),
                ),
              ),
            ),
          ],
        ),
      ),
      GallerySection(
        title: 'UiTopBar',
        child: Wrap(
          spacing: ui.space.s4,
          runSpacing: ui.space.s4,
          children: const <Widget>[
            GallerySpecimen(
              label: 'at rest',
              note: 'transparent over the fields',
              child: _OverFields(
                width: 360,
                height: 92,
                padded: false,
                child: Align(
                  alignment: Alignment.topCenter,
                  child: _Bar(scrolledUnder: false),
                ),
              ),
            ),
            GallerySpecimen(
              label: 'scrolled under',
              note: 'glass.flat, no fade',
              child: _OverFields(
                width: 360,
                height: 92,
                padded: false,
                child: Align(
                  alignment: Alignment.topCenter,
                  child: _Bar(scrolledUnder: true),
                ),
              ),
            ),
          ],
        ),
      ),
    ],
  );
}

/// A specimen box with a sky behind it, so glass has something to blur.
class _OverFields extends StatelessWidget {
  const _OverFields({
    required this.width,
    required this.height,
    required this.child,
    this.padded = true,
  });

  final double width;
  final double height;
  final Widget child;
  final bool padded;

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    return SizedBox(
      width: width,
      height: height,
      child: Squircle.clip(
        radius: ui.shape.tile,
        child: Stack(
          fit: StackFit.expand,
          children: <Widget>[
            const FieldLayer(preset: SkyPreset.home),
            if (padded)
              Padding(
                padding: EdgeInsetsDirectional.all(ui.space.s4),
                child: Center(child: child),
              )
            else
              child,
          ],
        ),
      ),
    );
  }
}

class _Pill extends StatefulWidget {
  const _Pill({required this.destinations, required this.initial});

  final List<UiNavDestination> destinations;
  final int initial;

  @override
  State<_Pill> createState() => _PillState();
}

class _PillState extends State<_Pill> {
  late int _current = widget.initial;

  @override
  Widget build(BuildContext context) => UiPillNav(
    destinations: widget.destinations,
    currentIndex: _current,
    onSelect: (int index) => setState(() => _current = index),
  );
}

class _Rail extends StatefulWidget {
  const _Rail({required this.initial, this.extended = false});

  final int initial;
  final bool extended;

  @override
  State<_Rail> createState() => _RailState();
}

class _RailState extends State<_Rail> {
  late int _current = widget.initial;

  @override
  Widget build(BuildContext context) => Align(
    alignment: AlignmentDirectional.topCenter,
    child: UiRail(
      destinations: _three,
      currentIndex: _current,
      extended: widget.extended,
      onSelect: (int index) => setState(() => _current = index),
    ),
  );
}

class _Sidebar extends StatefulWidget {
  const _Sidebar();

  @override
  State<_Sidebar> createState() => _SidebarState();
}

class _SidebarState extends State<_Sidebar> {
  int _current = 0;

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    return UiSidebar(
      destinations: _three,
      currentIndex: _current,
      header: Text('Specimen Digitization', style: ui.type.titleLarge),
      footer: Text(
        'Signed in as a reviewer',
        style: ui.type.bodySmall.copyWith(color: ui.color.inkSecondary),
      ),
      onSelect: (int index) => setState(() => _current = index),
    );
  }
}

class _Bar extends StatelessWidget {
  const _Bar({required this.scrolledUnder});

  final bool scrolledUnder;

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    return UiTopBar(
      title: 'Queue',
      scrolledUnder: scrolledUnder,
      leading: UiIcon(UiIcons.back, color: ui.color.ink),
      actions: <Widget>[UiIcon(UiIcons.reload, color: ui.color.ink)],
    );
  }
}

/// A page frame at a fixed size, with every slot a page uses.
class _Sample extends StatefulWidget {
  const _Sample();

  @override
  State<_Sample> createState() => _SampleState();
}

class _SampleState extends State<_Sample> {
  int _current = 0;

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    return UiScaffold(
      topBar: UiTopBar(
        title: 'Queue',
        actions: <Widget>[UiIcon(UiIcons.reload, color: ui.color.ink)],
      ),
      actionBar: Text('Approve record', style: ui.type.label),
      nav: UiPillNav(
        destinations: _three,
        currentIndex: _current,
        onSelect: (int index) => setState(() => _current = index),
      ),
      body: Builder(
        builder: (BuildContext context) => ListView.builder(
          padding: EdgeInsetsDirectional.fromSTEB(
            ui.space.s4,
            ui.space.s4,
            ui.space.s4,
            UiScaffold.of(context).bottomInset,
          ),
          itemCount: 8,
          itemBuilder: (BuildContext context, int index) => Padding(
            padding: EdgeInsetsDirectional.only(bottom: ui.space.s2),
            child: Surface(
              radius: ui.shape.tile,
              padding: EdgeInsetsDirectional.all(ui.space.s3),
              child: Text('Specimen ${index + 1}', style: ui.type.title),
            ),
          ),
        ),
      ),
    );
  }
}
