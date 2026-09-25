from basedbench.comment_selection_feedback import ARMS, evaluate


def _inventory():
    return {
        "schema_version": "comment-selection-feedback-anchors-v1",
        "sources": {"events.jsonl": "0" * 64},
        "anchors": [
            {"case_id": "case-a", "family_id": "family-a", "comment_id": "wanted",
             "kind": "positive_retention", "event_id": "event-1", "quote": "great",
             "constraints": {"must_be_in": ["retained_ids"]}},
            {"case_id": "case-a", "family_id": "family-a", "comment_id": "noise",
             "kind": "negative_exclusion", "event_id": "event-2", "quote": "false positive",
             "constraints": {"must_not_be_in": ["retained_ids", "selected_ids"]}},
            {"case_id": "case-a", "family_id": "family-a", "comment_id": "pointer",
             "kind": "ordering_negative", "event_id": "event-3", "quote": "incomplete",
             "constraints": {"must_not_be_first": True}},
            {"case_id": "case-a", "family_id": "family-a", "comment_id": None,
             "kind": "ambiguous_exclusion", "event_id": "event-4", "quote": "only this",
             "constraints": {}},
        ],
    }


def _outcomes():
    arms = {}
    for arm in ARMS:
        arms[arm] = {"status": "completed",
                     "selected_ids": ["pointer", "wanted", "noise"],
                     "retained_ids": ["pointer", "wanted", "noise", "other"],
                     "excluded_ids": []}
    arms["pointwise"] = {"status": "completed",
                         "selected_ids": ["wanted", "other", "pointer"],
                         "retained_ids": ["wanted", "other", "pointer"],
                         "excluded_ids": ["noise"]}
    return [{"case_id": "case-a", "family_id": "family-a", "status": "completed",
             "errors": {}, "scores": {}, "lists": arms}]


def test_reports_separate_membership_top_three_exclusion_and_order():
    result = evaluate(_inventory(), _outcomes())
    baseline = result["arms"]["baseline"]
    assert baseline["positive_retention_met"] == 1
    assert baseline["positive_top3_met"] == 1
    assert baseline["negative_top3_met"] == 0
    assert baseline["negative_exclusion_met"] == 0
    assert baseline["ordering_met"] == 0
    pointwise = result["arms"]["pointwise"]
    assert pointwise["positive_retention_met"] == 1
    assert pointwise["negative_top3_met"] == 1
    assert pointwise["negative_exclusion_met"] == 1
    assert pointwise["ordering_met"] == 1
    assert result["provenance"]["ambiguous_anchor_count"] == 1
    assert "accuracy" not in result


def test_unavailable_outcome_is_not_counted_as_a_miss():
    row = _outcomes()[0]
    row["status"] = "abstained"
    for arm in ("pointwise", "pairwise"):
        row["lists"][arm] = {"status": "unavailable"}
    result = evaluate(_inventory(), [row])
    baseline = result["arms"]["baseline"]
    assert baseline["unavailable_cases"] == 0
    assert baseline["positive_retention_met"] == 1
    assert baseline["failures"]
    for arm in ("pointwise", "pairwise"):
        counts = result["arms"][arm]
        assert counts["unavailable_cases"] == 1
        assert "positive_retention_total" not in counts
        assert counts["failures"] == []


def test_ordering_can_compare_preferred_ids_ahead_of_bad_first():
    inventory = _inventory()
    anchor = inventory["anchors"][2]
    anchor["constraints"] = {"preferred_ids": ["wanted", "other"], "badfirst_id": "pointer"}
    row = _outcomes()[0]
    row["lists"]["baseline"]["selected_ids"] = ["wanted", "other", "pointer"]
    row["lists"]["baseline"]["retained_ids"] = ["wanted", "other", "pointer", "noise"]
    counts = evaluate(inventory, [row])["arms"]["baseline"]
    assert counts["ordering_scored"] == 1
    assert counts["ordering_met"] == 1
    assert not [failure for failure in counts["failures"] if failure["check"] == "ordering"]


def test_missing_anchored_outcome_case_is_reported_without_a_miss():
    result = evaluate(_inventory(), [])
    for arm in ARMS:
        counts = result["arms"][arm]
        assert counts["missing_anchor_cases"] == ["case-a"]
        assert "positive_retention_total" not in counts
