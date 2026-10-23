/// The navigation family (10 sections 4.4 and 6).
///
/// The page the shell is judged on: if a disc stops reading as the current
/// destination, if a tab or a rail clips a word, or if the page frame stops
/// holding its chrome clear of the safe area, it shows here before it shows on
/// a screen.
library;

import 'dart:math' as math;

import 'package:flutter/widgets.dart';

import '../../../specimen_ui.dart';
import '../gallery_shell.dart';
import '../fit_columns.dart';

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
                child: SizedBox(
                  width: 316,
                  height: 300 * _specimenTextScale(context),
                  child: const _Sample(),
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
      GallerySection(
        title: 'Fit: a top bar with four commands, in narrow columns',
        child: Wrap(
          spacing: ui.space.s4,
          runSpacing: ui.space.s4,
          crossAxisAlignment: WrapCrossAlignment.start,
          children: <Widget>[
            for (final double width in fitColumns)
              GallerySpecimen(
                label: '${width.toInt()} dp',
                note: switch (width) {
                  >= 480 => 'every command on the bar',
                  >= 360 => 'two on the bar, two in the menu',
                  _ => 'every command in the menu',
                },
                child: _OverFields(
                  width: width,
                  height: 72,
                  padded: false,
                  child: const Align(
                    alignment: Alignment.topCenter,
                    child: UiTopBar(
                      leading: UiIcon(UiIcons.collection),
                      title: 'Queue and everything in it',
                      actions: _commands,
                    ),
                  ),
                ),
              ),
          ],
        ),
      ),
      GallerySection(
        title: 'UiTabBar',
        child: Wrap(
          spacing: ui.space.s4,
          runSpacing: ui.space.s4,
          children: const <Widget>[
            GallerySpecimen(
              label: 'two destinations',
              note: 'compact windows, every platform',
              child: _OverFields(
                width: 360,
                height: 96,
                padded: false,
                child: Align(
                  alignment: Alignment.bottomCenter,
                  child: _Tabs(destinations: _two, initial: 0),
                ),
              ),
            ),
            GallerySpecimen(
              label: 'three destinations, 34 dp inset',
              note: 'the ground runs under the home indicator',
              child: _OverFields(
                width: 360,
                height: 128,
                padded: false,
                child: Align(
                  alignment: Alignment.bottomCenter,
                  child: _Tabs(destinations: _three, initial: 1, inset: 34),
                ),
              ),
            ),
            GallerySpecimen(
              label: 'five destinations',
              note: 'the most a bar holds',
              child: _OverFields(
                width: 360,
                height: 96,
                padded: false,
                child: Align(
                  alignment: Alignment.bottomCenter,
                  child: _Tabs(destinations: _five, initial: 2),
                ),
              ),
            ),
            GallerySpecimen(
              label: 'five destinations in 200 dp',
              note: 'under 48 dp a cell the bar scrolls, on Help',
              child: _OverFields(
                width: 200,
                height: 96,
                padded: false,
                child: Align(
                  alignment: Alignment.bottomCenter,
                  child: _Tabs(destinations: _five, initial: 3),
                ),
              ),
            ),
            GallerySpecimen(
              label: 'two destinations, text at 200 percent',
              note: 'the bar grows, nothing is cut',
              child: _OverFields(
                width: 360,
                height: 112,
                padded: false,
                child: Align(
                  alignment: Alignment.bottomCenter,
                  child: _Tabs(destinations: _two, initial: 1, textScale: 2),
                ),
              ),
            ),
          ],
        ),
      ),
    ],
  );
}

/// The columns 11 section 3.3 measures a control's fit in.
///

/// Four commands, so the bar has two to keep and two to collapse.
const List<Widget> _commands = <Widget>[
  UiTopBarAction(
    icon: UiIcons.reload,
    label: 'Reload the queue',
    onPressed: _noop,
  ),
  UiTopBarAction(
    icon: UiIcons.filter,
    label: 'Filter records',
    onPressed: _noop,
  ),
  UiTopBarAction(
    icon: UiIcons.saveFilter,
    label: 'Save this filter',
    shortcut: 'Cmd S',
    onPressed: _noop,
  ),
  UiTopBarAction(icon: UiIcons.help, label: 'Open help', onPressed: _noop),
];

/// The gallery presses nothing. A null callback would render a control
/// disabled, which is a different specimen.
void _noop() {}

// The viewport belongs to the specimen, so it grows with the same text scale
// as its sidebar, header and actions. Fixed sample heights must not clip real
// components when the host asks to inspect accessibility sizes.
double _specimenTextScale(BuildContext context) {
  final double fontSize = context.ui.type.body.fontSize!;
  return math.max(
    1,
    MediaQuery.textScalerOf(context).scale(fontSize) / fontSize,
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
      height: height * _specimenTextScale(context),
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

class _Tabs extends StatefulWidget {
  const _Tabs({
    required this.destinations,
    required this.initial,
    this.inset = 0,
    this.textScale,
  });

  final List<UiNavDestination> destinations;
  final int initial;

  /// The system inset the bar is drawn over, as a phone's home indicator.
  final double inset;
  final double? textScale;

  @override
  State<_Tabs> createState() => _TabsState();
}

class _TabsState extends State<_Tabs> {
  late int _current = widget.initial;

  @override
  Widget build(BuildContext context) {
    final MediaQueryData media = MediaQuery.of(context);
    return MediaQuery(
      data: media.copyWith(
        viewPadding: EdgeInsets.only(bottom: widget.inset),
        textScaler: widget.textScale == null
            ? media.textScaler
            : TextScaler.linear(widget.textScale!),
      ),
      child: UiTabBar(
        destinations: widget.destinations,
        currentIndex: _current,
        onSelect: (int index) => setState(() => _current = index),
      ),
    );
  }
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
