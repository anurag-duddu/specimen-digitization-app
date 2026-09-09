# Safe catalog failure diagnostics

A failed protected data command reports a fixed stage, for example
`Data release blocked [stage=node.connect; sqlstate=42501].`
The stage identifies the operation that failed, not proof that it completed.
An absent catalog artifact does not establish whether a connection was made.

| Stage family | Failure boundary |
|---|---|
| `data.admission`, `data.plan` | Exact source, review, cumulative reservation or plan admission |
| `google.admission` | Repeated admission immediately before credential consumption |
| `google.credentials-file` | Exact action credential path, ownership, permissions or private file parsing |
| `google.credentials-validation`, `google.credentials-load`, `google.session` | Bound keyless credential contract, SDK loading or authorized session construction |
| `google.project-request`, `google.project-identity` | Native project request or observed project identity |
| `catalog.metadata-request`, `catalog.metadata-identity` | Native SQL instance metadata request or pinned target configuration |
| `node.preflight`, `node.dependencies`, `node.connector`, `node.connect` | Native source/environment checks, dependencies, connector options or PostgreSQL connection |
| `node.context`, `node.sessions` | Connected database/actor assertion or client-session observation |
| `node.catalog-begin`, `node.catalog-query`, `node.catalog-validate`, `node.catalog-rollback` | Fixed read-only transaction, catalog query, qualification or rollback |
| `node.output`, `node.cleanup` | Private native evidence write or connection cleanup |
| `catalog.native-execute`, `catalog.native-result` | Parent subprocess timeout/malformed diagnostic or native result/provenance |
| `catalog.encryption`, `catalog.receipt`, `data.receipt` | Controlled encryption or sanitized receipt publication |

Only trusted stage constants, validated numeric HTTP error statuses and a fixed
relevant PostgreSQL SQLSTATE allowlist may appear. Exception messages, exception
class names, URLs, credentials, SQL, raw stdout/stderr and catalog values never
become a public fallback. A malformed or absent child diagnostic becomes the
fixed `catalog.native-execute` stage. A first native failure remains the named
failure if cleanup also rejects. These diagnostics add no retry, permission,
workload or reservation authority.

The pinned GitHub auth action's native file writer can emit mode `0640` under
umask `022`. The consumer now opens only its exact named action credential with
no symlink following, checks owner, regular-file type, single link and mode
`0600` or `0640`, and removes the group-read bit on that descriptor. It proves
mode `0600` before reading bounded bytes from the same descriptor. Explicit ADC
or gcloud credential paths must agree. Broader modes, foreign owners, links and
changed files fail closed. General `private_bytes` remains unchanged and never
accepts group-readable input. This compatibility correction does not establish
the unobserved file mode or cause of any historical live failure.

The successful six-file initializer fingerprint protocol, private catalog bytes,
encrypted envelope and sanitized public receipt remain unchanged. Existing
admission, credential, target, SQL, timeout, transaction and privacy checks remain
mandatory. A new protected attempt needs its own reviewed source and cumulative
reservation; diagnostics alone do not authorize a live retry.
