// The destinations every navigation test and the gallery page share.
//
// Real product destinations rather than invented ones, so a golden and a
// semantics assertion are about the words a reviewer actually reads
// (05 section 2; appendix A of the build plan).

import 'package:specimen_ui/specimen_ui.dart';

/// The two destinations the application ships with today.
const List<UiNavDestination> twoDestinations = <UiNavDestination>[
  UiNavDestination(label: 'Queue', icon: UiIcons.queue),
  UiNavDestination(label: 'Intake', icon: UiIcons.intake),
];

/// The three the shell grows to once sources has a screen.
const List<UiNavDestination> threeDestinations = <UiNavDestination>[
  UiNavDestination(label: 'Queue', icon: UiIcons.queue),
  UiNavDestination(label: 'Intake', icon: UiIcons.intake),
  UiNavDestination(label: 'Sources', icon: UiIcons.sources),
];

/// The most a pill may hold.
const List<UiNavDestination> fiveDestinations = <UiNavDestination>[
  UiNavDestination(label: 'Queue', icon: UiIcons.queue),
  UiNavDestination(label: 'Intake', icon: UiIcons.intake),
  UiNavDestination(label: 'Sources', icon: UiIcons.sources),
  UiNavDestination(label: 'Help', icon: UiIcons.help),
  UiNavDestination(label: 'Account', icon: UiIcons.account),
];
