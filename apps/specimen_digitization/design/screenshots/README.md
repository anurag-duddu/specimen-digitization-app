# Screenshots of the current client

Captured 2026-09-13 from the synthetic demo (local API on port 8010, one cleared
fixture specimen). Android captures come from the `Medium_Phone_API_36` emulator;
the tablet and desktop captures come from the same emulator with its window
resized (`adb shell wm size`), which is a valid test because the app lays out by
window size. iOS captures were not possible on this machine: the iOS 26.5
platform component is not installed in Xcode. Web captures were not possible
because the synthetic API only allows the port 3000 origin and that port is held
by an older session.

| File | Window | What it shows |
|---|---|---|
| android-phone-01-signin.png | 411 x 914 dp | Synthetic sign-in. Tagline plus a 30-word caveat above the fields. |
| android-phone-02-signin-filled.png | phone | Fields filled; keyboard covers the primary button. |
| android-phone-03-queue.png | phone | Queue. App bar, banner, collection dropdown, title, tagline, search, six chips and a filter button occupy the full first screen; the first record starts at the bottom edge. |
| android-phone-04-workbench-top.png | phone | Workbench top. Permanent chrome uses 45 percent of the viewport. The region overlay label (a UUID on a black box) covers the label it marks. |
| android-phone-04-workbench-scroll1..5.png | phone | Record status card with a raw attempts dictionary, all four run actions shown for a finalized run, unbounded floats in the image check, tab chips two screens below the image. |
| android-phone-05-intake.png, -scroll.png | phone | Intake. Two paragraphs of 40 and 41 words before the first button. |
| android-phone-07-fields-tab.png, -scroll1..2.png | phone | Fields and evidence tab: classification and profile cards, then fields rendered as key: value lines and JSON disclosures. |
| android-phone-08-history-tab.png, -scroll.png | phone | History tab: audit events as ExpansionTiles with JSON bodies. |
| tablet-landscape-01-queue.png | 1180 x 820 dp | Rail plus queue. The collection dropdown spans the full width; one record card. |
| tablet-landscape-02-workbench.png | 1180 x 820 dp | Two-pane workbench. Image left, status right; the two decision buttons sit beside two occasional actions with equal weight. |
| tablet-landscape-03-workbench-scroll.png | 1180 x 820 dp | After one scroll the image pane is empty: the source image scrolls away with the page. |
| desktop-01-workbench.png | 1600 x 1000 dp | Same failure at desktop width. Processing card with four run actions; the tab selector is the last thing on the second screen. |
| (no desktop queue capture) | 1600 x 1000 dp | Pressing the system back control on the workbench exited the app to the launcher instead of returning to the queue (audit H3.1). |

These are evidence for [01-usability-heuristics-audit.md](../01-usability-heuristics-audit.md)
and [07-screen-blueprints.md](../07-screen-blueprints.md). They contain no museum data.
