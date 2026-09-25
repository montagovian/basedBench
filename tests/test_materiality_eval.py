"""Prompt isolation, exact human overlays, bounded spending and immutable replay."""
import asyncio
import json
from pathlib import Path

import pytest

from basedbench.pipeline import materiality_eval as ev
from basedbench.pipeline.curation_corpus import digest, file_hash, write_json
from tests.test_capacity_eval import prepared as capacity_prepared, Client
from tests.test_focused_connection_eval import FakeClient


def prepared(tmp_path, monkeypatch, *, mismatched_answer=False):
    _, source, _ = capacity_prepared(tmp_path, monkeypatch)
    asyncio.run(ev.capacity.run(source, client=Client()))
    doc = tmp_path / 'docs/materiality-comparison-plan.md'
    doc.write_text('\n'.join('> ' + line for line in ev.PARAGRAPH.splitlines()))
    human = tmp_path / 'human-overlay'; human.mkdir()
    old_cases = json.loads((source / 'cases.json').read_text())
    cases, rows, events = [], [], []
    for pid in ev.NEW_READY:
        c = next(c for c in old_cases if c['case_id'] == pid)
        event = {'kind': 'feedback', 'post_id': pid, 'event_id': 'saved-' + pid,
                 'fields': {'quality_a': 'ready'}, 'notes': 'PRIVATE NEW HUMAN NOTE'}
        cases.append({'case_id': pid, 'input': c['input'], 'original_quality': 'ready',
                      'human_event_id': event['event_id'], 'stratum': 'targeted_boundary'})
        rows.append({'post_id': pid, 'event': event, 'answers': [{'source': 'original', 'quality': 'ready',
                                                              'text_sha256': digest(c['input']['explanation'])}]})
        events.append(event)
    if mismatched_answer:
        cases[0]['input'] = cases[0]['input'] | {'explanation': 'Different answer despite a ready label'}
    write_json(human / 'cases.json', cases)
    write_json(human / 'human-feedback.json', rows)
    (human / 'events.jsonl').write_text('\n'.join(json.dumps(e) for e in events) + '\n')
    manifest = {'files': {p.name: file_hash(p) for p in human.iterdir()}}
    manifest['snapshot_id'] = digest(manifest)
    write_json(human / 'manifest.json', manifest)
    access = tmp_path / 'luna-access.json'
    write_json(access, {'models': [{'id': ev.MODEL}], 'inference_calls': 0})
    output = tmp_path / 'materiality'
    plan = ev.prepare(source, human, access, output)
    return source, human, output, plan


def test_only_declared_paragraph_and_cache_key_change_and_labels_stay_out(tmp_path, monkeypatch):
    source, human, output, plan = prepared(tmp_path, monkeypatch)
    assert len(plan['jobs']) == 56 and plan['budget_usd'] == 1
    assert len(plan['repeated_case_ids']) == 8 and len(plan['human_label_scope']) == 17
    assert set(plan['unlabeled_stress_cases']) == set(ev.STRESS_IDS)
    assert max(plan['request_bounds_usd'].values()) == pytest.approx(.2655)
    cases = json.loads((output / 'cases.json').read_text())
    for c in cases:
        a, b = (ev.request(c, arm, output) for arm in ev.ARMS)
        assert {k for k in a if a[k] != b[k]} == {'instructions', 'prompt_cache_key'}
        assert a == ev.capacity.request(c, 'luna', source)
        original_parts, new_parts = a['instructions'].split('\n\n'), b['instructions'].split('\n\n')
        assert [i for i in range(len(original_parts)) if original_parts[i] != new_parts[i]] == [2]
        assert new_parts[2] == ev.PARAGRAPH
        for hidden in ('PRIVATE NEW HUMAN NOTE', 'PRIVATE HUMAN LABEL NOTE', 'original_quality', 'human_snapshot_id'):
            assert hidden not in json.dumps(b)
    for pid in ev.NEW_READY:
        old = next(c for c in json.loads((source / 'cases.json').read_text()) if c['case_id'] == pid)
        new = next(c for c in cases if c['case_id'] == pid)
        assert old.get('original_quality') is None and new['original_quality'] == 'ready'
        assert new['stratum'] == new['original_selection_stratum'] == 'fresh_cached'
        assert new['human_review_stratum'] == 'targeted_boundary'
        for arm in ev.ARMS:
            assert (output/'requests'/f'{pid}.{arm}_r0.json').read_bytes() == (output/'requests'/f'{pid}.{arm}_r1.json').read_bytes()
    assert len(json.loads((output/'human-label-overlay.json').read_text())) == 2


def test_human_label_on_a_different_answer_is_rejected(tmp_path, monkeypatch):
    with pytest.raises(ValueError, match='exact answer'):
        prepared(tmp_path, monkeypatch, mismatched_answer=True)
    assert not (tmp_path / 'materiality').exists()


def test_complete_replay_preserves_source_and_new_files_without_provider_access(tmp_path, monkeypatch):
    source, human, output, plan = prepared(tmp_path, monkeypatch)
    protected = {str(p): file_hash(p) for d in (source, human) for p in d.rglob('*') if p.is_file()}
    client = FakeClient()
    report = asyncio.run(ev.run(output, client=client))
    assert report['complete'] and client.calls == report['calls'] == 56
    assert report['technical_errors'] == 0 and not report['quantitative_screen_pass']
    assert report['materiality_criteria']['counts']['materiality']['ready_first_pass'] == 8
    assert report['materiality_criteria']['counts']['materiality']['ready_repeat_pass'] == 5
    assert {p: file_hash(Path(p)) for p in protected} == protected
    hashes = {str(p): file_hash(p) for p in output.rglob('*') if p.is_file()}
    class NoCalls:
        def __getattr__(self, key):
            raise AssertionError('Replay accessed provider: ' + key)
    assert asyncio.run(ev.run(output, client=NoCalls())) == report
    assert hashes == {str(p): file_hash(p) for p in output.rglob('*') if p.is_file()}


def test_unknown_usage_stops_dispatch_and_keeps_missing_denominators(tmp_path, monkeypatch):
    _, _, output, _ = prepared(tmp_path, monkeypatch)
    client = FakeClient(unknown=True)
    report = asyncio.run(ev.run(output, client=client))
    assert client.calls == 1 and report['unknown_usage_calls'] == 1
    assert report['planned_calls'] == 56 and not report['complete'] and not report['quantitative_screen_pass']
    for arm in ev.ARMS:
        assert sum(sum(report['metrics'][s][arm].values()) for s in report['metrics']) == 20
    asyncio.run(ev.run(output, client=client))
    assert client.calls == 1


def test_tampered_request_or_plan_document_cannot_dispatch(tmp_path, monkeypatch):
    _, _, output, _ = prepared(tmp_path, monkeypatch)
    client = FakeClient()
    doc = tmp_path / 'docs/materiality-comparison-plan.md'
    original = doc.read_text(); doc.write_text(original + '\nChanged after freeze')
    with pytest.raises(ValueError, match='Frozen materiality'):
        asyncio.run(ev.run(output, client=client))
    doc.write_text(original)
    next((output/'requests').glob('*.json')).write_text('{}')
    with pytest.raises(ValueError):
        asyncio.run(ev.run(output, client=client))
    assert client.calls == 0


def test_new_ready_controls_and_all_repeat_targets_are_required(tmp_path, monkeypatch):
    _, _, output, plan = prepared(tmp_path, monkeypatch)
    cases = json.loads((output/'cases.json').read_text())
    results = [{'case_id': j['case_id'], 'arm': j['arm'], 'repeat': j['repeat'],
                'result': {'answer_quality': 'fail' if j['case_id'] in ev.focused.REPAIR_IDS else 'pass',
                           'verdict': 'fail' if j['case_id'] in ev.focused.REPAIR_IDS else 'uncertain'}} for j in plan['jobs']]
    budget = ev.capacity.Budget(plan, output)
    assert ev.report_for(plan, cases, results, [], budget)['quantitative_screen_pass']
    next(r for r in results if r['case_id'] == ev.NEW_READY[0] and r['arm'] == 'materiality' and r['repeat'] == 1)['result']['answer_quality'] = 'fail'
    report = ev.report_for(plan, cases, results, [], budget)
    assert not report['quantitative_screen_pass']
    assert report['materiality_criteria']['counts']['materiality']['ready_repeat_pass'] == 4
