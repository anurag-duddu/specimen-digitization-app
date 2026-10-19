# Reading old insect labels with NVIDIA Nemotron

Field Museum specimen digitization pilot, Chicago. Measured 18 October 2026.

## What we do

Natural history collections hold millions of pinned insects and microscope
slides. Each one carries small handwritten labels saying where, when and by
whom it was collected, often 50 to 100 years ago. Until those labels are
typed into a database, scientists cannot search them. Our pilot turns a
photo of a specimen into a checked digital record:

1. find the labels in the photo (SAM 3);
2. two different AI models read each label independently;
3. a first pass compares the two readings with the image and picks the
   right one, or leaves the label for a person;
4. parse the text into fields (place, date, collector, elevation);
5. a field expert for each field checks it against public sources such as
   GBIF and Catalogue of Life;
6. a curator reviews whatever is left uncertain.

## Where Nemotron fits

We added NVIDIA Nemotron 3.5 Super VL as a second option for every
language-model step. One model can do all of them: it reads images, follows
a schema and calls tools. It runs on Baseten through Hugging Face, with no
new account or secret. Each step can be switched to Nemotron on its own. In
production it is off until we decide.

## What we measured

We used real 1946 and 1948 handwritten labels from the Philippines and
Guatemala, checked against our own careful reading of each image. Each
step went through the app's own code with only the model changed.

| Step | Nemotron compared with today's model |
|---|---|
| Reading | No failed calls in 45, about 2 seconds a label (4x faster). It got 76% of label facts right alone; paired with our other reader, the pair covered 95% of facts, as well as today's pair. |
| Parsing | About as accurate as today's model, with fewer wrongly filled fields but less consistent from run to run. About 1 second against 24 (20x faster), and cheaper. |
| Comparing readings | With reasoning on, wrong picks are as rare as today's (15%), but a third of labels were left for a person. |
| Field research | Not yet: half of the field experts' answers failed our checks. |

## What would make Nemotron our default everywhere

Specific things we hit, in case they help the team:

1. **Reasoning and forced tool calls.** On Baseten, Nemotron skips its
   reasoning whenever a tool call is forced (0-1 reasoning tokens against
   about 1,500 with tool choice "auto"). Structured output forces one. We
   now send "auto" for the comparison step.
2. **Reasoning length.** It used about 2,800 output tokens to compare two
   readings, so nearly a third of calls ran past our 4,096-token cap. A
   reasoning budget control would fix that.
3. **Handwritten digits.** It read a handwritten "2" as "a" or "D" in dates
   and codes. Place names were strong: 87 of 96 right.
4. **Agentic answers.** In field research it wrote the word "None" into
   empty fields and invented identifiers such as "wikidata:Q123456".

## Cost per specimen

Today a specimen costs about 2.9 cents in total, 1.7 cents of it AI
(billed, 18 October 2026). From our measured per-call costs:

- Nemotron reading and parsing: about the same AI cost as today, and much
  faster.
- Nemotron in every step: about 3.5 times the AI cost of today's steps,
  estimated the same way from measured per-call costs. Most of that is
  field research, where today's model benefits from heavy prompt caching.

## What free credits would let us do

- **Run Nemotron as a third reader** on the 1,000 slides we have already
  photographed, and measure it against curator decisions at scale. That
  would give NVIDIA a real-world handwriting result, which we would share if
  the museum agrees.
- **Re-test comparing and field research** as reasoning controls improve,
  without spending the pilot's small budget.
- **Try a second NVIDIA vision model** as our independent second reader, if
  one becomes available on a hosted provider. Two NVIDIA readers need two
  different models.
- **Scale past the pilot.** Reading and parsing cost about 0.14 cents a
  specimen on Nemotron, so USD 1,000 of credits covers those steps for
  roughly 700,000 specimens. Every AI step on Nemotron would cover about
  25,000 specimens.

Method and every number:
`docs/product-requirements/NVIDIA_NEMOTRON_OPTION.md`, section 7.
