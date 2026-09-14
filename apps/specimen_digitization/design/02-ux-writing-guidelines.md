# UX writing guidelines: Specimen Digitization

Owner: content design. Applies to every user-facing string in `apps/specimen_digitization/lib/`.

**Notation used in this document.** In "current string" columns, `{EM}` marks a literal em-dash
character present in the source and `{EN}` marks a literal en-dash. Both characters are banned
(rule 4 in section 6), which is why the strings that contain them are listed for rewrite.

---

## 1. Research summary

Twelve principles, distilled from sources actually read for this document. Each is written as a
rule this codebase can be held to.

### 1.1 Put the load-bearing word first

Users scan in an F pattern and truncation eats the end of a string, not the beginning. Titles and
notification bodies should front-load the keyword, drop articles, and stay short enough not to
clip. NN/g measures page titles at 40 to 60 characters and Material specifies notification titles
under 29 characters.
Sources: <https://www.nngroup.com/articles/microcontent-how-to-write-headlines-page-titles-and-subject-lines/>,
<https://m3.material.io/foundations/content-design/notifications>

### 1.2 An error message is three facts, not a paragraph

What happened, why, and what to do next. NN/g's rubric scores messages on precise description,
constructive advice, low correction effort, and a nonjudgmental tone, and targets a seventh to
eighth grade reading level. Apple gives the canonical rewrite: "That password is too short" is
worse than "Choose a password with at least 8 characters," because only the second contains the fix.
Sources: <https://www.nngroup.com/articles/error-message-guidelines/>,
<https://www.nngroup.com/articles/error-messages-scoring-rubric/>,
<https://developer.apple.com/design/human-interface-guidelines/writing>

### 1.3 Severity picks the surface, not the wording

NN/g: design errors based on impact. Modal dialogs for errors that must stop work, banners and
toasts for everything else, and the message adjacent to its source. A blocked processing run and a
mistyped date must not arrive through the same widget.
Source: <https://www.nngroup.com/articles/error-message-guidelines/>

### 1.4 Never blame the user, and never use the word "invalid"

NN/g calls out "invalid" and "illegal" specifically as words that shift responsibility onto the
person. Apple adds that "Invalid name" is a robotic non-message and that "Use only letters for your
name" beats "Don't use numbers or symbols" because it states the rule positively.
Sources: <https://www.nngroup.com/articles/error-message-guidelines/>,
<https://developer.apple.com/design/human-interface-guidelines/writing>

### 1.5 A button label is a verb, two to four words, and never "OK"

NN/g: use just enough text to describe the command, lead with a strong verb, drop articles, add the
noun when a bare verb is ambiguous ("Delete folder", not "Delete"), and replace "OK" with the actual
action. Apple: "just saying 'Send' often works better than 'Let's do it!'"
Sources: <https://www.nngroup.com/articles/ui-copy/>,
<https://developer.apple.com/design/human-interface-guidelines/writing>

### 1.6 Sentence case for everything, and no terminal period in a title

Material requires sentence-style capitalization for all titles, headings, labels, menu items,
navigation, app bars and buttons. Microsoft states the same rule and adds that titles, headings and
UI titles take no period or colon at the end.
Sources: <https://m3.material.io/foundations/content-design/style-guide/ux-writing-best-practices>,
<https://learn.microsoft.com/en-us/style-guide/top-10-tips-style-voice>

### 1.7 Second person only, and no "we"

Material's word-choice guidance forbids mixing first and second person in the same context and
cautions against speaking as "we". Apple is blunter: avoid "we" altogether, because "We're having
trouble loading this content" is less clear than "Unable to load content." The exception both allow
is a first-person acknowledgement the user is actively making, which is exactly what an approval
reason is.
Sources: <https://m3.material.io/foundations/content-design/style-guide/word-choice>,
<https://developer.apple.com/design/human-interface-guidelines/writing>

### 1.8 State the consequence in neutral language, and say how to undo it

Material: "Tell users what will happen if they take an action and how they can undo it," and
"Avoid cautions or warnings that might sound alarming, intimidating, or condescending." This is the
governing rule for every confirmation dialog in the workbench, where the real consequence is
"a new run supersedes downstream results" and the real undo is "prior records stay in history."
Source: <https://m3.material.io/foundations/content-design/style-guide/ux-writing-best-practices>

### 1.9 Cut until only the decision remains

Microsoft: "Prune every excess word," give just enough information to decide confidently, and start
statements with a verb. GOV.UK sets hard numbers: split any sentence over 25 words, cap paragraphs
at 5 sentences, and prefer the short word ("buy" not "purchase", "help" not "assist"). NN/g adds the
technique: delete dependent clauses that add no information, and delete redundancy.
Sources: <https://learn.microsoft.com/en-us/style-guide/top-10-tips-style-voice>,
<https://guidance.publishing.service.gov.uk/writing-to-gov-uk-standards/writing-guidelines/clear-language/>,
<https://www.nngroup.com/articles/rewriting-content-brevity/>

### 1.10 Plain English is mandatory even for experts, and jargon gets defined on first use

GOV.UK makes plain English mandatory and permits specialist terms only when necessary, explained in
plain English at first use. It also flags nominalizations ending in "-ion" and "-ment" as the usual
culprits, which is precisely the register of "segmentation correction", "adjudication", and
"disposition". Shopify targets a seventh-grade reading level for product surfaces.
Sources: <https://guidance.publishing.service.gov.uk/writing-to-gov-uk-standards/writing-guidelines/clear-language/>,
<https://shopify.dev/docs/apps/design/content>

### 1.11 Voice is constant; tone moves with the situation

Apple: establish the voice once, then "vary your tone based on the situation," considering what the
person is physically doing. Shopify enumerates the situations and gives each a different posture:
everyday tasks get out of the way, simple errors explain and resolve, serious problems explain the
impact and apologize when you caused it. GOV.UK names the target register precisely: "brisk, not
terse", "incisive yet human", "serious without pomposity", and emotionless.
Sources: <https://developer.apple.com/design/human-interface-guidelines/writing>,
<https://shopify.dev/docs/apps/design/content/voice-and-tone>,
<https://guidance.publishing.service.gov.uk/writing-to-gov-uk-standards/writing-guidelines/right-tone/>

### 1.12 Say what you know, what you do not know, and how you know it

This is DACS principle 5 for archival description, with principle 6 requiring that archivists
"document and make discoverable the actions they take on records." It is the professional standard
this product's honesty caveats are trying to satisfy. The guidelines below do not remove the
honesty; they move it out of 44-word paragraphs and into a short label plus an expandable "Why".
Source: <https://saa-ts-dacs.github.io/dacs/04_statement_of_principles.html>

### 1.13 Keep the verbatim and the interpreted in separately named slots

Darwin Core, the standard this data will eventually be exported against, does not blend original and
processed values: `verbatimLocality` sits beside `locality`, `verbatimEventDate` beside `eventDate`,
`verbatimIdentification` beside `scientificName`, and the verbatim term is "meant to be used in
addition to, not instead of" the interpreted one. Doubt gets its own terms too:
`identificationQualifier` and `identificationVerificationStatus`. The UI layer names in section 3
map onto this, so the vocabulary a reviewer learns is the vocabulary the export uses.
Source: <https://dwc.tdwg.org/terms/>

---

## 2. Voice and tone

### 2.1 Who we sound like

**A meticulous, calm collections colleague.** Someone who has handled ten thousand drawers, who
tells you exactly what the record shows and exactly where it stops, who never guesses to fill a gap,
and who never makes a fuss when the network drops.

Concretely, that means:

| Trait | In practice |
| --- | --- |
| Precise | Names the object, the version, the stage. "Processing stopped at label detection", not "Something went wrong". |
| Calm | No exclamation marks. No "Oops". No red for anything that is not an error. Failures are stated at the same volume as successes. |
| Bounded | Says what a measurement does not establish, once, in a short clause. Never asserts more than the evidence carries. |
| Actionable | Every blocking message names the person who can unblock it: you, an administrator, or the service. |
| Economical | One idea per sentence. The reviewer reads this for six hours. |
| Consistent | The same action has the same label everywhere. "Save and revalidate" is never also "Apply changes". |

### 2.2 What we never sound like

| Never | Example of the failure mode | Where it exists today |
| --- | --- | --- |
| A legal disclaimer | Stacked negations and hedges that no one finishes reading | `capture_quality.dart:148` (44 words, four clauses) |
| An alarmed system | Shouting caps, warning colours on non-warnings | `main.dart:205`, `workspace.dart:609` (`SYNTHETIC ENVIRONMENT`) |
| A protocol log | Internal nouns exposed with no gloss | `workbench.dart:599` (`SHA-256:`), `large_record.dart:98` (`Retained artifact`) |
| A scolding teacher | "Invalid", "You must", "Required" as a bare word | `intake.dart:218` (`unsupported file type`) |
| A marketer | Aspirational headings that do not name the screen | `intake.dart:439` (`Bring a specimen into focus`), `workspace.dart:317` |
| A person with feelings | "Sorry!", "Great job!", emoji, apologies for things we did not cause | not present today; keep it that way |

### 2.3 Tone by situation

| Situation | Tone | Sentence pattern | Example copy | Surface |
| --- | --- | --- | --- | --- |
| Success | Silent, or a bare confirmation. Never congratulatory. | `<Object> <past-tense verb>.` | "Review recorded on version 4." | SnackBar, 4 s, no action |
| Waiting | Neutral present participle plus the object. Never "Please wait". | `<Verb>ing <object>…` | "Loading evidence…" | Inline skeleton, or a progress bar with a known denominator |
| Blocked by server | Factual, third person, system is the subject. Names the stage and the next attempt. | `<Stage> stopped. <What now>.` | "Processing stopped at authority lookup. The next automatic retry is at 14:32." | MaterialBanner or the record status card. Not a dialog |
| Blocked by policy | Flat and impersonal. Never implies the user did wrong. Names the role who can change it. | `<Thing> is not permitted <scope>. Ask <role> to <act>.` | "Clearance is not permitted until label coverage is confirmed. Confirm coverage, or ask a collection manager to defer this record." | Disabled control plus helper text under it |
| User error | Second person, imperative, contains the fix. | `<What is wrong>. <Do this>.` | "This file is 31 MB. Choose an image under 25 MB." | Inline, at the field, on submit or on blur |
| Data ambiguity | Neutral, source is the subject. Not an error. Offers a choice, not a fix. | `<N> readings differ for <object>.` | "Two readings differ for Label 2." | In-content chip, neutral colour, adjacent to the evidence |
| Model limitation | States the boundary of the claim, not a failure. Short label, expandable "Why". | `Not <measured/calibrated>.` | "Not calibrated. Why?" | Secondary text, `TextTheme.bodySmall`, with an expandable |
| Destructive confirmation | Names the object, the consequence, and what survives. Verb-specific button. | `<Action> <object>? <Consequence>. <What is retained>.` | "Start a new run? Results from run 3 are superseded. Run 3 stays in history." | AlertDialog, primary action labelled with the verb |

### 2.4 OPS-001: four categories that must never be conflated

PRD OPS-001 requires distinct treatment for user input errors, operational errors, data ambiguity,
and model limitations. They are distinguished by six mechanical properties, so the distinction is
testable and not a matter of taste.

| Property | User input error | Operational error | Data ambiguity | Model limitation |
| --- | --- | --- | --- | --- |
| Grammatical subject | you / the file you chose | the system, a stage, a run | the source, the readings, the label | the measurement, the score |
| Verb mood | imperative ("Choose", "Enter") | indicative past ("stopped", "was leased") | indicative present ("differ", "is unreadable") | negated present ("is not measured") |
| Who acts next | the person reading it | an administrator, an operator, or the clock | the reviewer, by deciding | nobody; it is a boundary statement |
| Retry offered | no; correct and resubmit | yes, named explicitly ("Retry from checkpoint") | no | no |
| Colour role | `colorScheme.error` | `colorScheme.tertiary` container (operational amber) | neutral `surfaceContainerHighest` | none; text only |
| Surface | inline at the field | banner or the status card | in-content chip next to the evidence | secondary text plus "Why" expandable |
| Prohibited words | "invalid", "illegal", "you must" | "you", "your" | "error", "problem", "failed" | "confidence", "accuracy", "verified" |

Worked contrast, all four about the same specimen:

- **User input error.** "Enter a reason before you save." (inline, under the reason field)
- **Operational error.** "Processing stopped at authority lookup after 5 attempts. An administrator
  must review the approved budget before this run continues." (status card, amber)
- **Data ambiguity.** "Two readings differ for Label 2. Choose one, or record the span as
  unreadable." (chip plus in-content action, neutral)
- **Model limitation.** "Review risk 62 of 100. Not calibrated." plus "Why" expanding to: "The score
  orders the queue. It is not a probability that the record is wrong, and it never overrides a
  validation gate."

A single screen may show all four at once. They must remain visually and grammatically separable
when it does.

---

## 3. Vocabulary

Two rules govern the table. First, one concept gets one word, used everywhere. Second, an internal
term stays visible only when the audit record depends on the reader seeing that exact token; the
rest move to a details sheet or disappear.

Placement values used below:

- **Primary** the main label or body text of a card, dialog or list row.
- **Secondary** `bodySmall`, below the primary text, same card.
- **Details** the per-object details sheet (`showModalBottomSheet` on mobile, side panel at
  1000 px and above), which replaces today's raw-JSON `ExpansionTile`s.
- **Hidden** never rendered; remains in the API payload and the copyable audit block only.

| Internal term | User-facing term | Visible | Placement | Why |
| --- | --- | --- | --- | --- |
| revision | **version** | yes | Primary ("Version 4") | The integer is the same, so audit references still resolve. "Revision" and "version" both appearing is the actual hazard. |
| CAS (content-addressed storage) | none | no | Hidden | The reviewer never makes a decision that depends on knowing the storage model. Replaced in copy by the checksum itself. |
| artifact | **evidence file** | yes | Primary | "Artifact" reads as a museum object in this domain, which is exactly wrong. |
| digest | **checksum** | yes | Details | Renaming only; the value stays. |
| SHA-256 | **Checksum (SHA-256)** | yes | Details, monospace, first 12 characters plus a copy action, full value on expand | Load-bearing for audit: it is the identity of the immutable original. DACS principle 6. Never in primary text. |
| lease | **reserved until \<time\>** | yes | Secondary | The reviewer needs the fact ("you cannot retry yet") and the time, not the mechanism. |
| dead letter | **stopped after repeated failures** | yes | Secondary, on the status card | Names the state in plain English. The term itself buys nothing. |
| disposition | **queue** (and the three queue names) | partly | Primary uses the queue name; the word "disposition" never appears | Cleared, Needs human review, Deferred are already the user's words. |
| run | **run** | yes | Primary ("Run 3 of 3") | A run is a countable object the reviewer reasons about, because a correction starts a new one. Keep it and define it once in the glossary sheet. |
| phase | **step** | yes | Primary ("Step: label detection") | Plain-English swap. GOV.UK 1.10. |
| observation | **reading** | yes | Primary ("Reading A", "Reading B") | Already partly done well at `workbench.dart:766`. Finish it: `observation_id` moves to Details. |
| region | **label region**, then **Label 1 / Label 2** | yes | Primary | First use is glossed; chips use the short form. |
| literal | **as written** | yes | Primary (field layer label) | Maps to Darwin Core `verbatim*`. "Literal" is programmer English. |
| parsed | **read as** | yes | Primary (field layer label) | The second Darwin Core layer, in a phrase a reviewer will not misread. |
| normalized | **standardized** | yes | Primary (field layer label) | Third layer. Plain word, same meaning. |
| authority | **authority** | yes | Primary | Genuine domain vocabulary for this audience. Keep. Gloss once: "Authority: the published reference list a value was matched against." |
| candidate | **suggested match** | yes | Primary | "Candidate" is ambiguous outside the codebase. The action becomes "Use this match". |
| unmeasured | **not measured** | yes | Primary, in the value slot | Must stay visible. It is the difference between honest absence and a fabricated zero. Never render "0" or an empty string in its place. |
| uncalibrated | **not calibrated** | yes | Chip next to any score, plus "Why" | Must stay visible. It is the load-bearing caveat on every score in the product. |
| synthetic | **test data** / **test environment** | yes | Banner | The honesty stays, the jargon and the shouting go. |

Terms that are **retired from the UI entirely**: CAS, artifact, digest (as a bare noun), lease,
dead letter, disposition, literal, parsed, normalized, candidate, synthetic, preflight (becomes
"server check"), adjudication (becomes "resolve"), segmentation (becomes "label detection").

One glossary surface exists: a **Terms** entry in the overflow menu, opening a scrollable sheet with
every row above, the user-facing term as the heading and the internal term in monospace beneath it.
This is what makes the retirements safe: nothing is hidden, it is relocated.

---

## 4. Pattern rules

Every rule below is stated so an engineer can implement it without asking a question. Character
budgets are in section 7.

### 4.1 Page titles

Noun phrase naming the screen. Sentence case. No verb, no period, no tagline underneath.

| Do | Do not |
| --- | --- |
| "Collection queue" | "Review the evidence. Resolve uncertainty." (`workspace.dart:317`) |
| "Add photographs" | "Bring a specimen into focus" (`intake.dart:439`) |
| "Review specimen FMNH-INS-0182" | "Review workbench" |

The subtitle slot under a page title carries **state, not slogan**: "48 records, 12 need review".

### 4.2 Section titles

Noun phrase, sentence case, no period, 32 characters or fewer, and it must name what is inside, not
the category of thing it is. "Independent readings" is good. "Evidence state" (`workbench.dart:141`)
is not, because every panel in this app is an evidence state.

Ampersands: spell out "and". `workbench.dart:1121` "Fields & evidence" becomes "Fields and
evidence"; Microsoft's guidance is to spell out words rather than use symbols.

### 4.3 Button labels

Verb first. Two to four words. One label per intent, used identically everywhere. No trailing
punctuation. Sentence case.

| Intent | Label | Notes |
| --- | --- | --- |
| Save a field correction | "Save correction" | Not "Save and revalidate": revalidation is a consequence, not the user's intent, and it belongs in the dialog body. |
| Approve a record | "Approve record" | Replaces "Record review approval" (`workbench.dart:1030`), which is a noun phrase, not a command. |
| Confirm coverage | "Confirm coverage" | Replaces "Confirm label coverage" only if "label" is already in the section title above it; otherwise keep the noun. |
| Retry a run | "Retry processing" | Already correct at `workbench.dart:1106`. |
| Start a new run | "Start new run" | Destructive-adjacent, see 4.4. |
| Dismiss a dialog | "Cancel" | Never "OK", never "Close" for a form. |
| Acknowledge an informational dialog | "Done" | Only where there is nothing to cancel. |

Loading states replace the label with the present participle and disable the button: "Saving…",
"Checking…", "Uploading…". They never show a bare spinner without a label, because a reviewer who
looks away needs to know which action is in flight.

### 4.4 Destructive and superseding actions

This product has no true deletes. It has **superseding** actions, which are more dangerous than they
look because the word "save" hides them. Treat any action that invalidates downstream results as
destructive-adjacent: it needs a confirmation dialog, a verb-specific primary button, and a sentence
naming what survives.

Actions in this class: correct classification (`workbench.dart:1049`), save region version
(`region_editor.dart:313`), start new run (`operational_panel.dart:160`), cancel processing
(`operational_panel.dart:159`), record a new language declaration
(`reading_declarations.dart:306`).

Pattern:

```
Title:   Correct classification?
Body:    A new run replaces the results that depend on the profile.
         Run 2 and its evidence stay in history.
Primary: Correct classification
Cancel:  Cancel
```

The primary button repeats the title's verb. Never "Confirm", never "Yes".

### 4.5 Confirmation dialogs

Title is a question or an imperative, 40 characters or fewer, no period. Body is at most two
sentences: consequence, then what is retained. Reason fields, where REV-005 requires one, sit below
the body with the label "Reason" and helper text naming who reads it: "Recorded in the audit history
with your name and the time."

Delete the phrase "This records your review" (`workbench.dart:347`) and every other sentence that
describes the act of saving. The button already says that.

### 4.6 Empty states

Three parts, in this order: title naming the absence, one sentence saying what would fill it, one
button that does it. Apple: an empty screen "can be daunting if it isn't obvious what to do next, so
guide them on actions they can take, and give them a button or link to do so."

The current queue empty state (`workspace.dart:396` to `407`) uses one body for two different
situations. Split them:

| State | Title | Body | Button |
| --- | --- | --- | --- |
| First run, nothing uploaded | "No specimens yet" | "Upload a photograph to create the first record." | "Add photographs" |
| Filters exclude everything | "No matches" | "No records match the current search and filters." | "Clear filters" |
| Queue genuinely empty after work | "Queue clear" | "Nothing needs review in this collection." | none |

The filtered state must offer "Clear filters" as its primary action. Today it offers "Add
photographs", which does not address the situation the reviewer is in.

### 4.7 Loading states

| Duration | Treatment | Copy |
| --- | --- | --- |
| Under 300 ms | Nothing | none |
| 300 ms to 3 s | Skeleton in the target shape | none |
| Over 3 s, unknown length | Skeleton plus a label | "Loading evidence…" |
| Over 10 s | Label plus a cancel affordance | "Loading evidence… Cancel" |

Present participle, one object, ellipsis character `…` (U+2026), never three periods. Never "Please
wait". Never a full-screen spinner over content that is already correct on screen.

### 4.8 Progress

Determinate whenever a denominator exists. Uploads have one, so the batch bar needs a visible
"Uploading 3 of 12" above it and per-file rows should show "4.2 of 18.0 MB". Never show a
percentage alone, because a stalled 94% and a moving 94% look identical.

The progress bar at `intake.dart:626` currently carries only `semanticsLabel: 'Upload progress'`,
which announces a state that never changes. It should announce the live counts: "Uploading 3 of 12,
4.2 of 18.0 megabytes".

Batch progress states the outcome split as it accrues: "9 uploaded, 2 in progress, 1 needs
attention". The failing item, not the count, is the tappable target.

### 4.9 Error messages

The triad, in order, in at most two sentences:

1. **What happened**, with the object named.
2. **Why**, only if the reason changes what the reader does.
3. **What to do**, as an imperative, or an explicit statement that the reader can do nothing and who
   can.

```
Bad:  Server preflight unavailable. Retry or check collection access.
Good: The server check did not run. Retry, or ask your administrator to confirm your
      collection access.
```

Never use "invalid", "illegal", "failed to", "an error occurred", "something went wrong", "Oops".
Never expose an exception class or a raw code in primary text; a correlation ID belongs in the
details sheet with a copy action, since PRD 16.5 requires correlation IDs to be traceable.

### 4.10 Inline validation

Fires on blur and on submit, never on every keystroke. NN/g: do not display errors prematurely,
because it is "like grading a test before the student has had a chance to answer."

Message sits in `InputDecoration.errorText`, is 80 characters or fewer, and states the rule
positively. Preserve what the user typed; never clear a field on validation failure.

| Current | Replace with |
| --- | --- |
| "A reason is required." (7 occurrences) | "Enter a reason for this decision." |
| "Enter a valid email address" (`auth.dart:232`) | "Enter an address like name@fieldmuseum.org." |
| "Enter a number from 0 to 100." (`search_filters.dart:35`) | keep; already correct |

The seven copies of "A reason is required." should become one constant, `Strings.reasonRequired`.

### 4.11 Helper text

One line under a control, 90 characters or fewer, present tense, describing what the control does
when used. Never repeat the label. Never carry a caveat; caveats use 4.15.

If helper text needs a second sentence, it is not helper text. It is a "Why" expandable.

### 4.12 Tooltips

Icon-only controls must have one; the current code already does this well
(`workbench.dart:426`, `439`, `965`). Tooltip text is the same string as the accessibility label, is
40 characters or fewer, and is a verb phrase: "Rotate view 90 degrees". Never a sentence, never a
period, and never the only place an important instruction lives, since tooltips are unavailable on
touch without a long press.

### 4.13 Status chips

Two to twenty characters, sentence case, no icon-only chips, and colour is never the sole carrier
(PRD 16.4). Every chip pairs a colour with a distinct shape or a leading glyph.

| Queue or state | Chip label | Role colour | Glyph |
| --- | --- | --- | --- |
| Cleared | "Cleared" | `tertiary` container | filled circle |
| Needs human review | "Needs review" | `secondary` container | half circle |
| Deferred | "Deferred" | `surfaceContainerHighest` | open circle |
| Processing blocked | "Blocked" | operational amber container | square |
| Duplicate | "Already in collection" | `surfaceContainerHighest` | open circle |
| Not calibrated | "Not calibrated" | none, outline only | none |

"Processing blocked" is an operational state and is never rendered in `colorScheme.error`, because
error red is reserved for things the reader can fix (section 2.4).

### 4.14 Timestamps and numbers

- Absolute time for anything auditable: `13 Sep 2026, 14:32 CDT`. Never relative time in the audit
  history or on a decision record, because "2 hours ago" is not a citable value.
- Relative time is allowed only in the queue list, and only paired with an absolute value in the
  accessibility label and the details sheet.
- UTC is labelled `UTC` when shown; the filter fields at `search_filters.dart:13` already do this
  and should keep it.
- Thousands separators on every count over 999.
- File sizes to one decimal in MB: "4.2 MB".
- Scores as "62 of 100", never "62/100" and never "62%".
- A number that was not measured renders as "Not measured", never `0`, `-`, or an empty cell.
  `operational_panel.dart:91` already does this correctly and is the model for the rest.
- Checksums truncate to the first 12 characters with an ellipsis and a copy action; the full value
  expands.

### 4.15 Caveat text

This is the pattern that fixes the largest problem in the current copy. A caveat is never a
paragraph in the flow of the page. It is:

1. A **short label**, 40 characters or fewer, stating the boundary. Always negative and specific:
   "Not calibrated", "Not measured", "Sharpness not checked".
2. A **"Why" affordance**, a `TextButton` with the label "Why" and a chevron, expanding an inline
   `AnimatedSize` region below it.
3. **Expanded body**, at most 300 characters, at most three sentences, in `bodySmall`.

```
Not calibrated.  Why ⌄

  A risk score orders the queue. It is not a probability that the record is
  wrong. Scores never override coverage, evidence or validation gates.
```

Rules for the pattern:

- The label alone must be true and sufficient. A reader who never expands "Why" must not be misled.
- One caveat per claim. Do not stack three caveats on one card; if three apply, the card is doing
  too much.
- Expansion state is per-caveat and not remembered across sessions, because these are exactly the
  statements a reviewer should re-read when a record is unusual.
- Caveats are never in `colorScheme.error` and never carry a warning triangle. They are statements
  of scope, not failures.

### 4.16 Accessibility labels

- Every `Semantics.label` is a complete phrase that stands alone out of context, 100 characters or
  fewer. "Label region 2 of 5, selected" beats "Region 2".
- Where a chip carries meaning through colour, the label carries it through words: the "Cleared"
  chip's semantic label is "Queue: cleared".
- Errors keep `liveRegion: true`, which the code already does; keep this and extend it to the
  operational status card, so a blocked run announces itself.
- Images keep the semantic labels already present at `workbench.dart:510` and `region_editor.dart:109`.
  Those are good and should not be shortened.
- A numeric value that reads badly aloud gets a `semanticsLabel` override: "62 of 100, not
  calibrated" for a chip that displays "62 / 100".
- Never use a tooltip as the only label; set both `tooltip` and `Semantics.label` to the same string.

---

## 5. Before and after

Forty real strings from the codebase. `{EM}` and `{EN}` mark literal em-dash and en-dash characters
present in the source.

### 5.1 Environment, session and access

| Location | Current string | Rewrite | What changed and why |
| --- | --- | --- | --- |
| `main.dart:205` | `SYNTHETIC ENVIRONMENT {EM} local fixture access only; not museum-approved records.` | Chip: `Test data` · Body: `This is a test environment. Records here are fixtures, not museum records.` | Em-dash removed. All-caps removed: GOV.UK notes capitals for extended text read as aggressive. Semicolon splice split into two sentences (one idea per sentence, 1.9). "Synthetic" replaced per section 3. |
| `workspace.dart:609` | `${environment.toUpperCase()} ENVIRONMENT {EM} fixture results are not real model processing or museum-approved records.` | `${labelOf(environment)} environment. Results are fixtures, not model processing or museum records.` | Same fixes. Interpolated value goes through `labelOf` so the banner reads "Staging environment", not "STAGING ENVIRONMENT". |
| `email_verification.dart:109` | `I verified my email {EM} check again` | `Check verification again` | Em-dash removed. Verb first (1.5). First person removed: Material forbids mixing "I" with "you" in one context. 36 characters down to 24. |
| `email_verification.dart:90` | `Open the verification link in your email, then check again. Collection access remains locked until your email and assigned role are verified.` | `Open the link we sent to ${email}, then check again.` · Secondary: `Your collection role is checked separately after verification.` | 22 words to 9 plus 9. "Remains locked" is alarming for a routine state (1.8). The address is echoed so the reader can spot a typo. |
| `auth.dart:283` | `Need an account or collection access? Ask your collection administrator to provide an account and assign a collection role. This app does not create accounts or grant roles.` | `No account or no collection access? Ask your collection administrator.` · "Why" expands: `This app cannot create accounts or assign roles. Both are managed by your collection administrator.` | 28 words in one block becomes 9 visible. The disclaimer that the app cannot do it is true and worth keeping, so it moves behind "Why" (4.15) rather than being deleted. |
| `magic_link_screen.dart:223` | `First time here? Your verified staff email creates your sign-in account. Collection access is managed separately by your collection administrator.` | `First time? Signing in with your verified staff email creates your account.` · "Why" expands: `Collection access is separate and is granted by your collection administrator.` | Two unrelated facts were competing in one paragraph. The one the reader needs now stays visible. |
| `workspace.dart:470` | `Your account has no assigned collection. Ask your administrator to grant a collection role, then check access again.` | `You have no collection assigned. Ask your administrator to assign one, then check again.` | Policy-blocked pattern (2.3): flat, names the role, no blame. 18 words to 14. "Grant a collection role" is internal phrasing for "assign a collection". |
| `magic_link.dart:295` | `This sign-in link has expired or was already used. Request a new link.` | keep, plus button `Send new link` | Already correct: what happened, then the fix, in two short sentences. Listed as the model the rest should match. |

### 5.2 Intake

| Location | Current string | Rewrite | What changed and why |
| --- | --- | --- | --- |
| `intake.dart:439` | `Bring a specimen into focus` | `Add photographs` | A page title must name the screen (4.1). The current title reads as an instruction about focus, which is a different concept on this exact screen. |
| `intake.dart:444` | `One photograph per specimen. Originals remain unchanged; processing continues after you leave.` | `One photograph per specimen.` · Secondary: `Your original file is never changed. Processing continues after you leave this screen.` | Semicolon splice split. The two reassurances move to secondary text so the rule reads first. |
| `intake.dart:479` | `Choose Non-sensitive only when these photographs and their label information are suitable for ordinary collection access. This choice applies to photographs added next; existing uploads keep their original classification.` | `Choose Non-sensitive only if these photographs and their labels are suitable for ordinary collection access.` · Helper: `Applies to photographs you add next.` | 30 words to 16 plus 6. The second clause is a scope note, which is helper text, not body copy. "Label information" to "labels". |
| `intake.dart:483` | `Local previews depend on this device. HEIC and approved TIFF/DNG families require a configured server codec and collection profile. Files can upload without a local preview; server completion verifies bytes, format and dimensions. A decoder block retains the upload for retry.` | `HEIC, TIFF and DNG may not preview on this device. You can still upload them.` · "Why" expands: `Previews depend on this device. The server verifies the file's bytes, format and dimensions when the upload completes. If the server cannot decode it, your upload is kept so you can retry.` | 41 words of unread paragraph becomes 15 visible. Everything true stays, behind "Why" (4.15). "Approved TIFF/DNG families" and "collection profile" are administrator concerns, not operator concerns, and are cut from the visible layer. |
| `intake.dart:513` | `Before submitting: check sharp focus, readable smallest text, even exposure, no glare, and every label inside the frame. Server quality checks are required; this client does not certify image quality.` | Heading `Before you upload, check:` then a five-item list: `Sharp focus` / `Smallest text readable` / `Even exposure` / `No glare` / `Every label inside the frame` · Secondary under the checkbox: `The server runs its own checks.` | A five-item checklist written as prose cannot be used as a checklist. Material 1.1: scannable formats. The self-deprecating "this client does not certify image quality" becomes one plain clause. |
| `intake.dart:521` | `I checked framing and readability` | keep | Correct as is. First person is right here: it is an acknowledgement the user is actively making, the exception Material allows. |
| `intake.dart:508` | `Direct camera capture is available in the Android and iOS app. In a browser, choose a photograph from your device.` | `Camera capture is available in the iOS and Android apps. In a browser, choose a file instead.` | 20 words to 16. "Direct" adds nothing. Second sentence made parallel to the button label it points at. |
| `intake.dart:379` | `Duplicate {EM} existing record retained` | Chip: `Already in collection` · Secondary: `This photograph matches an existing record by checksum. No new record was created.` | Em-dash removed. "Retained" is passive and internal. The reader's question is "did I just create a duplicate", so the answer is stated explicitly. |
| `intake.dart:420` | `Interrupted {EM} retry to resume from the server checkpoint` | Chip: `Interrupted` · Button: `Resume upload` · Secondary: `Resumes from where the server stopped.` | Em-dash removed. An instruction inside a status chip is not actionable; it becomes a real button. "Server checkpoint" is internal. |
| `intake.dart:582` | `Optional server preflight sends this original image to the collection service for decoding checks. It creates no specimen and makes no external provider call. Local measurements stay on this device until you choose an action.` | `Send this image to the server for a decode check.` · "Why" expands: `Nothing is created and no outside service is called. Your local measurements stay on this device until you choose an action.` | 35 words to 9 visible. "Preflight" retired (section 3). The privacy reassurances are genuinely reassuring and stay, behind "Why". |
| `intake.dart:602` | `Server preflight requires memory-limit enforcement on an approved runtime. Ask the service administrator to configure it. Changing this image format will not resolve that block; ordinary supported-image intake is checked separately.` | `The server check is not available. Ask the service administrator to enable memory-limit enforcement.` · "Why" expands: `Changing the image format will not help. Ordinary image intake is checked separately and is unaffected.` | Operational-error pattern (2.4): system is the subject, the role who can fix it is named. 31 words to 14 visible. |
| `intake.dart:418` | `Server decoding is blocked (${labelOf(...)}). The uploaded original is retained. Ask an administrator to check the approved codec, collection profile and runtime, then retry completion.` | `The server cannot decode this file (${reason}). Your upload is kept.` · Button: `Retry` · "Why": `Ask an administrator to check the approved codec, collection profile and runtime.` | The reassurance ("your upload is kept") is promoted, because it answers the reader's first question. The three-item administrator checklist is not the operator's job and moves behind "Why". |
| `intake.dart:200` | `${file.name}: choose a non-empty image under 25 MB.` | `${file.name} was skipped. Images must be under 25 MB and not empty.` | Says what happened before what to do (4.9). The current string implies the file is still selectable, which it is not. |
| `intake.dart:270` | `${file.name}: image exceeds the local 40 megapixel / 20,000 pixel axis limit.` | `${file.name} was skipped. It is over 40 megapixels or over 20,000 pixels on one side.` | "Exceeds the local ... axis limit" is three nominalizations in a row (1.10). The slash-joined compound limit is split into two readable conditions. |
| `intake.dart:542` | `After a restart, reselect the same original files. Checksums reconcile saved upload handles with server offsets; accepted records are not recreated.` | `After a restart, select the same files again to resume.` · "Why": `Checksums match your files to the uploads already on the server. Records that were accepted are not created twice.` | "Reselect", "upload handles", "server offsets" are all internal. 21 words to 9 visible. |
| `intake.dart:332` | `Recovered an interrupted camera photograph. Check its framing and readability before uploading.` | `Recovered an interrupted photograph. Check its framing and readability before you upload.` | Minor: "camera" is redundant on the capture path, "before uploading" to "before you upload" for the active second person. |
| `capture_quality.dart:114` | `Measured thumbnail · uncalibrated` | Chip: `Not calibrated` · Secondary: `Measured from a thumbnail.` | Two facts crammed into one chip. "Uncalibrated" to "Not calibrated" (section 3). |
| `capture_quality.dart:144` | `Large clipped areas or little contrast can hide text. Compare the preview with the original; these measurements do not establish sharpness or readability.` | `Clipping or low contrast can hide text.` · "Why": `Compare the preview with the original. These measurements do not show sharpness or readability.` | 23 words to 6 visible. "Do not establish" to "do not show": GOV.UK prefers the short word. |
| `capture_quality.dart:148` | `This device could not preview or measure the image. Inspect the original in a compatible viewer before confirming readability. Upload preserves the original; the server must decode it with an approved codec and establish its dimensions. Decoder or runtime blocks remain actionable upload errors.` | `This device cannot preview this image. Check the original in another viewer before you confirm readability.` · "Why": `Your original file is uploaded unchanged. The server decodes it and records its dimensions. If it cannot, the upload stays and you can retry.` | The worst string in the codebase: 44 words, four clauses, two semicolon splices, and the sentence the reader actually needs ("check it elsewhere first") buried in the middle. 16 words visible, everything else preserved behind "Why". |
| `capture_quality.dart:151` | `Focus, glare, framing and label coverage are not determined automatically. Check the smallest text, reflections and every label; retake the photograph if needed.` | `Focus, glare, framing and label coverage are not checked automatically.` · Button: `Retake photograph` · "Why": `Check the smallest text, any reflections, and that every label is in the frame.` | The instruction and the escape hatch were tangled in one sentence. The escape hatch becomes a button. "Determined" to "checked". |

### 5.3 Queue and workspace

| Location | Current string | Rewrite | What changed and why |
| --- | --- | --- | --- |
| `workspace.dart:317` | `Review the evidence. Resolve uncertainty. Keep every decision traceable.` | `${_items.length} records · ${needsReview} need review` | A three-clause mission statement under a page title is decoration, and Shopify's content guidance calls out duplicated and non-informative UI text explicitly. The slot becomes live state (4.1). |
| `workspace.dart:396` | `Your collection starts with a photograph` | `No specimens yet` | Empty-state titles name the absence (4.6). The current title is aspirational and does not tell a returning user whether something is broken. |
| `workspace.dart:402` | `Upload photographs or adjust your search. Completed results and processing blocks appear here.` | First-run: `Upload a photograph to create the first record.` · Filtered: `No records match the current search and filters.` with a `Clear filters` button | One body was serving two states, so it addressed neither. The filtered state now offers the action that resolves it, instead of "Add photographs". |
| `workspace.dart:293` | `This record changed while you were reviewing. Your decision was not saved. Refresh evidence and compare the current version before trying again.` | Dialog title `Record changed` · Body: `Another reviewer saved version ${n} while you were working. Your decision was not saved.` · Primary `Refresh and compare` · Secondary `Cancel` | The single most important message in the reviewer's day, currently a 22-word inline `Text`. It becomes a dialog (NN/g 1.3: severity picks the surface), names the version, and turns "refresh evidence and compare" into the primary button rather than an instruction. |
| `workspace.dart:433` | `Risk: ${n} / 100 · Uncalibrated` | `Risk ${n} of 100` plus a `Not calibrated` outline chip; `semanticsLabel: 'Review risk ${n} of 100, not calibrated'` | "62 / 100" reads as a fraction aloud (4.14). The caveat becomes a chip so it is a consistent object across the app rather than trailing text. |
| `workspace.dart:617` | `Runtime blocked: ${...}. Contact the collection administrator.` | `Processing is blocked: ${...}.` · Secondary: `Ask your collection administrator to review it.` | "Runtime" is internal. "Contact" to "Ask", which is what the reader will actually do. Operational amber, not error red (2.4). |
| `workspace.dart:324` | `Exact specimen ID; use Filters for other criteria` | `Exact specimen ID. Use Filters for anything else.` | Semicolon to period. "Other criteria" to "anything else". |
| `search_filters.dart:15` | `Minimum risk (0{EN}100)` | `Minimum risk (0 to 100)` | En-dash removed. Spelled range also reads correctly to a screen reader, which announces the en-dash inconsistently. |
| `search_filters.dart:67` | `All filters must match. Risk filters exclude unmeasured records; risk does not establish clearance.` | `All filters must match.` · "Why": `Risk filters exclude records with no measured risk. Risk never determines clearance.` | Three claims in one line. The operative rule stays visible; the two caveats move behind "Why". |

### 5.4 Workbench, evidence and operations

| Location | Current string | Rewrite | What changed and why |
| --- | --- | --- | --- |
| `workbench.dart:133` | `Creates a versioned decision. The server reruns affected checks and determines the queue.` | `Saving records a decision on version ${n} and reruns the affected checks. The server decides the queue.` | "Creates a versioned decision" has no subject and no object the reader recognizes. Naming the version connects the dialog to the record header. |
| `workbench.dart:171` | `Choose an unresolved state when the source cannot support a reading. Independent observations remain unchanged and clearance stays blocked.` | `Choose an unresolved state if the source does not support a reading.` · "Why": `Both readings are kept unchanged. The record stays blocked from clearance.` | 20 words to 12 visible. "Independent observations" to "both readings" (section 3). REV-010 depends on this control being understood, so the operative sentence must read first. |
| `workbench.dart:347` | `This records your review. All evidence and validation gates still apply; the server determines clearance.` | `All evidence and validation checks still apply. The server decides clearance.` | "This records your review" describes the button that is directly below it (4.5). "Validation gates" to "validation checks". |
| `workbench.dart:1030` | `Record review approval` | `Approve record` | Noun phrase to verb phrase (1.5). 22 characters to 14. |
| `workbench.dart:1023` | `Confirm label coverage` | keep | Already verb-first and specific. |
| `workbench.dart:420` | `Legacy source has no verified orientation derivative. Preview orientation may differ from original coordinates; region correction and overlays require a verified derivative.` | `This image has no verified orientation, so region editing is unavailable.` · "Why": `The preview may be rotated differently from the original coordinates. Region correction needs a verified orientation.` | 23 words in which the consequence for the reader ("you cannot edit regions") appeared last. It now appears first. "Derivative" and "legacy source" are internal. |
| `workbench.dart:831` | `No disagreement details recorded. This does not establish label coverage.` | `No differences recorded between the readings.` · "Why": `Agreement between readings does not mean every label was found.` | Two unrelated claims joined by a period. The caveat is real and stays, in the pattern that keeps it readable. |
| `workbench.dart:873` | `Literal text, candidates, resolved values and authority evidence are separate. Missing mandatory values block clearance.` | `As written, read as, standardized and authority values are recorded separately.` · Secondary: `Missing required values block clearance.` | Applies the section 3 vocabulary. "Mandatory" to "required". This string teaches REV-003's layering, so its words must match the column headers beside it. |
| `workbench.dart:907` | `Unsupported field state. Editing is disabled; refresh or update the client.` | `This field cannot be edited in this version of the app.` · Button: `Refresh` · "Why": `The server sent a field state this app does not recognize. Refreshing may help; otherwise update the app.` | "Unsupported field state" is an internal diagnosis presented as a user-facing sentence. The reader learns what they can do first. |
| `workbench.dart:1068` | `This request may already have executed. Reconcile the unknown external outcome before explicitly requesting another attempt.` | `The last request may already have run. Its result is unknown.` · "Why": `Reconcile that request before you retry. This app never retries it for you.` | Model/operational boundary made explicit as two facts. "Explicitly requesting another attempt" to "retry". |
| `operational_panel.dart:112` | `The last external request may have executed. Its outcome is unknown. An authorized operator must reconcile that request before deliberately retrying; the client never repeats it automatically.` | `The last external request may have run. Its result is unknown.` · Secondary: `An authorized operator must reconcile it before anyone retries.` · "Why": `This app never repeats the request automatically.` | 27 words to 11 plus 9. Same content, three layers deep instead of one wall. The "never automatically" promise is the reassurance and belongs behind "Why", not competing with the warning. |
| `operational_panel.dart:116` | `Processing stopped at a budget or cost-policy gate. An administrator must review the approved limit or provider configuration. Missing cost information is not zero cost.` | `Processing stopped at a cost limit.` · Secondary: `An administrator must review the approved limit or the provider configuration.` · "Why": `Where a cost is not recorded, it is unknown, not zero.` | "Budget or cost-policy gate" collapses to "cost limit". The final sentence is one of the most important honesty statements in the product and reads better as its own line than as a paragraph tail. |
| `operational_panel.dart:126` | `External work is leased until ${t}. Retry, resume and new-run requests must wait for the lease to end.` | `Reserved by the processing service until ${t}.` · Secondary: `Retry, resume and new run are unavailable until then.` | "Lease" retired (section 3). The second sentence states the consequence the reader is about to hit, in the same words as the buttons that are disabled. |
| `operational_panel.dart:122` | `Automatic attempts exhausted. Authorized recovery requires an explicit reason.` | `Automatic retries have stopped.` · Secondary: `Retrying now requires a reason.` | "Exhausted", "authorized recovery", "explicit" all replaced with the plain equivalents (1.10). |
| `review_context.dart:67` | `Uncalibrated measurements. A valid image is not proof of readable labels or complete coverage.` | Chip: `Not calibrated` · "Why": `A readable image does not prove the labels are legible or that all of them are in frame.` | "A valid image is not proof of" is a legal construction. Restated as a plain claim about what the reader can conclude. |
| `review_context.dart:110` | `Scores are uncalibrated; they do not establish correctness.` | Chip: `Not calibrated` · "Why": `Scores order the queue. They are not a measure of whether a reading is correct.` | Same pattern applied consistently, which is the point: three different phrasings of "uncalibrated" exist today across `review_context.dart`, `risk_assessment.dart` and `capture_quality.dart`. |
| `risk_assessment.dart:216` | `Reading agreement does not establish correctness.` | `Two readings agreeing does not make them right.` | Nominalization removed ("agreement" to "agreeing", "establish correctness" to "make them right"). This is the sentence most likely to be skimmed, so it should be the plainest one on the screen. |
| `large_record.dart:95` | `The standard workspace exceeds its response limit. Complete evidence is available as a read-only artifact. Field edits and approval are unavailable in this view.` | `This record is too large for the normal view.` · Secondary: `You can read the complete evidence here. Editing and approval are unavailable.` | "The standard workspace exceeds its response limit" describes a server constraint from the server's point of view. "Artifact" retired (section 3). |
| `audit_history.dart:179` | `This retained record is historical evidence. It cannot be edited or used as the current review revision.` | `This is a past version. It is read only.` · Secondary: `Your current review is on version ${n}.` | 18 words to 9 plus 6. "Retained record", "historical evidence" and "review revision" are three internal terms for one idea. |
| `reading_declarations.dart:221` | `Enter one candidate per line. Labels are preserved as declarations; no language or script is inferred. Leave a list empty to record no declaration. This does not approve the record.` | `Enter one language per line.` · "Why": `Your entries are recorded exactly as typed. Nothing is inferred. An empty list records no declaration, and saving does not approve the record.` | 30 words of dialog helper text before the reader reaches the first field. 5 words visible. |

---

## 6. Rules for agents

Run this checklist against every user-facing string before committing. Each item is mechanically
checkable; items 1 to 8 should become a `dart test` or a CI grep.

1. **No em-dash or en-dash.** `grep -rnP '\x{2014}|\x{2013}' lib/` must return nothing. Use a
   period, a comma, a colon, or a hyphen.
2. **Length is within budget.** Check the string against section 7 by its widget type. A string over
   budget is not shortened by shrinking the font; it is rewritten or split.
3. **Sentence case.** First word capitalized, everything else lowercase unless it is a proper noun,
   a taxon, or a standard's name (SHA-256, HEIC, UTC, Darwin Core). No Title Case anywhere.
4. **No terminal punctuation** on titles, headings, button labels, chips, tooltips, tab labels or
   text-field labels. Body text, helper text and error messages do take a period.
5. **One idea per sentence.** No semicolon splices. If the string contains `;`, split it. Any
   sentence over 25 words is a defect.
6. **Banned words.** `invalid`, `illegal`, `failed to`, `an error occurred`, `something went wrong`,
   `oops`, `please wait`, `simply`, `just`, `easily`, `unfortunately`, `sorry`, `we`, `our`,
   `delightful`, `seamless`. Also banned as bare UI text: `OK`, `Yes`, `No`, `Confirm`, `Submit`.
7. **No internal term without a glossary row.** Every noun in the string is either plain English or
   appears in the section 3 table with placement `Primary` or `Secondary`. Terms marked `Hidden` or
   `Details` must not appear in primary text. New internal terms require a new glossary row in the
   same commit.
8. **No emoji, no ASCII art, no decorative punctuation.** The middle dot `·` is permitted only as a
   separator between metadata values, never inside a sentence.
9. **Error strings satisfy the triad.** What happened, why (only if it changes the action), and what
   to do. Two sentences maximum. If you cannot say what to do, say who can.
10. **The error category is one of the four in section 2.4, and only one.** Check the grammatical
    subject, the verb mood, and the surface against that table. If a string mixes an input error
    with a model limitation, it is two strings.
11. **Buttons are verb first,** two to four words, and the same intent uses the same label
    everywhere in the app. Before adding a label, grep for an existing one with the same meaning.
12. **Destructive and superseding actions have a confirmation** whose primary button repeats the
    title's verb, and whose body names what is retained.
13. **No caveat longer than 40 characters is visible by default.** Anything longer uses the label
    plus "Why" pattern in 4.15. The visible label must be true on its own.
14. **Absence renders as words, never as a value.** "Not measured", "Not recorded", "Not declared".
    Never `0`, `-`, `null`, `N/A`, or an empty string in a value slot.
15. **Scores carry their caveat chip.** Any numeric score rendered without an adjacent
    `Not calibrated` chip is a defect.
16. **Second person, present tense, active voice.** No "we", no "the user", no "the system will
    have been". Passive voice is allowed only where the actor is genuinely unknown or irrelevant.
17. **Interpolated values pass through `labelOf`** before display, so `snake_case` server enums never
    reach the screen raw.
18. **The string is a `const` in one place** if it appears more than once. Seven copies of
    "A reason is required." is seven chances to diverge.
19. **Every icon-only control sets both `tooltip` and `Semantics.label`** to the same string, and
    every status conveyed by colour is also conveyed in the semantic label.
20. **Read it aloud.** Microsoft's test, and it catches nominalization stacks that pass every other
    check. "Server preflight requires memory-limit enforcement on an approved runtime" fails here
    and nowhere else.
21. **Check the string against the screen it lives on.** A caveat that is correct in isolation but is
    the third caveat on the card is still a defect; the card is doing too much.

---

## 7. Length budgets

Hard maximums. A string at the maximum should be rare; the target column is where most strings
should land. Counts are characters including spaces, measured on the English source before
localization, which typically expands by 30 percent.

| Element | Target | Maximum | Notes |
| --- | --- | --- | --- |
| Button label | 14 | 24 | Two to four words. Must not wrap at 320 px logical width. |
| Text button / inline link | 12 | 20 | "Why", "Retry", "Clear filters". |
| Status chip | 12 | 20 | Truncation in a chip is a defect, not an ellipsis case. |
| Tab label | 10 | 18 | Three tabs must fit side by side at 360 px. |
| SnackBar | 50 | 70 | One clause plus at most one action. No SnackBar for anything the user must act on. |
| Banner body | 90 | 120 | Plus at most two actions. Banners are for operational state, not input errors. |
| Dialog title | 28 | 40 | No period. Question or imperative. |
| Dialog body | 120 | 200 | Two sentences maximum. |
| Empty-state title | 20 | 30 | Names the absence. |
| Empty-state body | 70 | 120 | One sentence, followed by a button. |
| Page title | 22 | 30 | Noun phrase. |
| Page subtitle | 40 | 60 | State, not slogan. |
| Section title | 22 | 32 | Noun phrase, no period. |
| Field label | 20 | 32 | No period, no colon. |
| Helper text | 60 | 90 | One line, one sentence. |
| Inline validation | 55 | 80 | Contains the fix. |
| Tooltip | 24 | 40 | Same string as the semantic label. |
| Caveat label | 24 | 40 | Visible by default; must be true alone. |
| Caveat "Why" body | 180 | 300 | Three sentences maximum, `bodySmall`. |
| Accessibility label | 60 | 100 | Complete phrase, stands alone. |
| Reason field placeholder | 40 | 60 | Names who reads it. |

Enforcement: add `test/copy_budget_test.dart` asserting these limits over a single
`lib/src/strings.dart`, and a pre-commit grep for items 1 and 6 of section 6. Strings that live
inline in widget code cannot be checked, which is the main argument for centralizing them.

---

## Sources

Every URL below was opened while writing this document.

- NN/g, UX Writing Study Guide: <https://www.nngroup.com/articles/ux-writing-study-guide/>
- NN/g, Error-Message Guidelines: <https://www.nngroup.com/articles/error-message-guidelines/>
- NN/g, An Error Messages Scoring Rubric: <https://www.nngroup.com/articles/error-messages-scoring-rubric/>
- NN/g, UI Copy: Command Names and Keyboard Shortcuts: <https://www.nngroup.com/articles/ui-copy/>
- NN/g, Microcontent: <https://www.nngroup.com/articles/microcontent-how-to-write-headlines-page-titles-and-subject-lines/>
- NN/g, Rewriting Digital Content for Brevity: <https://www.nngroup.com/articles/rewriting-content-brevity/>
- Material 3, Content design overview: <https://m3.material.io/foundations/content-design/overview>
- Material 3, Style guide, UX writing best practices: <https://m3.material.io/foundations/content-design/style-guide/ux-writing-best-practices>
- Material 3, Style guide, Word choice: <https://m3.material.io/foundations/content-design/style-guide/word-choice>
- Material 3, Notifications: <https://m3.material.io/foundations/content-design/notifications>
- Material 3, Global writing: <https://m3.material.io/foundations/content-design/global-writing>
- Apple HIG, Writing: <https://developer.apple.com/design/human-interface-guidelines/writing>
- Microsoft Writing Style Guide, Top 10 tips: <https://learn.microsoft.com/en-us/style-guide/top-10-tips-style-voice>
- Shopify, App design content: <https://shopify.dev/docs/apps/design/content>
- Shopify, Voice and tone: <https://shopify.dev/docs/apps/design/content/voice-and-tone>
- GOV.UK, Clear language: <https://guidance.publishing.service.gov.uk/writing-to-gov-uk-standards/writing-guidelines/clear-language/>
- GOV.UK, Right tone: <https://guidance.publishing.service.gov.uk/writing-to-gov-uk-standards/writing-guidelines/right-tone/>
- Darwin Core quick reference guide, TDWG: <https://dwc.tdwg.org/terms/>
- DACS, Statement of Principles, Society of American Archivists: <https://saa-ts-dacs.github.io/dacs/04_statement_of_principles.html>

Note on Polaris: the URLs in the original brief (`polaris.shopify.com/content/voice-and-tone`,
`/content/actionable-language`, `/content/error-messages`) now 301 to a Polaris landing page and the
individual content pages are gone. The equivalent current guidance is at `shopify.dev/docs/apps/design/content`
and its `voice-and-tone` subpage, both cited above. Material's "alerts and errors" subpage named in
the brief could not be located at any URL under `m3.material.io/foundations/content-design/`; the
error-message guidance cited here comes from NN/g, Apple and Shopify instead.
