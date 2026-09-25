import json
from pathlib import Path

import pytest

from basedbench.pipeline import comment_selection_run as run
from basedbench.pipeline.curation_corpus import digest, file_hash


def case(cid, group=None):
    return {'case_id': cid, 'group_id': group or cid, 'post_id': cid,
            'comments': [{'id': 'one', 'text': 'The character mistakes a noun for a name.'},
                         {'id': 'two', 'text': 'That is hilarious.'}],
            'observation': {'visible_text': 'caption', 'visible_scene': 'Two people talking', 'uncertainties': []},
            'human_notes': 'PRIVATE', 'reference_explanation': 'PRIVATE'}


def baseline(c):
    return {'status': 'completed', 'ranking': [{'comment_id': x['id'], 'index': i, 'utility': .9-i*.1}
                                            for i, x in enumerate(c['comments'])]}


def test_review_selection_is_frozen_balanced_and_excludes_prior_cases():
    prior = [{'review_id': rid, 'family_id': f'g{i}'} for i, rid in enumerate(run.DEVELOPMENT_REVIEWS)]
    prior.append({'review_id': 'R99', 'family_id': 'g4'})
    cases = [case(str(i), f'g{i}') for i in range(20)]
    selected = run.review_selection(cases, prior)
    assert selected == run.review_selection(cases[::-1], prior[::-1])
    assert len({s['family_id'] for s in selected}) == 8
    assert [s['sample_kind'] for s in selected] == ['development']*4 + ['newly_reviewed']*4
    assert 'g4' not in {s['family_id'] for s in selected}
    assert sum(s['methods']['A'] == 'pairwise' for s in selected) == 4


def test_preflight_accounts_for_entire_reservation_and_questions(monkeypatch):
    cases = [case('one')]
    rows, preview = run.preflight(cases, 1)
    assert preview['state']['comments'] == cases[0]['comments']
    assert 'PRIVATE' not in json.dumps(preview)
    assert sum(r['questions'] for r in rows) == 16  # 7*2 + both directions
    with pytest.raises(ValueError, match='remaining budget'):
        run.preflight(cases, run.RESERVE_USD / 2)
    monkeypatch.setattr(run, 'LIMITS', {'max_calls': 1, 'max_questions': 20000})
    with pytest.raises(ValueError, match='preflight exceeds'):
        run.preflight(cases, 1)


class Jev:
    def __init__(self, invalid=False):
        self.calls = []
        self.invalid = invalid

    def post(self, url, json):
        self.calls.append(json)
        assert 'PRIVATE' not in str(json)
        answers = {qid: {'type': 'noul', 'noul': .95 if qid.startswith(('relevant', 'explains', 'complete')) else .05}
                   for qid in json['questions']}
        if self.invalid and len(self.calls) == 2:
            answers.pop(next(iter(answers)))
        return {'model': json['model'], 'answers': answers, 'usage': {'input_tokens': 100, 'output_tokens': 50}}


@pytest.mark.parametrize('invalid', [False, True])
def test_run_and_offline_replay_keep_baseline_abstentions_and_human_journal(tmp_path, monkeypatch, invalid):
    cases = [case('one'), case('two')]
    cases[1]['comments'][0]['text'] = 'Another decoding example.'
    image = tmp_path / 'images' / 'fixture'
    image.parent.mkdir()
    image.write_bytes(b'fixture image')
    for c in cases:
        c['image_path'] = str(image)
        c['image_sha256'] = file_hash(image)
    baselines = {c['case_id']: baseline(c) for c in cases}
    plan = {'plan_id': 'fixture', **run.LIMITS, 'budget_usd': .9, 'prior_spent_usd': .1,
            'inventory': {'families': 2, 'comments': 4},
            'review_selection': [{'review_id': 'S01', 'family_id': 'one', 'sample_kind': 'development',
                                  'methods': {'A': 'baseline', 'B': 'pairwise'}}]}
    monkeypatch.setattr(run, 'load', lambda _: (plan, cases, baselines))
    client = Jev(invalid)
    report = run.run(tmp_path, client=client)
    assert report['families_completed'] == 2-int(invalid)
    assert report['families_abstained'] == int(invalid)
    assert report['human_quality']['status'] == 'pending'
    assert report['cumulative_spent_usd'] == .1 + report['provider_ledger']['spent_usd']
    outcomes = run.read(tmp_path / 'outcomes.json')
    if invalid:
        assert outcomes[0]['scores'] == {}
        assert outcomes[0]['lists']['baseline']['status'] == 'completed'
        assert outcomes[0]['lists']['pairwise']['status'] == 'unavailable'
    assert len(client.calls) == 4
    count = report['provider_ledger']['calls']
    journal = tmp_path / 'review-feedback' / 'events.jsonl'
    journal.parent.mkdir()
    journal.write_text('human feedback remains mutable and outside model freeze\n')
    before = file_hash(journal)
    replayed = run.replay(tmp_path)
    assert replayed['provider_ledger']['calls'] == count
    assert file_hash(journal) == before
    assert run.run(tmp_path, client=client)['status'] == 'verified_replay'
    assert len(client.calls) == count
    with (tmp_path / 'outcomes.json').open('a') as stream:
        stream.write(' ')
    with pytest.raises(ValueError, match='artifact changed'):
        run.replay(tmp_path)


def test_cumulative_budget_counts_previous_run():
    c = case('one')
    outcome = {'case_id': 'one', 'status': 'abstained', 'lists': {}}
    with pytest.raises(ValueError, match='Cumulative budget'):
        run.summarize({'prior_spent_usd': .1}, [c], [outcome], {'spent_or_reserved_usd': .91})


def test_load_checks_source_anchors_code_and_prior_spend(tmp_path, monkeypatch):
    source = tmp_path / 'source'
    source.mkdir()
    run.atomic(source / 'report.json', {'provider_ledger': {'spent_usd': .1, 'pending_calls': 0, 'stop_reason': None}})
    anchor = tmp_path / 'anchors.json'
    anchor.write_text('{}')
    root = tmp_path / 'new'
    root.mkdir()
    for name, value in [('cases.json', []), ('baseline-packs.json', {}), ('request-preview.json', {})]:
        run.atomic(root / name, value)
    monkeypatch.setattr(run, 'code_hashes', lambda: {'code': 'fixed'})
    plan = {'version': run.VERSION, **run.LIMITS, 'cumulative_budget_usd': 1.,
            'prior_spent_usd': .1, 'budget_usd': .9, 'source_root': str(source),
            'code_hashes': run.code_hashes(), 'image_hashes': {},
            'source_hashes': {str(anchor): file_hash(anchor)},
            'input_hashes': {n: file_hash(root/n) for n in ('cases.json', 'baseline-packs.json', 'request-preview.json')}}
    plan['plan_id'] = digest(plan)
    run.atomic(root / 'plan.json', plan)
    assert run.load(root)[1:] == ([], {})
    anchor.write_text('{"changed":true}')
    with pytest.raises(ValueError, match='anchors changed'):
        run.load(root)
    anchor.write_text('{}')
    run.atomic(source / 'report.json', {'provider_ledger': {'spent_usd': .2, 'pending_calls': 0, 'stop_reason': None}})
    with pytest.raises(ValueError, match='spending changed'):
        run.load(root)
    monkeypatch.setattr(run, 'code_hashes', lambda: {'code': 'drift'})
    with pytest.raises(ValueError, match='code changed'):
        run.load(root)


def test_review_finalization_resumes_without_overwriting_existing_packet(tmp_path):
    c = case('one')
    c.update(image_path=str(tmp_path/'image'), image_sha256='imagehash')
    plan = {'plan_id': 'fixture', 'review_selection': [
        {'review_id': 'S01', 'family_id': 'one', 'sample_kind': 'development',
         'methods': {'A': 'baseline', 'B': 'pairwise'}}]}
    outcome = {'family_id': 'one', 'lists': run.policy.build_lists(c, baseline(c), None)}
    run.make_review(tmp_path, plan, [c], [outcome])
    before = file_hash(tmp_path/'review-cases.json')
    # Simulate a crash after writing the packet but before its manifest.
    (tmp_path/'review-manifest.json').unlink()
    run.make_review(tmp_path, plan, [c], [outcome])
    assert file_hash(tmp_path/'review-cases.json') == before
    run.make_review(tmp_path, plan, [c], [outcome])
    altered = run.read(tmp_path/'review-cases.json')
    altered[0]['case_id'] = 'changed'
    run.atomic(tmp_path/'review-cases.json', altered)
    with pytest.raises(ValueError, match='Existing review differs'):
        run.make_review(tmp_path, plan, [c], [outcome])
