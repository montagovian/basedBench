"""A pinned, frozen MiniLM representation with a small admission classifier."""

from __future__ import annotations

import importlib.metadata
import platform
import time
from pathlib import Path

from basedbench.pipeline.curation_corpus import file_hash, load_corpus
from basedbench.pipeline.curation_eval import decide, write_evaluation
from basedbench.pipeline.curation_history import history_status

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
MODEL_REVISION = "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"
FEATURE_VERSION = "minilm-two-fields-token-weighted-chunks-v1"
FIELDS = ("explanation", "comment_evidence")


def token_chunks(tokens: list[int], capacity: int) -> list[list[int]]:
    """Cover every token exactly once, including text beyond the first window."""
    if capacity < 1:
        raise ValueError("Token capacity must be positive")
    return [tokens[i:i + capacity] for i in range(0, len(tokens), capacity)] or [[]]


def encode_evidence(inputs: list[dict], encoder, *, batch_size: int = 32) -> tuple[object, list[dict]]:
    """Encode both complete fields separately, then concatenate their vectors.

    MiniLM uses BERT's [CLS] content [SEP] format. Supplying token IDs directly
    avoids a decode/re-encode step that could change boundaries or drop tokens.
    Within each field, average normalized chunk vectors by content-token count,
    then normalize the field vector. Neither field is overwhelmed by the other.
    """
    import numpy as np
    import torch

    if batch_size < 1:
        raise ValueError("Batch size must be positive")
    tokenizer = encoder.tokenizer
    if any(value is None for value in (tokenizer.cls_token_id, tokenizer.sep_token_id, tokenizer.pad_token_id)):
        raise ValueError("This packing policy requires BERT CLS/SEP/PAD tokens")
    capacity = int(encoder.max_seq_length) - 2
    chunks, owners, weights, packing = [], [], [], []
    for owner, item in enumerate(inputs):
        record = {}
        for field_index, field in enumerate(FIELDS):
            tokens = tokenizer.encode(item[field], add_special_tokens=False, truncation=False)
            pieces = token_chunks(tokens, capacity)
            record[field] = {"tokens": len(tokens), "chunks": len(pieces), "omitted_tokens": 0}
            for piece in pieces:
                chunks.append([tokenizer.cls_token_id, *piece, tokenizer.sep_token_id])
                owners.append((owner, field_index))
                weights.append(max(1, len(piece)))
        packing.append(record)
    if not chunks:
        raise ValueError("No model inputs to encode")
    vectors = []
    encoder.eval()
    # No gradients, fitting, labels, or test examples enter the encoder.
    with torch.inference_mode():
        for start in range(0, len(chunks), batch_size):
            batch = chunks[start:start + batch_size]
            length = max(len(chunk) for chunk in batch)
            ids = [chunk + [tokenizer.pad_token_id] * (length - len(chunk)) for chunk in batch]
            masks = [[1] * len(chunk) + [0] * (length - len(chunk)) for chunk in batch]
            features = {
                "input_ids": torch.tensor(ids, dtype=torch.long, device=encoder.device),
                "attention_mask": torch.tensor(masks, dtype=torch.long, device=encoder.device),
                "token_type_ids": torch.zeros((len(batch), length), dtype=torch.long, device=encoder.device),
            }
            result = encoder(features)["sentence_embedding"]
            result = torch.nn.functional.normalize(result, p=2, dim=1)
            vectors.append(result.cpu().numpy())
    chunks_encoded = np.concatenate(vectors, axis=0)
    pooled = np.zeros((len(inputs), len(FIELDS), chunks_encoded.shape[1]), dtype=np.float64)
    for vector, (owner, field_index), weight in zip(chunks_encoded, owners, weights, strict=True):
        pooled[owner, field_index] += vector * weight
    pooled /= np.maximum(np.linalg.norm(pooled, axis=2, keepdims=True), 1e-12)
    if not np.isfinite(pooled).all():
        raise ValueError("Encoder produced non-finite features")
    return pooled.reshape(len(inputs), -1).astype(np.float32), packing


def run_encoder(
    corpus: Path, output: Path, *, history_audit: Path,
    model_cache: Path = Path("data/curation/models"), batch_size: int = 32,
    accept_threshold: float = 0.9, reject_threshold: float = 0.1,
) -> dict:
    """Compare a frozen encoder on the already-locked development/calibration split."""
    decide(None, accept_threshold, reject_threshold)
    if output.exists():
        raise FileExistsError(f"Refusing to replace encoder run: {output}")
    try:
        import numpy as np
        import torch
        from sentence_transformers import SentenceTransformer
        from sklearn.linear_model import LogisticRegression
    except ImportError as exc:
        raise RuntimeError("Install encoder dependencies with: uv sync --extra encoder --extra curation") from exc
    manifest, rows = load_corpus(corpus)
    exposure = history_status(history_audit, manifest, rows)
    train = [r for r in rows if r["split"] == "development"]
    evaluation = [r for r in rows if r["split"] == "calibration"]
    if {r["label"] for r in train} != {"accept", "reject"} or not evaluation:
        raise ValueError("Need both development labels and a nonempty calibration split")
    selected = train + evaluation
    torch.set_num_threads(4)
    torch.manual_seed(0)
    started = time.perf_counter()
    encoder = SentenceTransformer(
        MODEL_NAME, revision=MODEL_REVISION, cache_folder=str(model_cache), device="cpu",
        token=False, trust_remote_code=False, model_kwargs={"use_safetensors": True},
    )
    if encoder[0].auto_model.config.model_type != "bert" or encoder.max_seq_length != 256:
        raise ValueError("Checkpoint is incompatible with the pinned BERT packing policy")
    load_ms = (time.perf_counter() - started) * 1000
    started = time.perf_counter()
    features, packing = encode_evidence([r["input"] for r in selected], encoder, batch_size=batch_size)
    encoding_ms = (time.perf_counter() - started) * 1000
    packing = [{"post_id": row["post_id"], "input_sha256": row["input_sha256"], "split": row["split"], **record}
               for row, record in zip(selected, packing, strict=True)]
    parameters = {"C": 1.0, "class_weight": "balanced", "max_iter": 1000, "random_state": 0}
    classifier = LogisticRegression(**parameters)
    started = time.perf_counter()
    classifier.fit(features[:len(train)], [int(r["label"] == "accept") for r in train])
    train_ms = (time.perf_counter() - started) * 1000
    started = time.perf_counter()
    scores = classifier.predict_proba(features[len(train):])[:, list(classifier.classes_).index(1)]
    prediction_ms = (time.perf_counter() - started) * 1000
    versions = {name: importlib.metadata.version(name) for name in
                ("sentence-transformers", "torch", "transformers", "numpy", "scipy", "scikit-learn", "joblib")}
    versions.update(python=platform.python_version(), encoder_source_sha256=file_hash(Path(__file__)))
    return write_evaluation(
        manifest, train, evaluation, output, model=classifier, scores=scores.tolist(),
        model_name="minilm-frozen-logistic-v1", feature_version=FEATURE_VERSION,
        parameters=parameters, versions=versions, exposure=exposure,
        timing_ms={"encoder_load": load_ms, "encoding": encoding_ms, "training": train_ms, "calibration_prediction": prediction_ms},
        accept_threshold=accept_threshold, reject_threshold=reject_threshold,
        feature_matrix=features, packing=packing,
        details={"checkpoint": MODEL_NAME, "revision": MODEL_REVISION, "device": "cpu", "threads": 4,
                 "batch_size": batch_size, "max_sequence_length": 256, "fields": list(FIELDS),
                 "feature_dimension": int(features.shape[1]), "encoder_frozen": True,
                 "encoder_pretraining_overlap": "unknown; reserved means unused by these local experiments only",
                 "total_content_tokens": sum(record[field]["tokens"] for record in packing for field in FIELDS),
                 "total_chunks": sum(record[field]["chunks"] for record in packing for field in FIELDS),
                 "omitted_tokens": 0},
        limitations=[
            "The encoder reads explanation/comment text, not images. Its pretrained representations remain fixed.",
            "Long fields are read in separate pieces and averaged. This preserves text coverage but loses relationships across piece boundaries.",
            "This tests one small encoder and one fixed classifier configuration, not the full potential of encoders.",
            "Overlap with the encoder's pretraining data is unknown.",
        ],
    )
