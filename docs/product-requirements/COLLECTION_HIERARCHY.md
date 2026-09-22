# Collection hierarchy at the Field Museum, and how the product models it

Recorded 2026-09-22 from the project owner's description. This page fixes
the vocabulary for organizations, collections and sub-collections so the
bootstrap, the memberships and later phases use the same shape.

## The museum's structure

The Field Museum's main collections are Botany, Anthropology, Zoology and
Geology. Each main collection holds sub-collections: Zoology holds Insects,
Mammals and others; Botany holds Flowering plants, Bryophytes, Lichens and
others. A collection can hold many sub-collections. Collection managers
usually sit at the sub-collection level, though not as a hard rule; it
depends on size. The first phase of this product covers Insects and Botany.

## What the museum publishes

The same hierarchy is visible in the museum's public data, which comes from
EMu. Three EMu fields carry it, named in the public search field map:
`CatDepartment` (Department), `CatCatalog` (Catalog) and `CatCatalogSubset`
(Catalog Subset). The anonymous JSON route
`https://www.fieldmuseum.org/api/collections-search` filters by `dept` and
`catalog` and returns records and a total, but no facets, so the list below
was assembled on 2026-09-22 from the museum's IPT feed (18 published
datasets titled by department and collection), GBIF's registry (17
occurrence datasets) and samples of that route. It is the published shape,
not an exhaustive census; the machine-readable copy with sources is
[`fieldmuseum-collection-hierarchy.json`](fieldmuseum-collection-hierarchy.json).

| Department | Catalog | Subsets seen or published |
|---|---|---|
| Zoology | Insects (published as Insect, Arachnid and Myriapod Collection) | Coleoptera, Lepidoptera, Diptera, Hymenoptera: taxonomic orders, a field rather than a sub-collection |
| Zoology | Mammals | |
| Zoology | Birds (and a separate Bird Egg Collection) | Specimen |
| Zoology | Fishes | |
| Zoology | Amphibians and Reptiles | |
| Zoology | Invertebrate Zoology | Molluscan |
| Botany | Botany (the catalog equals the department) | Seed Plants, Bryophytes, Lichens, Pteridophytes, Fungi |
| Geology | Fossil Invertebrates | Main Catalogue |
| Geology | Fossil Vertebrates | |
| Geology | Paleobotany | |
| Anthropology | Anthropology (the catalog equals the department) | Anthropology |

Two things follow for the product. For Zoology the owner's
"sub-collection" is the EMu catalog (Insects), and the subset is a
taxonomic order that stays a field on the specimen. For Botany the catalog
is the department itself, so the owner's sub-collections (Seed Plants,
Bryophytes, Lichens, Pteridophytes, Fungi) are the EMu subsets, and each
becomes a child collection under Botany. The observation datasets published
under "Action" (bird and mammal sightings, rapid inventories) are not
specimen collections. Meteorites and mineralogy were not seen in the public
data sampled.

## How the schema represents it

- One `Organization` row is the museum
  (`dataconnect/schema/schema.gql`, `type Organization`).
- Every level below it is a `Collection` row keyed by organization and id,
  with an optional `parentId` that references another collection in the
  same organization (`type Collection`, `parent` reference). A main
  collection is a collection with no parent; a sub-collection is a
  collection whose parent is the main collection. Depth is not limited by
  the schema.
- Membership and roles are per collection (`type CollectionMember`, roles
  `operator`, `reviewer`, `manager`, `admin`, plus `canViewSensitive`), so a
  manager at the sub-collection level is a membership on that
  sub-collection, and a manager at the main-collection level is a
  membership on the parent. Nothing is inherited by the schema; each scope
  a person works in is an explicit row.
- Specimens, snapshots, runs, readings and decisions are all keyed by
  organization and collection id, so records belong to exactly one
  collection and moving a collection under a new parent moves nothing else.
- Collection profiles form their own tree
  (`src/specimen_digitization/application/collection_profiles.py`), so a
  sub-collection can inherit label semantics and policy from its parent
  profile independently of the membership tree.

## The pilot under the approved bootstrap

The approved first-scope bootstrap
([`../execution/FIRST_COLLECTION_BOOTSTRAP.md`](../execution/FIRST_COLLECTION_BOOTSTRAP.md))
creates exactly one organization, one root collection with no parent, and
the administrator's two memberships in one four-insert transaction, with a
reviewed fixed pair of ids and names. The runtime pins the collection name
`Insects` for pilot runs (`application/production.py`, `pin_dependencies`).
So the pilot's scope is the museum as the organization and `Insects` as a
root collection, with the department layer above it not yet present.

Proposed names, pending the owner's confirmation:

| Row | Proposed value |
|---|---|
| Organization | `Field Museum` |
| Root collection for the pilot | `Insects` |

## After the pilot

Two shapes reach the full hierarchy. Both go through the protected data
plane as reviewed changes; there is no runtime API that creates or moves
collections, by design.

1. Keep the pilot's `Insects` as it is, then insert `Zoology` as a new root
   collection and set `Insects`'s parent to it. Specimens, memberships and
   evidence do not move. Then insert `Botany` as a root and its
   sub-collections beneath it, each with its own managers.
2. Extend the bootstrap contract before the first data release so it
   inserts `Zoology` and `Insects` together. That is a change to
   `scripts/ci/bootstrap_release.py`, `scripts/data/bootstrap_admin.py`,
   their tests and the contract document, plus an independent review,
   ahead of a release that is otherwise ready.

The first shape is recommended: it keeps the approved contract unchanged
for the pilot and adds the hierarchy as data once the pilot has passed
human review.

## Open decisions

- The exact organization name string, and whether the pilot collection is
  named `Insects` or carries its department (for example `Zoology: Insects`).
- Which Botany sub-collections come first, and who their managers are.
- Whether a person with a main-collection membership should be able to act
  in every sub-collection beneath it. Today that needs a row per
  sub-collection; inherited access would be a product change with a
  security review.
