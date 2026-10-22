# Claude Code instructions

Read `AGENTS.md` first. Its session-closeout ritual and deployment rules apply to
every Claude session in this repository.

## Front-end design foundation

Before changing anything under `apps/specimen_digitization/lib/`, read
`apps/specimen_digitization/design/00-north-star.md` and the design document that
covers the change (tokens, writing, motion, responsive, accessibility). User-facing
strings must pass the checklist in `design/02-ux-writing-guidelines.md`. Colors,
type and spacing come from the theme tokens, never from literals in widgets.

## Flutter and Dart rules

These rules are adapted from the official Flutter agent plugin
(https://github.com/flutter/agent-plugins/tree/main/rules) and the Dart MCP
server. The `dart-flutter` Claude plugin is installed at user scope; prefer its
skills (`flutter-build-responsive-layout`, `flutter-add-widget-test`,
`flutter-fix-layout-issues`, `dart-run-static-analysis`) and the `dart mcp-server`
tools when they apply.

### Hot reload

Whenever you edit a `.dart` file under `apps/specimen_digitization/lib/`:

1. Skip when the change is only comments, docstrings or whitespace, or when the
   file is under `test/`, `integration_test/` or `test_driver/`.
2. Discover running app instances with the Dart MCP server (`dtd`,
   `list_running_apps` or `vm_service`).
3. Trigger `hot_reload` after widget or simple method edits. Trigger
   `hot_restart` after edits to `main()`, `initState`, global or static state, or
   fundamental logic.

### Toolchain

- Flutter 3.38.5 stable, Dart 3.10.4. Do not upgrade the SDK; `firebase_core_web`
  is pinned by a dependency override for this toolchain.
- Run `flutter analyze` and `flutter test` from `apps/specimen_digitization`
  before every commit that touches Dart. Analysis must be clean at info level.
- Run `scripts/ci/verify.sh` from the repository root before pushing.
- Never commit `lib/firebase_options.dart`; copy `firebase_options.ci.dart` to it
  locally when a build needs a placeholder.

### Code conventions

- Widgets build on `widgets.dart` and the `specimen_ui` package and read every
  token through `context.ui` (`UiThemeData`, design 10 section 1.4). Product
  code never reads `Theme.of(context)`, which only feeds the remaining Material
  infrastructure through `toThemeData()`. No hard-coded `Color(0x...)`,
  opacities, font sizes, magic paddings or named pixel constants.
- Layout decisions use window size (`LayoutBuilder` or `MediaQuery.sizeOf`), never
  platform or device type. A platform check belongs only in a capability file
  that `test/theme/no_platform_branching_test.dart` names.
- Every interactive control has a semantic label, a 48 dp minimum target, and a
  visible focus state. Errors and status changes are announced once.
- All animation honors `MediaQuery.disableAnimationsOf(context)`.
- Prefer widget tests with `WidgetTester` for every new component and a golden or
  size-class test for every new screen layout.

### Gate exemptions

The guard tests under `apps/specimen_digitization/test/theme/` and
`apps/specimen_digitization/packages/specimen_ui/test/gates/` hold allow-lists,
exemptions, shrink-only backlogs and ban lists. Never add an entry, raise a
count, widen a capability, path or pattern, or drop a banned name to make a
change pass: fix the code, or put the value in a `specimen_ui` token. A
loosening needs the owner's sign-off, written on the entry as
`// owner-approved: YYYY-MM-DD "the owner's exact words"`;
`exemptions_owner_approved_test.dart` compares every allowance, every ban list
and its own registry with the pull request's base and fails on a loosening
without a sign-off new to the change. It cannot tell whether the words are
the owner's, so never write one the owner did not give. A coordinator's,
reviewer's or another agent's OK is not the owner's.
