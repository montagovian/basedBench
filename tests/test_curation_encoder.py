"""Ensure long evidence remains visible and frozen encoding uses no labels."""

import pytest

from basedbench.pipeline.curation_encoder import encode_evidence, token_chunks


def test_chunks_preserve_complete_token_sequence():
    tokens = list(range(901))
    chunks = token_chunks(tokens, 254)
    assert [token for piece in chunks for token in piece] == tokens
    assert max(map(len, chunks)) == 254
    assert len(chunks[-1]) == 139
    assert token_chunks([], 254) == [[]]
    with pytest.raises(ValueError):
        token_chunks(tokens, 0)


def test_long_tail_changes_features_and_batching_does_not_drop_text():
    torch = pytest.importorskip("torch")
    np = pytest.importorskip("numpy")

    class Tokenizer:
        cls_token_id, sep_token_id, pad_token_id = 101, 102, 0

        def encode(self, text, **kwargs):
            assert kwargs == {"add_special_tokens": False, "truncation": False}
            return [ord(char) for char in text]

    class Encoder:
        tokenizer = Tokenizer()
        max_seq_length = 6  # Four actual tokens, forcing many chunks.
        device = "cpu"

        def eval(self):
            self.evaluating = True

        def __call__(self, features):
            assert self.evaluating and not torch.is_grad_enabled()
            mask = features["attention_mask"]
            assert features["input_ids"].shape[1] <= self.max_seq_length
            # A deterministic stand-in whose result depends on all visible tokens.
            sums = (features["input_ids"] * mask).sum(dim=1).float()
            return {"sentence_embedding": torch.stack((sums, mask.sum(dim=1).float()), dim=1)}

    inputs = [{"explanation": "same explanation", "comment_evidence": "first part " + "a" * 40},
              {"explanation": "same explanation", "comment_evidence": "first part " + "z" * 40}]
    features, packing = encode_evidence(inputs, Encoder(), batch_size=3)
    again, _ = encode_evidence(inputs, Encoder(), batch_size=7)
    np.testing.assert_allclose(features, again)
    np.testing.assert_allclose(features[0, :2], features[1, :2])
    assert not np.allclose(features[0, 2:], features[1, 2:])
    assert packing[0]["comment_evidence"] == {"tokens": 51, "chunks": 13, "omitted_tokens": 0}
