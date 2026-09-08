# Independent baseline fixture evidence

Candidate SHA: `a53f855e963b457c3ee2065f387609a193bb6f32`.
Fixture SHA-256: `7f194fdff2c2798ac3f1702acdcb187b9ad6b8dd23d2668bc2ea21f9e001ecd8`.
Started: 2026-09-08T17:43:41.679839+00:00; ended: 2026-09-08T17:43:42.157926+00:00.
Transport: ASGI TestClient / SQLite / LocalBlobs.
Mode: fixture. Cloud specimens used: 0. Paid calls: 0. Release accepted: false.

| Check | State | Actual |
|---|---|---|
| missing-bearer | passed | 401 |
| batch | passed | 200 |
| item | passed | 200 |
| partial-upload | passed | 200 |
| upload-app-recreation | passed | {"status": 200, "offset": 20} |
| upload-replay | passed | 200 |
| upload-resume | passed | 200 |
| complete | passed | 200 |
| workspace | passed | 200 |
| synthetic-observations | passed | {"count": 2, "mode": "synthetic"} |
| correction | passed | 200 |
| readings-retained | passed | {"count": 2} |
| decision-replay | passed | 200 |
| decision-conflict | passed | 409 |
| correction-app-recreation | passed | {"revision": 29} |
| original-hash | passed | HTTP 200; SHA-256 matches the fixture digest above |
| history-reopens | passed | 200 |
| viewer-positive-control | passed | 200 |
| viewer-write-denied | passed | 403 |
| cross-organization-denied | passed | 404 |
| cors-untrusted-origin | passed | 400 |
| membership-revoked-workspace | passed | 404 |
| membership-revoked-source | passed | 404 |
| membership-revoked-history | passed | 404 |

Limits:

- App recreation in same process, not worker process restart
- Injected identity, not Firebase or App Check validation
- No real emulator, cloud SQL/Storage, browser, or provider used
- One authored blank raster; text supplied by synthetic adapter

Private raw JSON SHA-256: `cc42466ab479e1498eabff8bec559b1d747e1c1669ca664e3e98afb9de5696db`.
All 24 case names, states and actual observations were compared against the
private raw JSON. The original-hash row references the identical digest above.
