"""Two-tab read-only BasedBench explorer for Hugging Face Spaces."""

from __future__ import annotations

import html
import secrets
from typing import Any

import gradio as gr

try:
    from data import BenchmarkData, load_from_hub
except ImportError:
    from space.data import BenchmarkData, load_from_hub


DATA: BenchmarkData = load_from_hub()


def _escaped(value: Any) -> str:
    return html.escape(str(value or ""))


def _quoted(value: Any) -> str:
    lines = _escaped(value).splitlines() or [""]
    return "\n".join(f"> {line}" for line in lines)


def _prediction_markdown(post_id: str, selected_model: str) -> str:
    blocks: list[str] = []
    for prediction in DATA.predictions(post_id, selected_model):
        prediction_id = int(prediction["prediction_id"])
        judgments = DATA.judgments(prediction_id)
        correct = sum(row.get("verdict") == "correct" for row in judgments)
        incorrect = sum(row.get("verdict") == "incorrect" for row in judgments)
        consensus = str(prediction.get("consensus_verdict") or "no consensus")
        judge_lines = []
        for judgment in judgments:
            line = (
                f"**{_escaped(judgment['judge_model'])}:** "
                f"{_escaped(judgment['verdict'])}"
            )
            if judgment.get("reasoning"):
                line += "\n\n" + _quoted(judgment["reasoning"])
            judge_lines.append(line)
        historical = DATA.historical_judgment_counts.get(prediction_id, 0)
        history_note = (
            f"\n\n_{historical} superseded judgment record"
            f"{'s' if historical != 1 else ''} retained in the dataset._"
            if historical
            else ""
        )
        judge_details = "\n\n".join(judge_lines) or "_No judge records._"
        blocks.append(
            f"### `{_escaped(prediction['model_id'])}`\n\n"
            f"**Consensus: {consensus}** · {correct} correct / {incorrect} incorrect\n\n"
            f"<details><summary>Model prediction</summary>\n\n"
            f"{_escaped(prediction['prediction'])}\n\n</details>\n\n"
            f"<details><summary>Judge details</summary>\n\n"
            f"{judge_details}"
            f"{history_note}\n\n</details>"
        )
    return "\n\n---\n\n".join(blocks) or "_No prediction matches this filter._"


def _empty_render(position: str = "0 / 0") -> tuple[Any, ...]:
    return (
        0,
        position,
        gr.update(value=None, visible=False),
        gr.update(value="_No memes match these filters._", visible=True),
        gr.update(value="", visible=False),
        gr.update(value="", visible=False),
    )


def _render(
    ids: list[str], idx: int, hide_ground_truth: bool, selected_model: str
) -> tuple[Any, ...]:
    if not ids:
        return _empty_render()
    bounded = max(0, min(int(idx), len(ids) - 1))
    post_id = ids[bounded]
    meme = DATA.meme(post_id)
    info = (
        f"## {_escaped(meme['title'])}\n\n"
        f"`r/{_escaped(meme['subreddit'])}` · `{_escaped(post_id)}`"
    )
    return (
        bounded,
        f"{bounded + 1} / {len(ids)}",
        gr.update(value=DATA.image(post_id), visible=True),
        gr.update(value=info, visible=True),
        gr.update(
            value=("Ground truth hidden." if hide_ground_truth else meme["ground_truth"]),
            visible=True,
        ),
        gr.update(
            value=_prediction_markdown(post_id, selected_model),
            visible=True,
        ),
    )


def apply_filters(
    search: str, model_id: str, outcome: str, hide_ground_truth: bool
) -> tuple[Any, ...]:
    ids = DATA.filtered_ids(search, model_id, outcome)
    return (ids, *_render(ids, 0, hide_ground_truth, model_id))


def step_item(
    ids: list[str], idx: int, delta: int, hide_ground_truth: bool, model_id: str
) -> tuple[Any, ...]:
    return _render(ids, int(idx) + delta, hide_ground_truth, model_id)


def random_item(
    ids: list[str], hide_ground_truth: bool, model_id: str
) -> tuple[Any, ...]:
    if not ids:
        return _empty_render()
    return _render(ids, secrets.randbelow(len(ids)), hide_ground_truth, model_id)


def rerender_item(
    ids: list[str], idx: int, hide_ground_truth: bool, model_id: str
) -> tuple[Any, ...]:
    return _render(ids, idx, hide_ground_truth, model_id)


CSS = """
.gradio-container {
    max-width: 1180px !important;
}
.app-header {
    align-items: baseline !important;
    margin-bottom: 4px !important;
}
.app-title h1 {
    margin: 0 !important;
    line-height: 1.1 !important;
}
.app-subtitle {
    color: var(--body-text-color-subdued) !important;
    font-size: 14px !important;
}
.inspect-toolbar {
    gap: 8px !important;
    align-items: center !important;
    flex-wrap: wrap !important;
    margin-bottom: 8px !important;
}
.inspect-toolbar .block {
    min-width: 0 !important;
}
.nav-button {
    min-width: 82px !important;
    max-width: 96px !important;
}
.random-button {
    min-width: 78px !important;
    max-width: 88px !important;
}
.inspect-position {
    min-width: 72px !important;
    max-width: 84px !important;
    text-align: center !important;
    color: var(--body-text-color-subdued) !important;
}
.inspect-position p {
    margin: 0 !important;
}
.meme-image img {
    width: 100% !important;
    max-height: 72vh !important;
    object-fit: contain !important;
    object-position: top center !important;
}
.prediction-panel details {
    border-top: 1px solid var(--border-color-primary);
    padding: 8px 0;
}
.prediction-panel summary {
    cursor: pointer;
    font-weight: 600;
}
.leaderboard-table {
    min-height: 250px !important;
}
@media (max-width: 700px) {
    .gradio-container {
        padding-left: 10px !important;
        padding-right: 10px !important;
    }
    .inspect-toolbar {
        gap: 6px !important;
    }
    .filter-toolbar .form {
        display: grid !important;
        grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) !important;
        gap: 6px !important;
        width: 100% !important;
    }
    .filter-toolbar .form > .block {
        flex: none !important;
        min-width: 0 !important;
        max-width: none !important;
        width: 100% !important;
    }
    .filter-toolbar .form > .block:first-child,
    .filter-toolbar .form > .block:last-child {
        grid-column: 1 / -1 !important;
    }
    .nav-button,
    .random-button {
        min-width: 70px !important;
        max-width: none !important;
        flex: 1 1 auto !important;
    }
    .meme-image img {
        max-height: none !important;
    }
}
"""


def build_app() -> gr.Blocks:
    model_choices = [("All models", "all")] + [(model, model) for model in DATA.models]
    with gr.Blocks(title="basedBench") as demo:
        with gr.Row(elem_classes="app-header"):
            gr.HTML(
                "<div class='app-title'><h1>basedBench</h1>"
                "<div class='app-subtitle'>Read-only benchmark explorer</div></div>"
            )

        with gr.Tabs(selected="inspect"):
            with gr.Tab("Inspect", id="inspect"):
                ids_state = gr.State([])
                idx_state = gr.State(0)

                with gr.Row(elem_classes=["inspect-toolbar", "filter-toolbar"]):
                    search = gr.Textbox(
                        placeholder="Search title, source, ID, or ground truth",
                        label="Search",
                        show_label=False,
                        min_width=260,
                        scale=3,
                    )
                    model = gr.Dropdown(
                        choices=model_choices,
                        value="all",
                        label="Model",
                        show_label=False,
                        min_width=210,
                        scale=2,
                    )
                    outcome = gr.Dropdown(
                        choices=[
                            ("Any outcome", "all"),
                            ("All got it right", "all_correct"),
                            ("All got it wrong", "all_incorrect"),
                            ("Mixed", "mixed"),
                        ],
                        value="all",
                        label="Outcome",
                        show_label=False,
                        min_width=180,
                        scale=2,
                    )
                    hide_ground_truth = gr.Checkbox(
                        label="Hide ground truth",
                        value=False,
                        min_width=150,
                        scale=1,
                    )

                with gr.Row(elem_classes="inspect-toolbar"):
                    previous = gr.Button("Previous", elem_classes="nav-button")
                    random_button = gr.Button("Random", elem_classes="random-button")
                    position = gr.Markdown("0 / 0", elem_classes="inspect-position")
                    next_button = gr.Button("Next", elem_classes="nav-button")

                with gr.Row(equal_height=False):
                    with gr.Column(scale=1, min_width=320):
                        image = gr.Image(
                            label="Meme",
                            type="pil",
                            interactive=False,
                            elem_classes="meme-image",
                        )
                    with gr.Column(scale=1, min_width=320):
                        info = gr.Markdown()
                        ground_truth = gr.Textbox(
                            label="Ground Truth",
                            lines=5,
                            interactive=False,
                        )
                        predictions = gr.Markdown(elem_classes="prediction-panel")

                render_outputs = [
                    idx_state,
                    position,
                    image,
                    info,
                    ground_truth,
                    predictions,
                ]
                filter_outputs = [ids_state, *render_outputs]
                filter_inputs = [search, model, outcome, hide_ground_truth]

                demo.load(apply_filters, inputs=filter_inputs, outputs=filter_outputs)
                search.submit(apply_filters, inputs=filter_inputs, outputs=filter_outputs)
                model.change(apply_filters, inputs=filter_inputs, outputs=filter_outputs)
                outcome.change(
                    apply_filters,
                    inputs=filter_inputs,
                    outputs=filter_outputs,
                )
                previous.click(
                    lambda ids, idx, hidden, selected: step_item(
                        ids, idx, -1, hidden, selected
                    ),
                    inputs=[ids_state, idx_state, hide_ground_truth, model],
                    outputs=render_outputs,
                )
                next_button.click(
                    lambda ids, idx, hidden, selected: step_item(
                        ids, idx, 1, hidden, selected
                    ),
                    inputs=[ids_state, idx_state, hide_ground_truth, model],
                    outputs=render_outputs,
                )
                random_button.click(
                    random_item,
                    inputs=[ids_state, hide_ground_truth, model],
                    outputs=render_outputs,
                )
                hide_ground_truth.change(
                    rerender_item,
                    inputs=[ids_state, idx_state, hide_ground_truth, model],
                    outputs=render_outputs,
                )

            with gr.Tab("Leaderboard"):
                gr.Markdown(
                    f"**Snapshot:** `{DATA.snapshot_id}` · "
                    f"**Memes:** {len(DATA.post_ids):,} · "
                    f"**Predictions:** {len(DATA.predictions_by_id):,}"
                )
                gr.Dataframe(
                    value=DATA.leaderboard_rows(),
                    headers=[
                        "Model",
                        "Correct",
                        "Incorrect",
                        "Total",
                        "Accuracy",
                        "Judge agreement",
                    ],
                    datatype=["str", "number", "number", "number", "str", "str"],
                    interactive=False,
                    wrap=True,
                    elem_classes="leaderboard-table",
                )
                gr.Markdown(
                    "Consensus requires at least two matching judge votes. "
                    "Judge agreement is the stricter rate where all latest votes match."
                )

    return demo


demo = build_app()


if __name__ == "__main__":
    demo.launch(css=CSS)
