# Releasing Specimen Digitization

This page is for the person who owns the project, not for a developer. It
explains what a release is here, what the one command asks you for, and how to
tell whether it worked. Terms that could be jargon are explained on the spot.

Nothing on this page deploys anything. The command described here only prepares
a sealed envelope of evidence. The release itself still runs on GitHub, under
the rules in [DEPLOYMENT.md](../DEPLOYMENT.md), which this page does not change.

## What a release is

A **release** is the moment a change you approved becomes the thing the museum
actually uses. In this project a release never happens because someone runs a
command on their laptop. It happens when GitHub — the service that stores the
code — runs an automated job after a change has been reviewed and merged.

"Merged" means the change was proposed, checked, and then folded into the single
official copy of the code, called **main**. Only code that is in `main` can be
released.

There is a deliberate reason for this. A release spends real money, touches real
museum records, and is hard to undo. So the project is built so that no single
person — and no agent — can deploy by deciding to. The evidence has to line up
first, and the automated gate checks it independently.

## The three planes

A "plane" is just one part of the system that gets released on its own. They are
released separately because they carry very different risks.

| Plane | What it is | What it can break |
|---|---|---|
| **Hosting** | The website people open in a browser | The page people see |
| **Data** | The database holding specimen records | The records themselves |
| **Runtime** | The servers that read the slides and run the models | Cost, and processing results |

Hosting is the gentlest and is fully automatic: merge a change to `main` and it
goes out. It needs nothing from this page.

Data and Runtime are the guarded ones. They will not run unless a valid,
in-date, source-bound envelope of evidence is already installed. Producing that
envelope is what this page is about.

Runtime is further split in two — `runtime-build` (make the server images) and
`runtime` (put them into service) — so that whoever can build cannot also
deploy. Data is likewise split into `data` and `data-initialization`. Each of
those four gets its own envelope.

## Why this used to be stuck

The guarded planes read one GitHub **secret** called `RELEASE_INPUTS_B64`. A
secret is a value stored in GitHub that the automated job can use but nobody can
read back afterwards.

That secret holds an envelope containing three things: the **packet** (the
claims about which commit is being released, by whose authority, and under what
spending limit), the **plan** (exactly what will be built or changed), and the
**evidence** (the approval record, the independent reviewer's report, and the
running cost ledger).

Every one of those has to agree with every other one, digit for digit. Until
now, that envelope was assembled by hand. When the temporary folders holding the
hand-assembled pieces were cleaned up by the operating system, there was no way
to make another one, and both guarded planes stopped dead.

`scripts/ci/mint_release_packet.py` replaces the hand assembly. It does not make
the gate easier to pass. It makes it possible to pass at all.

## What the command does for you, and what it asks

The command works out for itself everything that can be observed. You are never
asked for any of this:

- which commit is currently the tip of `main`, and its tree
- which merged pull request produced that commit
- which CI run built it, and whether all five required checks passed on that
  exact commit (a **check** is one automated test job; **CI** is the service
  that runs them)
- the current time, and the deadline two hours out at the latest
- the coordinator's identity and the cost reservations, both read out of the
  cost ledger you supply
- the pinned model revision

It asks you only for things that are genuinely private or genuinely a decision.
Each is asked once, with an explanation:

| What it asks for | What it is | Where it comes from |
|---|---|---|
| The **deployment plan** file | What will actually be built or changed, written against the live system as it stands | The coordinator writes it |
| The **authorization artifact** file | The private record of your approval for this release | Kept with the coordinator |
| The **independent review report** file | The report by the reviewer who is *not* the coordinator | The reviewer writes it |
| The **human review scope** file | The record of exactly what the human reviewers approved. Runtime only | Kept with the coordinator |
| The **shared budget ledger** file | The running total of every cost committed across every session and retry | The coordinator maintains it |
| The **cost review** file | The reviewed basis for each cost ceiling | The coordinator maintains it |
| The **reviewer's session id** | Who did the independent review | The reviewer's own session |
| The **project number** | The numeric id of the Google Cloud project | The live cloud project |
| The **identity pool id** | Which pool issues the job's short-lived credential | The live cloud project |
| The **pilot manifest digest** | 64 characters identifying the exact ten specimens | The frozen pilot manifest |

A **digest** (also written `sha256`) is a 64-character fingerprint of a file. If
one byte of the file changes, the fingerprint changes completely. That is how
the system proves two people are talking about the same file.

Note that you give it the **files**, not their fingerprints. It computes the
fingerprints itself, and puts the exact original bytes of those files into the
envelope. That removes any chance of typing a fingerprint wrongly.

### What it will never do

- It will never invent, default or guess an approval, a reviewer, or a cost
  figure. A missing answer stops the run with a message saying what is missing.
- It will never mint against a commit that is not the current tip of `main`. A
  stale packet is precisely what blocked both planes for days.
- It will never print the secret value. The secret goes into one file that only
  you can read, and the rest of the output is safe to share.
- It will never report success unless its own output has already passed the same
  validators the release job will run.

## Running it

You need `gh` (the GitHub command-line tool) signed in, and your copy of the
code up to date:

```bash
git fetch origin main
```

Then run the command for the plane you are releasing. Replace
`RELEASE_RUN_ID` with the id of the release run this envelope is for — the
envelope is locked to one specific run, so a retry needs a new envelope:

```bash
uv run python scripts/ci/mint_release_packet.py --plane runtime --release-run-id RELEASE_RUN_ID --secret-out ~/release-inputs.b64 --evidence-digests ~/release-evidence.json
```

It will ask its questions one at a time. If you would rather pass everything on
the command line and have it fail instead of asking, add `--no-prompt` and the
matching options (`--plan-path`, `--ledger-path`, and so on; run it with
`--help` to see them all).

The `--evidence-digests` file is a small JSON file holding the fingerprints of
release evidence the command cannot observe for itself — the published server
images, the model artifacts, the database schema, the approval records, and the
rollback point. Each is produced by another step of the release. If any is
missing, the command stops and names it rather than filling in a placeholder.

### About the deadline

Every envelope carries a deadline, and the release job refuses to start after it
passes. You do not normally set it: the command picks the right one for the
plane. Runtime gets two hours, the most the gate allows, because the approved
single processing run takes 3,500 seconds and has to finish inside the envelope's
life. The other planes get half an hour. If you override it with
`--window-seconds` and choose a Runtime value too short for that run, the command
refuses and explains why, rather than minting an envelope that could never be
activated.

### About the spending limit

Your approved ceiling is USD 12. That ceiling only applies if the cost ledger
you supply is version `release-cost-ledger/v3`. With any older ledger the packet
silently falls back to the earlier USD 5 limit, and the release is then rejected
for asking to spend more than it is allowed.

The command checks this for you and refuses with a full explanation rather than
letting it happen quietly. If you genuinely mean to release under the old USD 5
authority, pass `--accept-legacy-budget` to say so out loud.

It also reads the cost reservations straight out of the ledger. If the
coordinator has not yet reserved cost for this run, the command stops. Reserving
cost is a spending decision, and this tool does not make spending decisions.

## Installing the values

When it succeeds, the command prints exactly what to install and where. There
are six values for the Runtime plane and five for the others, and they belong to
the **environment** for that plane — not to the repository as a whole. An
**environment** is a named box in GitHub holding settings that only certain jobs
can see. Each plane has its own, so each plane gets its own envelope.

Go to:

> **GitHub → your repository → Settings → Environments → the environment for
> this plane → Environment secrets / Environment variables**

The environment names are `runtime-production`, `runtime-build-production`,
`data-production` and `data-initialization-production`.

Under **Environment secrets**, add one secret:

- `RELEASE_INPUTS_B64` — paste the contents of the file the command wrote

Under **Environment variables**, add five variables for the Runtime plane, or the
first four for any other plane. The command prints every value it produced; they
are fingerprints and commit ids, and none of them is a secret:

- `RELEASE_INPUTS_SHA256`
- `RELEASE_PACKET_SHA256`
- `RELEASE_BUDGET_LEDGER_SHA256`
- `RELEASE_AUTHORIZED_SHA`
- `RELEASE_HUMAN_REVIEW_AUTHORIZATION_SHA256` — Runtime only

The fifth one is new to this page because the Runtime job has always required it
and nothing used to produce it. It is the fingerprint of the human review scope
file — the record of exactly what the reviewers approved. When Runtime puts the
servers into service, it compares the deployment plan against this value and
stops if the two disagree, so a plan that quietly widened what the reviewers
agreed to cannot run. Without the variable installed, Runtime activation fails
closed every time, which is why the other four alone were never enough.

The command works the fingerprint out from the file you give it, and refuses if
the file is not one of the approved human review scopes recorded in
[APPROVED_RELEASE_BUDGET.md](APPROVED_RELEASE_BUDGET.md). It never invents or
defaults this value. The other three planes do not run human review, so they
neither ask for the file nor print the variable.

If you prefer the command line, the tool prints ready-to-run `gh secret set` and
`gh variable set` commands with the right environment already filled in. Using
those avoids opening the secret file at all.

Do not paste the secret into a chat, an issue, a commit message or a log. It is
the one value on this page that must stay private.

## How to tell whether it worked

**The command worked** if it printed "Minted one release input bundle", listed
the commit and the CI run, and wrote the secret file. It validates its own
output before printing anything, so if you see that line the envelope is
internally consistent and bound to the current `main`.

If it printed "Nothing was minted", nothing was written anywhere. The message
below it names the exact gate. The common ones:

| Message says | What it means | What to do |
|---|---|---|
| not at the current tip of main | Your copy of the code is behind | `git fetch origin main`, then mint again |
| the CI/CD run is still in_progress | The checks have not finished | Wait for them, then mint again |
| concluded 'failure' | A required check failed | Fix the cause. Never mint around a failed check |
| no reserved rows for … | Cost has not been reserved for this run | The coordinator reserves it first |
| not 'release-cost-ledger/v3' | The ledger cannot carry the USD 12 ceiling | Supply the approved v3 ledger |
| the public readiness candidate is not complete | Some release evidence has not been produced yet | Record the named digests and mint again |
| the human review scope artifact is required | Runtime was minted without the reviewers' scope file | Supply it with `--human-review-scope-path` |
| neither approved human-review scope | The file supplied is not one of the approved scopes | Supply the exact approved artifact, unchanged |
| too short to release the runtime plane | The chosen deadline cannot fit the approved processing run | Drop `--window-seconds` and take the default |

**The release worked** is a separate and later question, and a successful mint
is not evidence of it. A release is only complete when all of the following are
true, and `docs/DEPLOYMENT.md` is the authority on them:

1. the change was merged to `main` through a pull request;
2. the `main` workflow ran green, including its deploy job;
3. the public site reports that exact commit at `/deployment.json`;
4. the smoke test passed against the public URL.

If any of those is missing or unknown, the release is not complete. Report the
gate. Do not deploy by hand — a hand deployment is never a substitute here, and
the guarded planes reject one.

## Where this fits

- [DEPLOYMENT.md](../DEPLOYMENT.md) — the authoritative release contract
- [APPROVED_RELEASE_BUDGET.md](APPROVED_RELEASE_BUDGET.md) — the USD 12 amendment
- [RELEASE_AUTHORIZATION.md](RELEASE_AUTHORIZATION.md) — the bounded authority
- [RELEASE_INPUT_TRANSPORT.md](RELEASE_INPUT_TRANSPORT.md) — how the envelope travels
- `scripts/ci/release_admission.py` — the gate that judges the envelope
- `scripts/ci/mint_release_packet.py` — the command this page describes
