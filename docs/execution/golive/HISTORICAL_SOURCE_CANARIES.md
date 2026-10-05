# Tier-one historical source qualification, 2026-10-05

These are public place-only endpoint/parser canaries, not a specimen run, model
result, production source effect, or live review acceptance. Root captured the
full HTTP response bytes, parameters, status, URL and SHA-256 for each exchange
under `specimen-golive/live-20261003/lane-p-notes/codex-takeover-20261004/
historical-source-canaries/`. The raw receipts remain under that custody path;
the hashes below pin exactly what was inspected. The runtime captures every
actual response afresh under its own durable source effect and refuses schema,
transport or partial-result errors as operational outcomes.

## tgn

Getty TGN's anonymous reconciliation and SPARQL endpoints answered a Manila
place-only query with three HTTP 200 exchanges and ten parsed records. The
receipt `Manila/tgn.json` has SHA-256
`8ecb3be9385209f878982c1b39a0af98f6b4e7bffe8a9e53841d26e9e960ff6c`.
An exact Yepocapa query returned `no_match` after one successful exchange;
the corresponding `tgn.json` has SHA-256
`0b8748975102c1abaefc51f31604a3eb4a6c0c262e77f253427e474bad198660`.
The Manila reconciliation hit the ten-record cap, so its result is ambiguous
and cannot claim exhaustive absence or choose a Manila without other context.
Getty identifies TGN as ODC-By 1.0 and documents these public data services:
https://www.getty.edu/research-conservation/tools-databases/vocabularies/data-services/.
Credit Getty Research Institute and the cited TGN record/release in use.

## wikidata

Wikidata's item search, entity detail and referenced-label APIs answered a
Yepocapa query in three HTTP 200 exchanges. The parsed answer includes a
municipality, a settlement and an unrelated dialect, so name-only coincidence
does not settle a place. `wikidata.json` has SHA-256
`a994442cd80b28a990c4bc3854514c412e4009a3e365ea8bef5191d72d2dbd49`.
Structured data is CC0: https://www.wikidata.org/wiki/Wikidata:Licensing.
The runtime sends an identifiable project User-Agent, consistent with
https://foundation.wikimedia.org/wiki/Policy:User-Agent_policy.

## nga

NGA GNS answered a Yepocapa name, feature-detail and administrative-unit
query in three HTTP 200 exchanges; two parsed records distinguish ADM2 from
PPLA2. `nga.json` has SHA-256
`49e4b583d9555c86fa5d5b58325b6c16a22911b323cd10105dc1e2a660829763`.
The public service and current GNS reference are documented at
https://geonames.nga.mil/gns/html/gns_services.html and
https://geonames.nga.mil/geonames/GNSHome/reference.html. Credit NGA GNS;
third-party coordinates have separate source responsibility. A parsed candidate
point remains evidence metadata, never a record coordinate value.

For all three sources, follow-up IDs come only from the preceding parsed
response. Every exchange is bounded at 2 MB and the chain at three GETs. A
transport error, stale/unknown durable effect, malformed response, incomplete
requested ID set, or ten-hit truncation never becomes a scientific `no_match`.
Historical candidates require qualified temporal/context interpretation and a
fresh GEOLocate validation before settlement or a computed review proposal.
