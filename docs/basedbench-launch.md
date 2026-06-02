# BasedBench: evaluating meme and visual humor understanding in VLMs

BasedBench is a benchmark for meme and visual humor understanding in vision-language models.

The task is intentionally simple: given an internet meme or visual joke, the model must explain why it is funny. Its answer is then compared against a human explanation derived from Reddit explanation communities and validated through the benchmark pipeline.

This is not a benchmark for generating jokes, ranking memes, or deciding whether a model has a sense of humor. It evaluates whether a model can understand a meme well enough to explain it.

That task is harder than it may look. A model has to read the image, parse the text, identify the relevant visual details, recognize the joke format, catch references, and explain how those pieces work together. Many failures are not subtle. The model may misread the caption, miss the relevant object, identify the template but not the joke, or produce an explanation-shaped answer that sounds plausible but explains the wrong thing.

The point of BasedBench is to make those failures measurable.

## What the benchmark tests

Meme understanding bundles together several capabilities that are usually tested separately, if they are tested at all.

First, it tests visual understanding under realistic internet conditions. Memes are low-resolution, compressed, cropped, reposted, captioned, and often visually cluttered. Text may be small, distorted, or embedded inside a screenshot. The visual joke may depend on layout, juxtaposition, facial expression, or one small load-bearing detail. OCR is necessary, but not sufficient.

Second, it tests humor understanding. A meme can depend on irony, sarcasm, template recognition, social inference, or expectation violation. A visual pun may require the model to map an image to a word, a word to a sound, and a sound to a joke. That is not the same as object recognition, captioning, or ordinary visual question answering.

Third, it tests deep-cut knowledge. Memes often rely on references to shows, books, anime, games, streamers, internet drama, forum culture, political micro-events, or stale platform-specific joke formats. Foundation models are trained on large parts of the internet, but they do not know every factoid or subcultural reference. Different training mixtures should produce different failure modes.

This is the most direct sense in which BasedBench is "based": it rewards models for knowing the kind of weird internet material that may not matter in a clean cognitive benchmark, but does matter if the model is expected to understand what people actually post online.

## Why memes are a useful test case

Memes are useful because they are compact.

A single meme can force a model to combine vision, text, reference, tone, and joke structure. It can require both perception and background knowledge. It can expose whether the model merely describes the artifact or understands why the artifact works.

This makes meme understanding a good stress test for VLMs. It is not comprehensive, and it is not a replacement for other multimodal benchmarks. But it covers a region of model behavior that standard evaluations often miss: messy internet-native visual communication.

That region matters. People do not communicate only through clean images, well-formed questions, and explicit factual requests. They communicate through screenshots, jokes, fragments, formats, references, and shared conventions. A model that can operate in that environment needs more than OCR and object labels. It needs to explain what the artifact is doing.

## Dataset construction

BasedBench uses found labeled data.

Reddit explanation communities already contain the basic structure needed for an evaluation: a confusing meme or visual joke, a set of human explanations, and social signals about which explanations other users accept. BasedBench uses those naturally occurring explanations as candidate ground truth, then filters and validates them before using them for evaluation.

This is the methodological idea behind the benchmark. Instead of inventing examples and asking annotators to label them from scratch, BasedBench starts from places where people are already doing the labeling work because they want the answer. In that respect, it is inspired by the same broad pattern as SWE-bench: use real tasks and real resolutions from the wild, rather than a fully synthetic proxy task.

There are obvious caveats. Reddit explanations can be wrong. Consensus is not truth. Human verification still matters. LLM judges can fail. Safety and consensus filters can reject valid examples or accept bad ones. BasedBench treats those as pipeline problems to track and improve, not as details to hand-wave away.

The longer-term possibility is a more dynamic benchmark. If the consensus, safety, and judging steps become reliable enough, new examples can be drawn continuously from fresh memes and fresh human explanations. That would reduce, though not eliminate, contamination pressure. The current benchmark is not fully automated, but it points toward a benchmark factory built from found explanation work.

## What to look at

The leaderboard is useful, but the error patterns are at least as important.

A model can fail because it cannot read the text. It can fail because it cannot parse the image. It can fail because it lacks the relevant reference. It can fail because it understands all the individual pieces but not how they form a joke. These are different failures, and they imply different things about the model.

That is why the benchmark asks for explanations rather than classifications. A classification can hide the route the model took. An explanation makes the failure legible. If the model gets the joke, the answer should show how. If it does not, the answer often reveals what went missing.

BasedBench is therefore a benchmark of meme and visual humor understanding, but it is also a diagnostic tool. It probes how VLMs handle messy visual inputs, internet-specific references, joke structure, and the practical burden of knowing enough weird online material to explain what people are laughing at.

It is not the whole of intelligence. It is one thing models should be able to do if they are going to live on the internet.
