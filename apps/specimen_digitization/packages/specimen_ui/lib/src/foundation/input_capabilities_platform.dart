/// Browser input capabilities, separate from the last-used input density.
library;

export 'input_capabilities_platform_stub.dart'
    if (dart.library.js_interop) 'input_capabilities_platform_web.dart';
