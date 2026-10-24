/// Who may open the costs, asked in one place.
///
/// The account menu decides whether to offer the entry, the route decides
/// whether to draw the screen and the screen decides whether to ask the
/// server. All three ask this, so they cannot disagree about it.
library;

import '../../costs.dart';
import '../../workspace.dart';

/// The organization whose costs [controller]'s account may open, or null.
///
/// Null until the server has confirmed the account's collections, and for any
/// account that is not an administrator of a collection in the open
/// collection's organization. A reviewer never reaches a request that the
/// server would refuse.
String? costOrganizationFor(WorkspaceController controller) =>
    controller.scopesVerified
    ? costOrganizationOf(controller.scopes, controller.scope)
    : null;

/// The cost surface of [controller]'s repository, when the account may use it.
///
/// Null where the account is not an administrator and where the build has no
/// cost support at all. The entry is hidden in both, never disabled.
({CostRepository repository, String organizationId})? costAccessFor(
  WorkspaceController controller,
) {
  final String? organization = costOrganizationFor(controller);
  final CostRepository? repository = costsIn(controller.repository);
  if (organization == null || repository == null) return null;
  return (repository: repository, organizationId: organization);
}
