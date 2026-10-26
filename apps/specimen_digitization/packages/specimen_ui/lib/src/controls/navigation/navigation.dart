/// The navigation family (10 section 4.4): the pill navigation, the bottom
/// tab bar, the rail, the sidebar, the top bar and the page scaffold.
///
/// One destination model, four ways to show it, one bar across the top and
/// one frame that holds them. Between them they retire `NavigationBar`,
/// `CupertinoTabBar`, `NavigationRail`, `Drawer`, `AppBar` and `Scaffold`.
///
/// `nav_disc.dart` and `nav_group.dart` are not exported. They are the disc
/// the pill and the rail share and the roving focus every one of the three
/// needs, and nothing outside this family has a use for either.
library;

export 'navigation_menu.dart';

export 'breadcrumbs.dart';
export 'steps.dart';
export 'collapsing_header.dart';
export 'nav_destination.dart';
export 'pill_nav.dart';
export 'rail.dart';
export 'scaffold.dart';
export 'sidebar.dart';
export 'side_panel.dart';
export 'sticky_bar.dart';
export 'tab_bar.dart';
export 'top_bar.dart';
export 'workspace_header.dart';
export 'view_tabs.dart';
