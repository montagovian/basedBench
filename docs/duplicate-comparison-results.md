# Bordered-copy and explanation retrieval results

September 22, 2026 · [Issue #17](https://github.com/montagovian/basedBench/issues/17)

**Both new routes recover the missed children-on-phones copy.** Broader image
windows add that pair without losing earlier image hits or adding a new inspected
false match in the fixed packet. Supported explanations also retrieve it, but
replacing the old text loses a plausible different-image joke-family link.
Retain both text views and keep explicit adjudication separate from retrieval.
No frozen outcomes, representatives, splits or publication membership changed.

The [predeclared local comparison](duplicate-comparison.md) used **zero paid
calls, $0 model cost, 21.711 seconds wall time and 21.641 CPU seconds**. The local
MiniLM weights were already cached; offline loading was enforced. The explanation
source experiment's separate 20.0¢ cost is reported in [#16's results](connection-comparison-results.md).

## Scope and results

The packet contains **56 posts and 20 explicit pair controls**. There are 53
static images, two missing images and one published animated image. Image
comparison considers 1,540 possible pairs, of which 1,378 have two static images.
The baseline and broader image rankings both use this packet and the same
top-five-per-pool cap. Original full-audit retrieval is recorded separately;
packet rankings are not a rerun of the full image corpus.

The semantic comparison retains the original **2,634-record text pool**, with
52 packet queries that have text. It substitutes 17 model-supported,
assistant-inspected explanations from #16, including both members of the missed
copy. These are development judgments, not human gold. The other 11 cases in
#16 are excluded from replacement because of unresolved errors, meaning/support
concerns or the absence of an answer. The 0.65 threshold, top-five cap, encoder
revision and all other text slots are unchanged.

| Measure | Baseline | Broader image / supported text |
| --- | ---: | ---: |
| Retrieved image pairs within packet | 12 | 13 |
| Selected copy/recorded-family controls found by image or MiniLM | 12/13 | 13/13 |
| Recorded historical families found by combined methods | 3/3 | 3/3 |
| Known same-template/topic false-match controls still retrieved | 4/4 | 4/4 |
| Semantic pairs from packet queries against full pool | 52 | 46 |
| Newly retrieved semantic pairs | — | One: the missed copy |
| Lost semantic pairs | — | Seven, inspected separately |

The 13 copy/family controls comprise three recorded families and ten copy
controls, including the newly added bordered pair. The four distinct-joke
controls remain false **retrieval candidates**, never automatic duplicate
exclusions. One different-presentation family-policy question and two
missing-image controls remain unresolved. The missing square-root image retains
its original TF-IDF candidate link even though the MiniLM arm does not retrieve
it. No match or failed image comparison makes a missing/animated image assessed.

## The bordered pair

`1ue5z6v` has the broad nonuniform borders; `1uczut7` has the unbordered image.
The baseline uniform trim missed it, with prior full-image distances 28/23.
The new aspect window matches the full 1080×1920 image against coordinates
`[158, 0, 561, 718]` in the 718×718 bordered image. This retains 56.1% of that
source's area and yields **dHash 1, aHash 1, mean RGB difference 5.2239**.
Thresholds were not loosened: hashes remain bounded by eight and the new
window route additionally requires mean difference at most 18.

Full-image inspection confirms the same photograph, children, caption and joke;
the discarded regions are borders. This independent inspection is why it is a
copy finding. The algorithm correctly leaves the crop result a candidate.
A near-perfect crop can otherwise discard text that changes the joke, as covered
by the regression test.

Comment-based MiniLM similarity was **0.511483**. The two supported explanations
give **0.755075**, and the pair survives full-pool top-five retrieval. This is a
useful demonstrated gain from explaining the joke instead of comparing partial
comment samples. It is one pair, not a recall estimate.

Both posts are unpublished fresh candidates. If later selecting a representative,
the unbordered `1uczut7` is the stronger image candidate: its 1080×1920 asset
contains substantially more detail than the embedded 403×718 region. Answer and
evidence quality must also be considered. No representative is selected here,
and both original automatic accepts remain intact.

## False matches, lost links and routing

The two template controls remain distinct: the three-panel SCP/routine and
sociology memes use different references, while the Family Guy pair asks
different questions about horses and energy drinks. The DiCaprio and dinosaur
topic matches likewise remain distinct jokes. Existing image hashes and semantic
scores still retrieve these pairs; the experiment does not claim to have made
the scores an exclusion rule.

The seven semantic links removed by replacing old text come from the repaired
Harry Potter and Freddie Mercury answers. Inspection of all seven target images
found six different jokes and **one plausible family link worth retaining**:
the Magic Johnson group photograph (`1ilz9mq`) also uses a day/night-of-infection
insinuation. It is a different photograph and celebrity reference, not a copy,
but losing that possible family relationship is relevant to split/exposure
accounting. Its similarity falls from 0.661578 to 0.493527. Clearer answers do not
monotonically improve semantic family retrieval.

The union of the two semantic arms has 53 pairs and preserves all seven old
links while adding the bordered copy. This is the recommended evidence-retention
route, not permission to exclude 53 items. Of the revised arm's 46 links, 11 are
explicit controls and **35 other links remain unadjudicated**. The lost-link
inspection was a deterministic follow-up on seven observed changes, not a new
held-out test or population precision estimate.

Published membership remains separate: all three recorded historical families
contain a published member; two of the six earlier fresh–archive visual-copy
controls also match a published item. Other archived counterparts can be outside
the release. An unpublished counterpart is not automatically redundancy with a
published benchmark item, and duplication is not intrinsic answer/suitability
failure. Missing-image links and the base-notation family-policy question still
need resolution before keeper or split decisions.

## Next decision and verification

The targeted retrieval hypothesis succeeds on this packet. Carry the additional
image windows and both semantic evidence views into a future versioned admission
integration, with the copy/family adjudication step intact. Preserve the bordered
pair as one family for future split accounting; investigate the Magic Johnson/
Freddie relationship before separating those examples across evaluation splits.
All inspected controls and #16 cases remain development-exposed. Historical split
violations reported in the original audit are unchanged.

No paid duplicate follow-up is needed for this result. A separate unseen local
retrieval check would be useful before claiming general recall; broader automatic
backfill still depends on the unresolved answer-check weaknesses in #16 and a
new decision in #9. Do not compensate with looser similarity cutoffs or tighter
suitability exclusions.

Local artifacts: `data/backfill/duplicate-comparison-v1` contains frozen inputs,
assets, parameters, both vector views and results. Separate
`duplicate-comparison-analysis-v1` contains explicit control dispositions, the
bordered-copy inspection, seven lost-link inspections and aggregate counts.
All raw images and corpus material remain local. The shared preservation check
confirmed **10,649 prior files byte-identical**, including frozen runs, corpus
database, human feedback and the unrelated app/test edits. All **442 tests pass**
across sandbox-compatible tests and the separately executed localhost test.
