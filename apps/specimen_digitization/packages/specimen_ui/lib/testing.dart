/// Helpers a test needs, kept out of the main barrel.
///
/// Nothing here is part of the product's runtime surface, and nothing here
/// imports `flutter_test`, so importing this library from an application test
/// does not put `flutter_test` in the application's dependency graph.
library;

export 'src/testing/glass_budget.dart';
