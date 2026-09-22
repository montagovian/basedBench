# Duplicate and joke-family audit

Issue [#6](https://github.com/montagovian/basedBench/issues/6).

The pilot now has a read-only duplicate audit. It distinguishes an exact copy,
a possible repeat and an item it could not assess. None of those is a finding
about whether the meme is good, safe or correctly explained.

## Completed bounded run

The combined retrieval found **all three known repeat families**. Across the
100 fresh candidates, it found **one exact-copy pair and 28 possible-match
pairs**, involving 20 fresh posts. These are pair counts, not 29 excluded items.
There were no paid model calls or API costs.

| Coverage / result | Count |
| --- | ---: |
| Archived records | 5,886 |
| Archived static images assessed | 5,390 |
| Archived missing images / animated files | 479 / 17 |
| Fresh static images assessed / missing | 73 / 27 |
| Legacy explanations / fresh comment samples compared | 2,537 / 97 |
| Fresh–legacy match pairs / fresh–fresh match pairs | 26 / 3 |
| Fresh posts with an exact-copy match | 2 |
| Fresh posts with other candidate matches | 18 |
| Fresh posts with no match found | 57 |
| Fresh posts without an image and without a text match | 23 |

Four of the 18 posts with candidate matches also have missing images. All 27
missing-image cases therefore remain incomplete, not just the 23 whose summary
route is `not_assessed`. Three fresh posts have no text surviving the comment
selection rule; two have no usable comments and one has only shorter comments.
Those three still received image comparisons.

The archive includes all 519 published items: 518 have static images, one is
animated, and all 519 have explanations. Animated files participate in exact
byte matching only; the near-image method does not compare their frames. Thus
image near-match coverage is incomplete even for the published set. The text
encoder read 169,670 tokens across the selected evidence, with no tokens omitted
from those selected fields. This does not make the source comment sample complete.

| Known family | Near-image retrieval | TF-IDF retrieval | MiniLM retrieval |
| --- | --- | --- | --- |
| Teapot carton | Found | Found | Found |
| Number-plate prank | Missed | Found | Found |
| Clarkson / Porsche 928 | Found | Missed | Found |

These are outcomes under the frozen thresholds and top-five limits. The
number-plate pair changes light/dark presentation and framing enough to defeat
this image method. Text recovers it. Conversely, both text methods miss the
same Hello Kitty comic in the diagnostic table below because its stored
explanations emphasize different meanings. No one method establishes completeness.

Assistant inspection of all six fresh near-image pairs found recognizable
reposts: the spouse-comparison tweet, language-reaction map, American Squid Game
joke, Uber/Benz narrative, examination/echo comic and Toy Story ratings post.
Two of those match published images; four match archive records outside the
published set. They remain candidates in the automatic report, with the visual
observations saved separately. This small retrieved sample does not estimate
recall or general near-image precision.

Six additional semantic-only pairs were inspected:

- The differently framed **“who is JSON?”** screenshots share the same core
  image and joke; the image search missed them.
- **DiCaprio:** an Epstein comparison and an age-gap-as-parenthood joke are
  different jokes despite an encoder score of 0.791. **Dinosaurs:** a scarred
  dinosaur comic and a Spinosaurus-reconstruction joke are likewise different,
  despite a score of 0.658. Shared topic is a real source of false matches.
- The **“every base calls itself 10”** tier list and alien-counting comic share
  a core inference but have different setups. Keep this as an explicit family
  policy question, not an automatic merge.
- The laptop-company and square-root-treasure matches have missing fresh images.
  Their comments suggest relations, but their visual jokes remain unverified.

The 12 inspected fresh pairs are an exploratory selection. The remaining
candidates are unadjudicated; no precision estimate or automatic exclusion is
claimed. These observations are assistant annotations, not new curator labels.

The split check flags the two already-known families crossing development and
calibration (number plate and Clarkson), plus five additional pending cross-split
links. It preserves the original assignments and records the retrieval exposure.
Later splits must resolve or quarantine those links before claiming independence.

Run artifacts: `data/backfill/duplicate-audit-v1/`. Analysis, visual controls,
exposure and split audit: `data/backfill/duplicate-controls-v1/`. Audit ID:
`fa506730f16087403cee929f78e79d1ac4c69d0e5e131c731e0be18616dda838`.
Implementation commits: `87c82ec`, `5cb4dd5`, local and unpushed.
**389 tests passed.** Source database, frozen corpus and human-feedback hashes
were unchanged. An offline recomputation produced identical report, vector and
token-packing hashes, with runtime versions verified against the frozen plan.
The code and result summaries are committed; raw evidence and images remain local.

## What the check does

- Compare every available fresh image against the archived images and the other
  fresh images. Equal file bytes or equal full decoded pixels establish a copy.
  Re-encoding a PNG without changing its pixels still counts as an exact copy.
- Search original and border-trimmed views using perceptual hashes. Rank nearby
  images by pixel difference after resizing. Border removal and resizing are
  retrieval aids: they can discard meaningful differences, so these matches
  remain candidates even when the similarity is very high.
- Compare stored legacy explanations with up to five substantive fresh comments,
  using both word/phrase overlap (TF-IDF) and the pinned local MiniLM encoder.
  The encoder reads long text in chunks without dropping tokens. These methods
  retrieve possible repeated jokes; neither determines that two jokes are equal.
- Preserve the matching post IDs, image hashes, compared crops, distances,
  text-similarity scores, comment IDs and published-release membership. Matches
  against excluded historical items are visible; they do not automatically
  eliminate a fresh candidate.

Both image and text retrieval retain up to five matches **per query, per pool**
(legacy and fresh). Exact matches are uncapped. Image retrieval requires both
64-bit hash distances at most eight; text similarity floors are 0.35 for TF-IDF
and 0.65 for MiniLM. These are exploratory retrieval settings, not calibrated
probabilities or production acceptance thresholds.

Fresh comment selection uses at least 40 characters, excludes moderator comments,
and sorts by score then comment ID. It is a bounded evidence sample, not a
consensus determination. It omits titles and curator labels. Legacy explanations
may themselves be defective. Neither shared topic nor shared template establishes
a repeated punchline. The semantic comparison should be repeated on supported
candidate explanations once the answer workflow has produced them.

## Consequences for admission and later splits

An exact match establishes that two records contain the same image, **not which
record to keep**. Release membership, explanation correctness, content policy,
image quality and later collection policy still matter. In particular, matching
an excluded historical record does not mean the joke is already published.

The report's `copy_found`, `review_matches`, `no_match_found` and `not_assessed`
values are duplicate-component findings, not accept/reject decisions. Per-item
image status remains explicit even where text retrieved a match. Missing images
must still defer in the admission workflow. No match found does not prove novelty.

`split_audit(assignments, edges)` joins confirmed copies and previously reviewed
families into indivisible groups, including links through unassigned members.
An unresolved similarity link crossing those groups' proposed splits holds the
split for adjudication; it does not silently merge families. Once reviewed,
same-joke pairs can become confirmed edges and different-joke pairs can be removed
from the pending constraints, retaining their evidence and decision provenance.
The existing frozen evaluation splits are not rewritten. This is a scoped audit,
not proof that the entire archive is free of family leakage. The retrieval run
reads historical explanations across the old splits; this is development work,
not a new untouched holdout. Keep that exposure in later evaluation provenance.
With no proposed assignments, split readiness is unassessed (`null`), not a pass.

For #7/#8, consume the frozen report by audit ID, retain each match and its
published-membership evidence, and distinguish potential redundancy from intrinsic
suitability. Do not call the old `auto_exclude_duplicate_images` helper: its rule
of excluding matches to any reviewed item is not the new pilot's admission policy.
Retain uncertain pairs outside automatic admission until a bounded decision rule
can resolve them. Deferral need not create a mandatory human queue.

## Reproduce locally

Raw images, frozen evidence, vector arrays and match records stay under ignored
`data/`. The database is opened read-only. The audit does not write reviews,
answers, release membership or human feedback, and it makes no network requests
or paid inference calls. MiniLM must already be present in its pinned local cache.

```sh
uv run --no-sync python -m basedbench.pipeline.duplicate_audit prepare \
  --inventory data/backfill/inventory-june20-26-v1 \
  --output data/backfill/duplicate-audit-v1
uv run --no-sync python -m basedbench.pipeline.duplicate_audit run \
  --output data/backfill/duplicate-audit-v1
```

Preparation verifies the source inventory manifest and freezes the read-only
archive records, fresh comment sample, image fingerprints, thumbnails and known
family controls. It records source/code hashes, model revision, library versions
and retrieval settings. Rerunning uses those frozen records and thumbnails,
verifies their hashes, and recomputes the local retrieval; it does not collect
new evidence. Changed code or inputs require a new run directory.

The model is `sentence-transformers/all-MiniLM-L6-v2`, revision
`1110a243fdf4706b3f48f1d95db1a4f5529b4d41`, loaded locally on CPU. The existing
chunked encoder implementation is reused; there is no fitting to review labels.

## Real-image diagnostic controls

The three previously reviewed positive families are the teapot carton,
number-plate prank and Clarkson/Porsche 928. Their known-family links are added
**after** measuring retrieval, so supplying those links cannot manufacture a
successful result. They are development controls, not an independent accuracy
sample.

Additional assistant visual inspection found these useful contrasts:

| Pair | Visual evidence | Implication |
| --- | --- | --- |
| `1n4gbgg` / `1t55ci9` | Same three-panel reaction template, different writing: SCP island/routine versus childhood imagination and sociology. Image hash distances are only 3 and 0, despite the different references. | A near-image match can be a different joke. Preserve it as a candidate, never a confirmed copy. |
| `1ja7tpy` / `1rpdvw4` | Same Family Guy “asking too many questions” template; one asks about horses in films, the other about energy drinks in bottles. | Shared format and mechanism need not mean interchangeable benchmark content. The implied questions differ. |
| `1kn0cs2` / `1sdqoek` | Same first-date/Hello Kitty car-reveal comic at different resolutions, but the stored explanations emphasize different things. | Text disagreement does not establish a new joke; the resized image remains a useful retrieval signal. |

These were selected by looking for archive image-hash neighbors with low
explanation word overlap, then visually inspected after the retrieval settings
were frozen. They demonstrate failure modes; they do not estimate precision or
recall. They are assistant diagnostic annotations, not new human ground truth,
and they do not replace any curator label or adjudicate every returned pair.
Local evidence is under `data/backfill/duplicate-controls-v1/`.
