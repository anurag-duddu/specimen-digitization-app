import '../models.dart';

/// One visible collection in the chooser. Catalog membership is not access.
class CollectionChoice {
  const CollectionChoice({
    required this.name,
    required this.key,
    this.scope,
    this.groupLabel,
    this.depth = 0,
    this.headingOnly = false,
  });

  final String name;
  final String key;
  final CollectionScope? scope;
  final String? groupLabel;
  final int depth;
  final bool headingOnly;
}

/// Groups the server's catalog while enabling only explicitly granted scopes.
/// Legacy servers without a catalog continue to show their granted scopes.
List<CollectionChoice> collectionChoices(
  List<CollectionScope> scopes, {
  String? selectedKey,
}) {
  final choices = <CollectionChoice>[];
  final organizations = scopes.map((scope) => scope.organizationId).toSet();
  for (final organization in organizations) {
    final authorized = <String, CollectionScope>{
      for (final scope in scopes)
        if (scope.organizationId == organization) scope.collectionId: scope,
    };
    final catalog = <String, CollectionCatalogNode>{
      for (final scope in authorized.values)
        for (final node in scope.catalogNodes) node.collectionId: node,
    };
    final visited = <String>{};
    final selectedPath = <String>{};
    List<CollectionCatalogNode> childrenOf(String parent) =>
        catalog.values
            .where(
              (child) => child.parentCollectionId == parent && !child.testing,
            )
            .toList()
          ..sort((a, b) {
            if (selectedPath.contains(a.collectionId) !=
                selectedPath.contains(b.collectionId)) {
              return selectedPath.contains(a.collectionId) ? -1 : 1;
            }
            return a.name.compareTo(b.name);
          });
    void visit(CollectionCatalogNode node, int depth, String? group) {
      if (!visited.add(node.collectionId)) return;
      choices.add(
        CollectionChoice(
          name: node.name,
          key: '$organization/${node.collectionId}',
          scope: authorized[node.collectionId],
          groupLabel: group,
          depth: depth,
        ),
      );
      for (final child in childrenOf(node.collectionId)) {
        visit(child, depth + 1, null);
      }
    }

    final roots = catalog.values
        .where(
          (node) =>
              !node.testing &&
              (node.parentCollectionId == null ||
                  !catalog.containsKey(node.parentCollectionId)),
        )
        .toList();
    String? selectedRoot;
    final seen = <String>{};
    for (final node in catalog.values) {
      if ('$organization/${node.collectionId}' != selectedKey || node.testing) {
        continue;
      }
      var current = node;
      selectedPath.add(current.collectionId);
      while (current.parentCollectionId != null &&
          seen.add(current.collectionId) &&
          catalog.containsKey(current.parentCollectionId)) {
        current = catalog[current.parentCollectionId]!;
        selectedPath.add(current.collectionId);
      }
      selectedRoot = current.collectionId;
    }
    roots.sort((a, b) {
      if (a.collectionId == selectedRoot) return -1;
      if (b.collectionId == selectedRoot) return 1;
      return a.name.compareTo(b.name);
    });
    for (final root in roots) {
      final children = childrenOf(root.collectionId);
      if (children.isEmpty && !authorized.containsKey(root.collectionId)) {
        visited.add(root.collectionId);
        choices.add(
          CollectionChoice(
            name: root.name,
            key: '$organization/${root.collectionId}',
            headingOnly: true,
          ),
        );
      } else if (authorized.containsKey(root.collectionId)) {
        visit(root, 0, null);
      } else {
        visited.add(root.collectionId);
        for (var index = 0; index < children.length; index++) {
          visit(children[index], 0, index == 0 ? root.name : null);
        }
      }
    }
    var firstTesting = true;
    for (final node in catalog.values.where((node) => node.testing)) {
      visit(node, 0, firstTesting ? 'Testing' : null);
      firstTesting = false;
    }
    // A custom repository or older server can omit parent context. Keep the
    // granted scope reachable without inventing a relationship from its name.
    for (final scope in authorized.values) {
      if (visited.add(scope.collectionId)) {
        choices.add(
          CollectionChoice(name: scope.name, key: scope.key, scope: scope),
        );
      }
    }
  }
  return choices;
}
