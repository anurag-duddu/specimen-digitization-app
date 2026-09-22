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

## The pilot's scope and the bootstrap

The owner decided on 2026-09-22 to create the whole tree in the first data
release rather than one flat collection, so that nothing is re-parented
later. The approved four-insert bootstrap
([`../execution/FIRST_COLLECTION_BOOTSTRAP.md`](../execution/FIRST_COLLECTION_BOOTSTRAP.md))
stays as it is, and an additive hierarchy mode inserts one organization,
the reviewed tree in parent-first order and the administrator's two
memberships in one transaction, verifying every row exactly as the
four-insert mode does. The runtime pins the collection name `Insects` for
pilot runs (`application/production.py`, `pin_dependencies`), so the
pilot's scope is the `Insects` collection beneath `Zoology`.

The tree the release creates is reviewed in the repository at
`infra/reference/fieldmuseum-collection-tree.json`: four departments as
root collections (Zoology, Botany, Anthropology, Geology) and the
sub-collections beneath them (Insects, Mammals, Birds, Fishes, Amphibians
and Reptiles and Invertebrate Zoology under Zoology; Seed Plants,
Bryophytes, Lichens, Pteridophytes and Fungi under Botany; Fossil
Invertebrates, Fossil Vertebrates and Paleobotany under Geology). Keys and
names are public; the collection identifiers are minted privately once by
`scripts/data/prepare_hierarchy_request.py` and live only in the private
request and artifact. The artifact binds the exact digest of the tree file
at the release's source commit, so the tree cannot drift between review
and application.

Adding a collection later (a Botany sub-collection, meteorites, a new
department) is a reviewed insert through the protected data plane, with
its parent already in place. Memberships for managers at the sub-collection
level are rows on those collections, added the same way. Neither needs a
runtime API, by design.

The organization name is the owner's: the proposal is `Field Museum`.

## Open decisions

- The exact organization name string (proposal: `Field Museum`).
- Which Botany sub-collections come first, and who their managers are.
- Whether a person with a main-collection membership should be able to act
  in every sub-collection beneath it. Today that needs a row per
  sub-collection; inherited access would be a product change with a
  security review.
