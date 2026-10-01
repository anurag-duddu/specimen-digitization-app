# app_links 7.0.0 local privacy and mobile registration patch

Source: https://pub.dev/api/archives/app_links-7.0.0.tar.gz
Upstream: https://github.com/llfbandit/app_links
Archive SHA256: `3462d9defc61565fde4944858b59bec5be2b9d5b05f20aed190adb3ad08a7abc`.
License: Apache-2.0; the complete upstream LICENSE is retained unchanged. The archive has no NOTICE file. All 25 regular files outside example/ are included with original relative paths and line endings. Example application files are omitted; implementation and package metadata are retained. UPSTREAM_FILES.json records original/local hashes and exact modified-file identities.

Local changes on 2026-09-30:

- AppLinksPlugin.java: remove raw Intent logging, its Log import and unused TAG constant.
- AppLinksHelper.java: remove the logging-only raw action/URL block, its Log import and unused TAG constant.
- pubspec.yaml: remove `resolution: workspace` for standalone consumption; remove the `app_links_linux` and `app_links_web` dependency edges and Linux, macOS, web, and Windows plugin declarations. Retain version 7.0.0, the SDK/Flutter floors, `app_links_platform_interface: ^2.0.2`, and the Android/iOS plugin declarations. All 25 vendored upstream files remain, including unregistered desktop files.

The three modified files carry local-change notices. Other upstream files are byte-identical, including license and Dart stream behavior. Android/iOS native routing/filtering and Dart stream behavior are unchanged. Desktop/web app_links registration is intentionally excluded from this local package metadata; the existing application browser adapter remains separate. No global package cache was patched. Future upgrades must recheck logging throughout the entire package. Do not replace this package with the hosted version without reviewing this privacy patch.

At the initial source-preparation checkpoint (9536c9b8ab6373ad637f52de2f04e6cd6ec19270), the factory was prepared but startup did not call it. Dependency resolution, lockfile update, analysis, tests and native builds had not run. The repository's pinned Flutter3.38.5/Dart3.10.4 meet declared package floors only; that is not a resolved or native-build compatibility result. Hosted transitive implementations/platform interface were unchanged and unresolved at that checkpoint. Native cached initial/latest links remain in memory; acknowledging a BufferedEmailLinkSource delivery does not erase those plugin caches.

Adding the path dependency means a later Flutter build can generate platform plugin registration even while the factory is uncalled. No native runtime is activated during this source-only preparation. Browser URL handling remains the existing separate conditional implementation; future web/native generated registration must be included in qualification.

Mobile-only metadata update, 2026-09-30:

- A separate dependency-setup clone subsequently resolved the original metadata to app_links_platform_interface 2.0.2, app_links_linux 1.0.3, app_links_web 1.0.4, and gtk 2.2.0. Its resolved lockfile (SHA256 `4cd5ae218321f236c787442768e48d123b3df9efd32f60f33b54eb9483c29787`) and generated package graph are preserved as historical setup evidence, not copied into this source checkpoint.
- This checkpoint applies the mobile-only metadata changes above. It has not been resolved. Its tracked lockfile remains the pre-setup baseline (SHA256 `d3985fbdc33b53b6154cab7ea618128a45185a2989357372aaa47c640e7541b4`); it is not a resolved compatibility result for this fork.
- Flutter discovers reachable plugins using the saved package graph and each plugin's own declarations. Removing parent platform declarations alone does not prevent reachable endorsed implementations from registering. Removing the two dependency edges is also required, followed by fresh dependency resolution and inspection of actual generated plugin lists and web, Dart, and native registrants. No such refresh or generated-registration validation has run for this fork.
- Startup still does not call the factory. Android/iOS implementation, logging removal, license, application source, browser adapter, and native application configuration are unchanged. Analysis, tests, native builds, and device behavior remain unverified for this checkpoint. Native cached initial/latest links remain in memory after application acknowledgement.
