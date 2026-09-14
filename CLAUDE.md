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

- Material 3 with the app theme. Widgets read `Theme.of(context)` and the product
  `ThemeExtension`; no hard-coded `Color(0x...)`, font sizes or magic paddings.
- Layout decisions use window size (`LayoutBuilder` or `MediaQuery.sizeOf`), never
  platform or device type.
- Every interactive control has a semantic label, a 48 dp minimum target, and a
  visible focus state. Errors and status changes are announced once.
- All animation honors `MediaQuery.disableAnimationsOf(context)`.
- Prefer widget tests with `WidgetTester` for every new component and a golden or
  size-class test for every new screen layout.
