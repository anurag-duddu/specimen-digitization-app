/// Window size classes, re-exported from the design system.
///
/// [WindowClass] and [Adaptive] moved into `specimen_ui`'s foundation
/// (`foundation/window.dart`) in wave F, unchanged: the same breakpoints, the
/// same `of`, `fromWidth`, `isAtLeast` and `isCompact`. They belong there
/// because the package's own scaffolds and patterns choose arrangements with
/// them and cannot import the application (11 section 3.1).
///
/// [WindowArrangement] joined them on 2026-10-17: the shell's own rule for
/// when the window is stacked and when it docks, which every surface that
/// draws chrome reads (05 section 2).
///
/// This file stays so that no call site in the application moved with them.
/// A screen may import either path; both names resolve to the one
/// declaration.
library;

export 'package:specimen_ui/specimen_ui.dart'
    show Adaptive, WindowArrangement, WindowClass;
