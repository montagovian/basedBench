"""Offline duplicate integration preserves candidate status and source provenance."""
import copy
import json

import pytest

from basedbench.pipeline import admission_v2 as v2, admission_pilot as pilot
from basedbench.pipeline.curation_corpus import digest, file_hash, write_json
from tests.test_admission_pilot import source, freeze, client, content_pass, draft, check, suitability


def records():
    return [{'post_id': p, 'pool': 'legacy' if p == 'p2' else 'fresh', 'in_release': p == 'p2'} for p in ['p1', 'p2', 'p3']]


def test_crop_and_topic_scores_cannot_confirm_or_remove_old_evidence():
    old = [{'left': 'p1', 'right': 'p2', 'status': 'candidate', 'evidence': [{'method': 'tfidf', 'score': .8}],
            'scope': 'fresh', 'release_members': ['p2']}]
    snapshot = copy.deepcopy(old)
    additions = [{'left': 'p1', 'right': 'p2', 'status': 'confirmed',
                  'evidence': {'method': 'aspect_window', 'pixel_difference': 0}},
                 {'left': 'p1', 'right': 'p3', 'evidence': {'method': 'minilm_supported_answers', 'score': .99}}]
    edges = v2.merge_edges(old, additions, records())
    assert old == snapshot and all(e['status'] == 'candidate' for e in edges)
    assert edges[0]['evidence'][0] == old[0]['evidence'][0]
    assert edges[0]['release_members'] == ['p2'] and edges[1]['release_members'] == []
    assert pilot.duplicate_route(edges)['decision'] == 'defer'
    additions[0]['evidence']['method'] = 'exact_pixels'
    with pytest.raises(ValueError, match='cannot invent'):
        v2.merge_edges(old, additions, records())


def test_confirmed_identity_and_unpublished_routing_survive():
    edge = {'left': 'p1', 'right': 'p2', 'status': 'confirmed', 'evidence': [{'method': 'exact_bytes'}],
            'scope': 'fresh', 'release_members': ['p2']}
    added = {'left': 'p1', 'right': 'p2', 'evidence': {'method': 'minilm_supported_answers', 'score': .9}}
    merged = v2.merge_edges([edge], [added], records())
    assert merged[0]['status'] == 'confirmed' and pilot.duplicate_route(merged)['decision'] == 'fail'
    merged[0]['release_members'] = []
    assert pilot.duplicate_route(merged)['reason_codes'] == ['copy_outside_release']


@pytest.mark.asyncio
async def test_offline_replay_reuses_exact_requests_and_new_link_blocks_them(tmp_path, source):
    prior, plan = freeze(tmp_path, source)
    api = client(content_pass(), draft(), check(), suitability())
    original = await pilot.run(prior, budget_usd=.25, client=api)
    case = json.loads((prior / 'cases.json').read_text())[0]
    ledger = []
    outcome = await v2.replay_case(case, prior, plan, ledger)
    assert outcome['decision'] == original['outcomes'][0]['decision'] == 'accept'
    assert len(ledger) == 4 and api.responses.create.call_count == 4
    case['duplicate'] = pilot.duplicate_route(v2.merge_edges([], [
        {'left': 'p1', 'right': 'p3', 'evidence': {'method': 'aspect_window', 'pixel_difference': 0}}], records()))
    blocked_ledger = []
    outcome = await v2.replay_case(case, prior, plan, blocked_ledger)
    assert outcome['decision'] == 'defer' and not blocked_ledger
    assert outcome['human'] == source['human'] and not outcome['human_validated']


@pytest.mark.asyncio
async def test_missing_call_defers_and_changed_request_cannot_be_reused(tmp_path, source):
    prior, plan = freeze(tmp_path, source)
    case = json.loads((prior / 'cases.json').read_text())[0]
    outcome = await v2.replay_case(case, prior, plan, [])
    assert outcome['decision'] == 'defer' and outcome['technical_status'] == 'error'
    await pilot.run(prior, budget_usd=.25, client=client(content_pass(), draft(), check(), suitability()))
    request = prior / 'requests' / 'p1.generated_check.json'
    value = json.loads(request.read_text())
    value['instructions'] = 'A changed prompt'
    write_json(request, value)
    with pytest.raises(ValueError, match='request identity'):
        await v2.replay_case(case, prior, plan, [])


@pytest.mark.asyncio
async def test_human_ready_disagreement_remains_guarded(tmp_path, source):
    source['input']['explanation'] = 'Human-ready answer.'
    source['human'] = {'components': {'ground_truth': 'pass'}}
    prior, plan = freeze(tmp_path, source)
    await pilot.run(prior, budget_usd=.25, client=client(content_pass(), check('fail')))
    case = json.loads((prior / 'cases.json').read_text())[0]
    outcome = await v2.replay_case(case, prior, plan, [])
    assert outcome['reason_codes'] == ['answer:human_ready_answer_challenged']
    assert outcome['human'] == source['human']


@pytest.mark.asyncio
async def test_versioned_report_is_repeatable_and_frozen(tmp_path, source):
    prior, source_plan = freeze(tmp_path, source)
    await pilot.run(prior, budget_usd=.25, client=client(content_pass(), draft(), check(), suitability()))
    output = tmp_path / 'v2'
    output.mkdir()
    cases = json.loads((prior / 'cases.json').read_text())
    cases[0]['duplicate_coverage'] = {k: False for k in
        ['expanded_image_packet_member', 'expanded_image_assessed', 'semantic_comparison_query']}
    write_json(output / 'cases.json', cases)
    plan = {'version': v2.VERSION, 'code_hashes': v2.code_hashes(), 'source_directory': str(prior),
        'source_files': {str(p): file_hash(p) for p in prior.rglob('*') if p.is_file() and p.name != 'run.lock'},
        'files': {'cases.json': file_hash(output / 'cases.json')}, 'component_versions': source_plan['component_versions'],
        'retrieval_scope': {}, 'limitations': []}
    plan['experiment_id'] = digest(plan)
    write_json(output / 'plan.json', plan)
    report = await v2.run(output)
    before = {str(p): file_hash(p) for p in output.rglob('*') if p.is_file() and p.name != 'run.lock'}
    assert report == await v2.run(output)
    assert report['changes'] == [] and report['paid_model_calls'] == 0
    assert before == {str(p): file_hash(p) for p in output.rglob('*') if p.is_file() and p.name != 'run.lock'}
    (output / 'report.json').write_text('{}')
    with pytest.raises(ValueError, match='Frozen input'):
        await v2.run(output)
