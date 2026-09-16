/// The navigation family (10 section 4.4): the pill navigation, the rail,
/// the sidebar, the top bar and the page scaffold.
///
/// One destination model, three ways to show it, one bar across the top and
/// one frame that holds them. Between them they retire `NavigationBar`,
/// `NavigationRail`, `Drawer`, `AppBar` and `Scaffold`.
///
/// `nav_disc.dart` and `nav_group.dart` are not exported. They are the disc
/// the pill and the rail share and the roving focus every one of the three
/// needs, and nothing outside this family has a use for either.
library;

export 'nav_destination.dart';
export 'pill_nav.dart';
export 'rail.dart';
export 'scaffold.dart';
export 'sidebar.dart';
export 'top_bar.dart';
