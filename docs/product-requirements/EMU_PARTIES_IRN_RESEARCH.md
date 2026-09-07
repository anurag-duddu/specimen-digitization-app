# Field Museum EMu Parties and IRN availability check

| Research field | Value |
|---|---|
| Status | Current technical finding; collection-manager and Field IT confirmation still required |
| Checked | 2026-09-07 |
| Scope | Public Field Museum collection surfaces, public Field Museum technical documentation, and official Axiell EMu documentation |

## Finding

**Confirmed:** Field Museum uses EMu `eparties` records for people and organizations, and current Field documentation maps an occurrence's identified-by name through an `eparties` reference. The evidence supports interpreting **Identified by IRN** as the Internal Record Number of the identifier's Parties record, not the specimen's catalogue IRN.

**Not confirmed:** there is no verified anonymous public endpoint or user interface that resolves an arbitrary person name to a Field Museum Parties IRN. The public collection search exposes catalogue/specimen IRNs and display-name strings, but the current published field map does not expose identified-by or collector Parties IRNs.

**Implementation decision:** model an EMu identity as `(source system or connection, tenant/environment, module, irn)`, require a confirmed `eparties` match for `Identified by IRN` before an Insects record can be Cleared, and request a read-only authority lookup from Field Museum IT. A missing or ambiguous match must remain unresolved and route to review. An unavailable or unauthorized authority service is an operational block. Neither case may produce a guessed value.

## Evidence and status

| Status | Evidence | Product implication |
|---|---|---|
| Confirmed | [Axiell documentation](https://help.emu.axiell.com/v6.5/en/Topics/Common/How%20to%20add,%20edit%20and%20save%20records.htm) defines IRN as the automatically assigned Internal Record Number for an EMu record, and its [unique-field documentation](https://help.emu.axiell.com/latest/en-US/Topics/Common/Unique-valued%20fields.htm) scopes uniqueness to a module. | Do not treat an IRN as a globally unique person identifier. Qualify it with its source system or connection, tenant/environment, and module. |
| Confirmed | Field Museum's [current Parties-module documentation](https://github.com/fieldmuseum/EMu-Documentation/wiki/eparties-module), edited 2026-08-19, says `eparties` represents individuals, groups, and organizations and shows real records with IRNs. | `eparties` is the relevant Field Museum person/organization authority. |
| Confirmed | Field Museum's active Darwin Core mapping resolves `identifiedBy` through `IdeIdentifiedByRef_nesttab` to `eparties.NamFullName` and `recordedBy` through collection-event participant references to `eparties.NamFullName`. See the [identified-by mapping](https://github.com/fieldmuseum/EMu-Documentation/blob/master/Standards/estandards/Darwin%20Core/DwC_Occurrence_TermDefRecords.xml#L1970-L2024) and [recorded-by mapping](https://github.com/fieldmuseum/EMu-Documentation/blob/master/Standards/estandards/Darwin%20Core/DwC_Occurrence_TermDefRecords.xml#L1855-L1883). | Identifier display names, and recorded-by names derived from collection-event participants, are backed by Parties relationships. The requirement to resolve every Insects collector remains unconfirmed. |
| Strong technical evidence | Field Museum's [2024 sample REST schema](https://github.com/fieldmuseum/dams-netx/blob/main/data/sample_emurestapi_json/fmnh_schema_2024_ecatalogue.json) constrains both `ColCollectorRef_tab` and nested `IdeIdentifiedByRef` values to `emu:/fmnh/eparties/...` URIs. Its older [schema workbook](https://github.com/fieldmuseum/EMu-Documentation/blob/master/Schemas/fmnh_schema.xls) also maps collector, identifier, and taxonomy-author reference fields to `eparties`. | Use Parties resolution for collectors and identifiers. Taxonomy-author resolution is supported by historical schema evidence but still needs confirmation against production. |
| Confirmed public capability | The live anonymous [Field Museum collections JSON route](https://www.fieldmuseum.org/api/collections-search?catalog=Insects&page=1&size=1) returned HTTP 200 and, for an Insects result, catalogue `irn`, catalogue number, collector display text, taxonomy reference, and taxonomy data. A [public specimen page](https://www.fieldmuseum.org/collection-item/d809ff49-5dc8-48f5-a3b2-194b59c97845) displays its **Catalog IRN**. | This route may corroborate public specimen data, but its contract is not documented as a stable external API and its IRN is the catalogue IRN. |
| Confirmed public limitation | Field Museum's [public-search field map](https://github.com/fieldmuseum/EMu-Documentation/wiki/admin-WEBSITE-COLLECTIONS-SEARCH-HELP), current as of February 2026, exposes `IRN` from catalogue `irn` and `Collector` from the flattened `DarCollector` field. It lists no Parties index, identified-by reference, collector Parties IRN, or identifier Parties IRN. | Do not use a public catalogue IRN as `Identified by IRN`. Do not infer a Parties IRN from a display name. |
| Confirmed public limitation | A [public insect result with collector and identifier names](https://db.fieldmuseum.org/search-results/keywords/FMNHINS+0004+227+184/dept/zoology/start/0) displays catalogue IRN `4227184`, but no IRN for either person. | The public catalogue can supply name observations, not authoritative person identifiers. |
| Confirmed public limitation | The public [Field Museum Insects IPT resource](https://fmipt.fieldmuseum.org/ipt/resource?r=fmnh_insects) exports `recordedBy`, `identifiedBy`, and `dateIdentified`, but its current Darwin Core archive does not map `recordedByID`, `identifiedByID`, or a Parties IRN. | The public biodiversity archive cannot currently resolve a person name to an `eparties` IRN. |
| Confirmed access pattern | Field Museum's [official REST examples](https://github.com/fieldmuseum/emurestapi-examples) search `eparties`, but first obtain a JWT with an EMu username and password. Axiell REST calls likewise use bearer authorization. | A direct EMu Parties adapter requires a museum-provisioned read-only account and permission set. |
| Confirmed provisionable option | Field Museum documents an EMu-to-MongoDB-to-Elasticsearch web pipeline and says IT can provide [read-only Elasticsearch token access](https://github.com/fieldmuseum/EMu-Documentation/wiki/EMu-data-web) to third-party projects. | Ask whether the export contains an approved `eparties` index. If it does, prefer a least-privilege read-only token; if it does not, request a privacy-filtered authority export or direct EMu access. |
| Not confirmed | Public probes of `/eparties`, `/parties`, `/api/eparties`, and `/api/parties` did not produce a public Parties search. Adding an `eparties` module parameter to the public collections route still returned catalogue data. | Build no anonymous Parties dependency until Field Museum publishes or provisions one. |
| Not confirmed | The exact production columns, nested-row relationship, permitted Parties fields, and whether every taxonomy-author name must resolve to a Parties record have not been approved for this pilot. | Treat the current schema mapping as evidence for the design, not permission to write production EMu records. |

## Required Field Museum confirmation

Ask the collection manager and Field IT to confirm:

1. The current production columns for collector, identified-by, identification date, and taxonomy-author references.
2. Whether the public-data Elasticsearch export contains an `eparties` index or alias.
3. If it does, the endpoint, index/alias, read-only token, rate limits, permitted fields, and retention/caching policy.
4. If it does not, whether the pilot may receive a read-only EMu REST service account or a privacy-filtered Parties authority export.
5. The approved matching fields. The initial request should include `irn`, `NamPartyType`, `SummaryData`, `NamFullName`, `NamBriefName`, `NamTaxonomicName`, `NamCitedName`, permitted synonyms/other names, relevant dates and affiliations, and non-sensitive external identifiers such as ORCID.
6. Which attributes must never leave EMu. Private addresses, phone numbers, email addresses, and other contact data are out of scope unless explicitly approved.

## Proposed typed representation

```json
{
  "source_system": "field_museum_emu",
  "tenant": "fmnh",
  "environment": "production",
  "module": "eparties",
  "irn": 7124,
  "display_name": "example only",
  "resolution_status": "confirmed",
  "evidence": []
}
```

`source_system`, `tenant`, `environment`, `module`, and `irn` together form the identity. The display name is a versioned observation and must not be used as the key. During processing, `irn` may remain null with a typed `resolution_status` and `resolution_reason`; null does not satisfy the mandatory field's Cleared gate.
