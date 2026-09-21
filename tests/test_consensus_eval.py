"""Legacy Boolean results must not imply semantic answer correctness."""

from io import StringIO
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from rich.console import Console

from basedbench.db import queries
from basedbench.pipeline import consensus_eval
from tests.conftest import sample_post


def test_seeding_never_uses_flagged_bad_text_as_gold_or_overwrites_adjudication(db):
    for pid in ("bad", "reviewed"):
        queries.insert_meme(db, sample_post(pid))
        queries.flag_consensus_regression(db, pid, "partial", "Known faulty explanation")
    queries.upsert_consensus_eval_item(db, "reviewed", "true_no_consensus", False, source="manual_review")
    assert queries.seed_consensus_eval_from_regressions(db) == 1
    items = {i.post_id: i for i in queries.list_consensus_eval_items(db)}
    assert items["bad"].expected_explanation is None
    assert not items["reviewed"].expected_has_consensus
    assert items["reviewed"].source == "manual_review"


@pytest.mark.asyncio
async def test_transport_error_cannot_pass_a_no_consensus_control(db, monkeypatch):
    queries.insert_meme(db, sample_post("broken"))
    queries.upsert_consensus_eval_item(db, "broken", "true_no_consensus", False, source="test")
    detector = SimpleNamespace(prompt_id="p", detect_consensus=AsyncMock(return_value=(
        SimpleNamespace(has_consensus=False, selected_explanation=None, confidence=0,
                        agreeing_comment_ids=[], reasoning="Transport failed"),
        SimpleNamespace(error="Transport failed", latency_ms=12))))
    monkeypatch.setattr(consensus_eval, "ConsensusDetector", lambda *a, **k: detector)
    monkeypatch.setattr(queries, "insert_llm_call", lambda *a: None)
    output = StringIO()
    run_id = await consensus_eval.run(db, SimpleNamespace(consensus_model="fake"), console=Console(file=output))
    result = queries.list_consensus_eval_results(db, run_id)[0]
    assert not result.passed and result.error == "Transport failed"
    assert "NOT EVALUATED" in output.getvalue()
    assert "Boolean matches: 0/1" in output.getvalue()
