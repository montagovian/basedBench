"""Regression coverage for isolated labels, bounded execution and immutable replay."""
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from basedbench.pipeline import focused_connection_eval as ev
from basedbench.pipeline.curation_corpus import file_hash, write_json


def source(tmp_path, name, ids, human):
    p = tmp_path / name
    (p / 'assets').mkdir(parents=True)
    image = p / 'image.png'
    Image.new('RGB', (24, 24), 'blue').save(image)
    sha = file_hash(image); image.rename(p / 'assets' / sha)
    cases = []
    for cid in ids:
        c = {'case_id': cid, 'post_id': cid, 'group_id': cid, 'family_weight': 1,
             'stratum': 'targeted' if human else 'fresh_cached',
             'human_note': 'PRIVATE HUMAN LABEL NOTE',
             'input': {'explanation': 'The sound-alike decodes the joke.',
                       'comment_evidence': 'ID: a | Score: 4\nfirst\nID: b | Score: 3\nsecond\nID: c | Score: 2\nthird',
                       'image_sha256': sha}}
        if human:
            c['original_quality'] = 'repair' if cid in ev.REPAIR_IDS else 'ready'
        cases.append(c)
    write_json(p / 'cases.json', cases)
    write_json(p / ('manifest.json' if human else 'plan.json'),
               {'files': {str(f.relative_to(p)): file_hash(f) for f in p.rglob('*') if f.is_file()}})
    return p


def prepared(tmp_path, monkeypatch):
    (tmp_path / 'docs').mkdir()
    (tmp_path / 'docs/focused-connection-plan.md').write_text('Frozen test plan')
    monkeypatch.chdir(tmp_path)
    human = source(tmp_path, 'human', ev.REPAIR_IDS + ev.READY_IDS, True)
    stress = source(tmp_path, 'stress', ev.STRESS_IDS, False)
    output = tmp_path / 'run'
    plan = ev.prepare(human, stress, output)
    return human, stress, output, plan


def value(focused=True):
    v = {'answer_quality': 'pass', 'evidence_status': 'insufficient', 'material_defects': [],
         'missing_or_wrong_connection': None, 'supporting_comment_ids': ['a', 'b'],
         'reason': 'The answer gets the joke, but only two comments support it.'}
    if focused:
        v['required_connections'] = [{'visible_cue': 'A wordplay cue.', 'recovered_meaning': 'A sound-alike.',
            'candidate_basis': 'The candidate decodes it.', 'coverage': 'present', 'why_needed': 'It is the pun.'}]
    return v


def test_frozen_requests_only_include_source_answer_and_shared_runtime(tmp_path, monkeypatch):
    human, stress, output, plan = prepared(tmp_path, monkeypatch)
    assert len(plan['jobs']) == 52 and plan['budget_usd'] == 1
    assert max(plan['request_bounds_usd'].values()) == pytest.approx(.2655)
    assert set(plan['unlabeled_stress_cases']).isdisjoint(plan['human_label_scope'])
    c = json.loads((output / 'cases.json').read_text())[0]
    a, b = (ev.request(c, arm, output) for arm in ev.ARMS)
    original = ev.calibrated.request(c, 'simple_6', output)
    assert a == original | {'max_output_tokens': 4000}
    assert a['input'] == b['input'] and a['model'] == b['model'] == 'gpt-6-luna'
    assert a['reasoning'] == b['reasoning'] == {'effort': 'medium'}
    assert a['max_output_tokens'] == b['max_output_tokens'] == 4000
    for path in (output / 'requests').glob('*.json'):
        text = path.read_text()
        assert 'PRIVATE HUMAN LABEL NOTE' not in text and 'original_quality' not in text
        assert 'evaluation_role' not in text
    assert list(b['text']['format']['schema']['properties'])[0] == 'required_connections'
    with pytest.raises(FileExistsError):
        ev.prepare(human, stress, output)


def test_coverage_contradictions_and_unknown_support_cannot_pass(tmp_path):
    p = source(tmp_path, 'human', ['1ueh8cd'], True)
    c = json.loads((p / 'cases.json').read_text())[0]
    v = value()
    def parsed():
        return ev.parse(c, 'focused', {'status': 'completed', 'response': {'model': ev.MODEL},
                                      'output_text': json.dumps(v)})
    assert parsed()['answer_quality'] == 'pass' and parsed()['verdict'] == 'uncertain'
    v['required_connections'][0]['coverage'] = 'missing'
    assert 'error' in parsed()
    v.update(answer_quality='fail', material_defects=['missing_connection'], missing_or_wrong_connection='The decoding is missing.')
    assert parsed()['verdict'] == 'fail'
    v['required_connections'][0]['coverage'] = 'present'
    assert 'error' in parsed()
    v = value(); v['evidence_status'] = 'supported'
    assert 'error' in parsed()
    v['supporting_comment_ids'] = ['a', 'b', 'unknown']
    assert 'error' in parsed()


class FakeClient:
    def __init__(self, unknown=False):
        self.responses = self
        self.calls = 0
        self.unknown = unknown

    async def create(self, **body):
        self.calls += 1
        usage = None if self.unknown else {'input_tokens': 100, 'output_tokens': 100}
        output = json.dumps(value(body['instructions'] == ev.FOCUSED))
        return SimpleNamespace(status='completed', output_text=output,
            usage=SimpleNamespace(model_dump=lambda **_: usage) if usage else None,
            model_dump=lambda **_: {'model': ev.MODEL, 'status': 'completed', 'usage': usage})


def test_completed_run_replays_without_accessing_provider_or_changing_files(tmp_path, monkeypatch):
    _, _, output, _ = prepared(tmp_path, monkeypatch)
    client = FakeClient()
    report = asyncio.run(ev.run(output, client=client))
    assert client.calls == report['calls'] == 52
    assert report['complete'] and report['technical_errors'] == 0
    assert not report['quantitative_screen_pass']  # Passing every defective answer fails the target.
    hashes = {str(p): file_hash(p) for p in output.rglob('*') if p.is_file()}
    class NoCalls:
        def __getattr__(self, key):
            raise AssertionError('Replay touched provider: ' + key)
    assert asyncio.run(ev.run(output, client=NoCalls())) == report
    assert hashes == {str(p): file_hash(p) for p in output.rglob('*') if p.is_file()}


def test_unknown_usage_stops_dispatch_and_survives_resume(tmp_path, monkeypatch):
    _, _, output, _ = prepared(tmp_path, monkeypatch)
    client = FakeClient(unknown=True)
    report = asyncio.run(ev.run(output, client=client))
    assert client.calls == 1 and report['unknown_usage_calls'] == 1
    assert not report['complete'] and not report['quantitative_screen_pass']
    asyncio.run(ev.run(output, client=client))
    assert client.calls == 1


def test_mutated_request_is_rejected_before_provider_access(tmp_path, monkeypatch):
    _, _, output, _ = prepared(tmp_path, monkeypatch)
    path = next((output / 'requests').glob('*.json'))
    path.write_text('{}')
    client = FakeClient()
    with pytest.raises(ValueError):
        asyncio.run(ev.run(output, client=client))
    assert client.calls == 0
