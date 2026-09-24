import json
from pathlib import Path

import pytest

from basedbench.pipeline import evidence_ranking_run as run
from basedbench.pipeline import evidence_ranking_policy as policy
from basedbench.pipeline.curation_corpus import file_hash


def row(cid='ready', gold='ready', group='g', comment='The clue is a reversed greeting.'):
    return {'case_id': cid, 'gold': gold, 'group_id': group, 'post_id': cid,
            'image_error': None, 'arms': {'broad_observation': {'state': 'completed'}},
            'input': {'image_sha256': 'image', 'explanation': 'PRIVATE REFERENCE ' + cid},
            'comments': [{'id': 'one', 'text': comment}],
            'observation': {'visible_text': 'caption', 'visible_scene': 'Two speakers', 'uncertainties': []},
            'human': {'notes': 'PRIVATE NOTE'}}


def test_context_reference_is_not_borrowed_from_different_family_variant(tmp_path):
    rows = [row('a-repair', 'repair'), row('b-ready', comment='Different evidence')]
    cases, inventory = run.freeze_cases(rows, tmp_path)
    assert len(cases) == 1 and cases[0]['reference_explanation'] is None
    assert inventory['context_variants'][0]['context_count'] == 2
    assert inventory['unmatched_ready_reference_versions'] == 1
    assert inventory['unmatched_ready_references'][0]['case_id'] == 'b-ready'
    rows.append(row('c-ready'))
    cases, _ = run.freeze_cases(rows, tmp_path)
    assert cases[0]['reference_case_ids'] == ['c-ready']
    assert 'PRIVATE NOTE' not in json.dumps(cases)
    assert 'PRIVATE REFERENCE' not in json.dumps(policy.comment_requests(cases[0]))


def test_review_sampling_has_unique_families_and_balanced_blinded_slots(tmp_path):
    rows = [row(post + '-version', group=post) for post in run.DIAGNOSTICS]
    rows += [row(f'c{i}', group=f'g{i}') for i in range(30)]
    cases, _ = run.freeze_cases(rows, tmp_path)
    selection = run.review_selection(cases)
    assert selection == run.review_selection(list(reversed(cases)))
    assert len({s['family_id'] for s in selection}) == 16
    assert sum(s['sample_kind'] == 'diagnostic' for s in selection) == 4
    from collections import Counter
    assert sorted(Counter(tuple(s['methods'].values()) for s in selection).values()) == [2, 2, 3, 3, 3, 3]


class Jev:
    def __init__(self, invalid=False):
        self.calls = []
        self.invalid = invalid

    def post(self, url, json):
        self.calls.append(json)
        assert 'PRIVATE' not in str(json)
        answers = {qid: {'type': 'noul', 'noul': .9 if qid.startswith(('useful', 'decodes')) else .1}
                   for qid in json['questions']}
        if self.invalid and len(self.calls) == 1:
            answers.pop(next(iter(answers)))
        return {'model': json['model'], 'answers': answers,
                'usage': {'input_tokens': 100, 'output_tokens': 50}}


@pytest.mark.parametrize('invalid', [False, True])
def test_offline_end_to_end_preserves_abstentions_and_replays_without_keys(tmp_path, monkeypatch, invalid):
    cases, inventory = run.freeze_cases([row('one', group='one'), row('two', group='two',
                                           comment='Another specific clue.')], tmp_path)
    image = tmp_path / 'images/image'
    image.parent.mkdir()
    image.write_bytes(b'offline image fixture')
    for case in cases:
        case['image_sha256'] = file_hash(image)
    plan = {'plan_id': 'fixture', **run.LIMITS, 'inventory': inventory,
            'review_selection': [{'review_id': 'R01', 'family_id': 'one', 'sample_kind': 'sampled',
                                   'methods': dict(zip('ABC', run.METHODS))}]}
    monkeypatch.setattr(run, 'load', lambda root: (plan, cases))
    client = Jev(invalid)
    result = run.run(tmp_path, client=client)
    assert result['families_completed'] == (1 if invalid else 2)
    assert result['families_abstained'] == int(invalid)
    assert result['human_quality']['status'] == 'pending'
    assert len(client.calls) == 2  # An invalid family does not abort the next.
    count = result['provider_ledger']['calls']
    checked = run.replay(tmp_path)
    assert checked['status'] == 'verified_replay'
    assert checked['provider_ledger']['calls'] == count
    review = run.read(tmp_path / 'review-cases.json')
    assert review[0]['packs']['A']['status'] == 'completed'
    if invalid:
        assert review[0]['packs']['B']['status'] == 'unavailable'
    before = file_hash(tmp_path / 'evidence-ranking-ledger.json')
    (tmp_path / 'review-feedback').mkdir()
    (tmp_path / 'review-feedback/events.jsonl').write_text('{}\n')
    run.replay(tmp_path)  # New human feedback is outside the model-run freeze.
    assert file_hash(tmp_path / 'evidence-ranking-ledger.json') == before
    with (tmp_path / 'outcomes.json').open('a') as stream:
        stream.write(' ')
    with pytest.raises(ValueError, match='artifact changed'):
        run.replay(tmp_path)


def test_prepared_identity_detects_code_drift_without_network(monkeypatch, tmp_path):
    from basedbench.pipeline.curation_corpus import digest
    run.atomic(tmp_path / 'cases.json', [])
    run.atomic(tmp_path / 'request-preview.json', {})
    manifest = {'version': run.VERSION, **run.LIMITS, 'code_hashes': {'fake': 'before'},
        'cases_sha256': file_hash(tmp_path / 'cases.json'),
        'preview_sha256': file_hash(tmp_path / 'request-preview.json'), 'source_hashes': {}, 'image_hashes': {}}
    manifest['plan_id'] = digest(manifest)
    run.atomic(tmp_path / 'plan.json', manifest)
    monkeypatch.setattr(run, 'code_hashes', lambda: {'fake': 'after'})
    with pytest.raises(ValueError, match='code'):
        run.load(tmp_path)


def test_invalid_later_batch_clears_partial_scores_and_keeps_order(tmp_path):
    case = run.freeze_cases([row()], tmp_path)[0][0]
    case['comments'].append({'id': 'two', 'text': 'A competing interpretation.'})

    class LaterInvalid:
        calls = 0

        def call(self, body):
            self.calls += 1
            if self.calls == 1:
                return {'status': 'completed', 'scores': {key: .5 for key in body['questions']}, 'errors': []}
            return {'status': 'invalid', 'scores': {}, 'errors': ['answer_ids']}

    result = run.evaluate_case(case, LaterInvalid())
    assert result['status'] == 'abstained'
    assert result['scores'] == {}
    assert result['packs']['order']['status'] == 'completed'
    assert result['packs']['rank']['status'] == 'unavailable'
