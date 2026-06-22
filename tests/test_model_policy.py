from basedbench.model_policy import is_active_summary_model


def test_active_summary_models_hide_retired_opus_47():
    assert not is_active_summary_model("claude-opus-4-7")
    assert is_active_summary_model("claude-opus-4-8")
    assert is_active_summary_model("gpt-5.5")
    assert is_active_summary_model("x-ai/grok-4.3")
