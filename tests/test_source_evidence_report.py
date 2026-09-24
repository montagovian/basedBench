"""Reconciliation tests use synthetic frozen artifacts, never provider calls."""
import json
import shutil

import pytest

from basedbench.pipeline import source_evidence_report as analysis
from basedbench.pipeline.curation_corpus import digest, file_hash, write_json


def _case(post, answer, quality, group):
    input_value = {'explanation': answer, 'comment_evidence': 'ID: c1 | Score: 1\nThe inversion.',
                   'image_sha256': 'a' * 64}
    sha = digest(input_value)
    return {'case_id': f'{post}-{sha[:16]}', 'post_id': post, 'input': input_value,
            'input_sha256': sha, 'group_id': group, 'image_error': None,
            'human': {'quality': quality, 'events': [{'notes': 'Exact human note.'}]}}


def _result(answer='pass', evidence='supported', verdict='pass'):
    return {'answer_quality': answer, 'evidence_status': evidence, 'verdict': verdict,
            'reason': 'Specific reading.', 'essential_claims': []}


def _match(case, *, repeat=0, answer='pass', evidence='insufficient', verdict='uncertain'):
    return {'case_id': case['case_id'], 'post_id': case['post_id'],
            'experiment': 'calibrated-luna-dev-v1', 'condition': 'simple_6', 'repeat': repeat,
            'input_identity': {'dataset_input_sha256': case['input_sha256'],
                               'match': 'exact_input_match'},
            'answer_quality': answer, 'evidence_status': evidence, 'joint_verdict': verdict,
            'verdict_kind': 'joint_answer_and_evidence_gate', 'parsed': {},
            'model': {'actual_returned': 'gpt-6-luna'},
            'prompt_hash': 'old-prompt', 'schema_hash': 'old-schema',
            'source': {'call_sha256': 'b' * 64}}


def _fixture(tmp_path, *, complete=True, tampered_audit=False):
    root = tmp_path / 'frozen'
    for folder in ('dataset', 'baselines', 'evaluation'):
        (root / folder).mkdir(parents=True)
    ready = _case('p1', 'This sign reverses the scene.', 'ready', 'raw1')
    repair = _case('p1', 'A different answer version.', 'repair', 'raw1')
    held = _case('p2', 'Unsupported animation.', 'unclear', 'raw2')
    cases = [ready, repair, held]
    write_json(root / 'dataset' / 'cases.json', cases)
    write_json(root / 'dataset' / 'report.json', {'cases': 3})
    dataset_manifest = {'files': {name: file_hash(root / 'dataset' / name) for name in
                                  ('cases.json', 'report.json')}, 'source_manifest_hashes': {}}
    dataset_manifest['dataset_id'] = digest(dataset_manifest)
    write_json(root / 'dataset' / 'manifest.json', dataset_manifest)
    write_json(root / 'baselines' / 'matches.json', [_match(ready),
        _match(ready, repeat=1, answer='fail', evidence='insufficient', verdict='fail')])
    write_json(root / 'baselines' / 'report.json', {'matched_trial_count': 2})
    write_json(root / 'baselines' / 'manifest.json', {name: file_hash(root / 'baselines' / name)
        for name in ('matches.json', 'report.json')})
    write_json(root / 'evaluation' / 'sources.json', [{'source_id': 's1', 'post_ids': ['p1'],
        'access_status': 'accessible', 'passage': 'A read passage.', 'support_scope': 'The reference.'}])
    jobs = [{'key': f'j{i}', 'case_id': cid, 'arm': arm} for i, (cid, arm) in enumerate((
        (ready['case_id'], 'original_evidence'), (ready['case_id'], 'external_evidence'),
        (repair['case_id'], 'original_evidence'), (repair['case_id'], 'external_evidence')))]
    plan = {'model': 'gpt-6-luna', 'jobs': jobs, 'max_calls': 4,
            'holds': {held['case_id']: 'animated_image_unsupported'},
            'source_files': {str(root / 'dataset' / 'manifest.json'): file_hash(root / 'dataset' / 'manifest.json')},
            'files': {'sources.json': file_hash(root / 'evaluation' / 'sources.json')}}
    plan['experiment_id'] = digest(plan)
    write_json(root / 'evaluation' / 'plan.json', plan)
    results = [{'key': 'j0', 'case_id': ready['case_id'], 'arm': 'original_evidence',
                'result': _result(evidence='insufficient', verdict='uncertain')},
               {'key': 'j1', 'case_id': ready['case_id'], 'arm': 'external_evidence',
                'result': _result()},
               {'key': 'j2', 'case_id': repair['case_id'], 'arm': 'original_evidence',
                'result': {'error': 'invalid_schema'}},
               {'key': 'j3', 'case_id': repair['case_id'], 'arm': 'external_evidence',
                'result': {'error': 'not_attempted'}}]
    report = {'experiment_id': plan['experiment_id'], 'complete': complete, 'stop_reason': 'budget_cap',
              'planned_calls': 4, 'completed_calls': 3, 'missing_calls': 1, 'results': results,
              'cost': {'budget_usd': 1, 'accounted_usd': .5}}
    write_json(root / 'evaluation' / 'report.json', report)
    write_json(root / 'evaluation' / 'results-manifest.json', {
        'report.json': file_hash(root / 'evaluation' / 'report.json')})
    audit = {'version': 'grouping-audit-v1',
             'dataset_manifest_sha256': file_hash(root / 'dataset' / 'manifest.json'),
             'source_files': {}, 'case_group_ids': {c['case_id']: 'family1' if c['post_id'] == 'p1'
                                                   else 'family2' for c in cases},
             'case_strata': {ready['case_id']: ['calibration', 'review'],
                             repair['case_id']: ['calibration'], held['case_id']: ['review']}}
    audit['audit_id'] = digest(audit)
    write_json(root / 'grouping-audit.json', audit)
    if tampered_audit:
        audit['case_group_ids'][ready['case_id']] = 'unverified'
        write_json(root / 'grouping-audit.json', audit)
    return root, cases


def test_report_separates_answer_evidence_errors_and_correlated_versions(tmp_path):
    root, cases = _fixture(tmp_path)
    output = tmp_path / 'analysis'
    report = analysis.prepare(root, output)
    rows = json.loads((output / 'rows.json').read_text())
    posts = json.loads((output / 'posts.json').read_text())
    assert report['coverage']['cases'] == 3 and report['coverage']['posts'] == 2
    assert report['coverage']['answer_versions_beyond_first'] == 1
    assert report['coverage']['families'] == 2 and report['grouping']['verified']
    assert report['coverage']['simple_6_r0_cases'] == 1
    assert report['coverage']['simple_6_r1_cases'] == 1
    assert report['coverage']['matched_baseline_cases'] == 1
    assert report['same_model_baseline']['r0_vs_r1_answer_changed_ids'] == [cases[0]['case_id']]
    assert 'conservative' in report['cost_basis']
    assert report['paired_external']['completed_pairs'] == 1
    assert report['paired_external']['evidence_changed_ids'] == [cases[0]['case_id']]
    assert report['paired_external']['answer_changed_ids'] == []
    assert report['by_human_quality']['repair']['original_evidence']['state'] == {'technical_error': 1}
    assert report['by_human_quality']['repair']['external_evidence']['state'] == {'not_attempted': 1}
    assert report['by_human_quality']['ready']['original_evidence']['answer_quality'] == {'pass': 1}
    assert report['by_human_quality']['ready']['original_evidence']['evidence_status'] == {'insufficient': 1}
    assert report['by_human_quality']['unclear']['external_evidence']['state'] == {'not_applicable': 1}
    assert next(row for row in rows if row['case_id'] == cases[0]['case_id'])['source_strata'] == ['calibration', 'review']
    assert next(post for post in posts if post['post_id'] == 'p1')['answer_versions'] == 2
    with pytest.raises(FileExistsError):
        analysis.prepare(root, output)


def test_partial_report_refused_without_publishing(tmp_path):
    root, _ = _fixture(tmp_path, complete=False)
    output = tmp_path / 'analysis'
    with pytest.raises(ValueError, match='still running'):
        analysis.prepare(root, output)
    assert not output.exists()


def test_tampered_audit_or_source_manifest_refused(tmp_path):
    root, _ = _fixture(tmp_path, tampered_audit=True)
    with pytest.raises(ValueError, match='Grouping audit identity'):
        analysis.prepare(root, tmp_path / 'analysis')
    root, _ = _fixture(tmp_path / 'second')
    (root / 'baselines' / 'matches.json').write_text('[]')
    with pytest.raises(ValueError, match='Frozen source file changed'):
        analysis.prepare(root, tmp_path / 'analysis2')


def test_complete_baseline_snapshot_supersedes_old_one(tmp_path):
    root, _ = _fixture(tmp_path)
    shutil.copytree(root / 'baselines', root / 'baselines-complete')
    matches_path = root / 'baselines-complete' / 'matches.json'
    matches = json.loads(matches_path.read_text())
    matches[0]['experiment'] = 'calibrated-luna-fresh-v1'
    write_json(matches_path, matches)
    write_json(root / 'baselines-complete' / 'manifest.json', {name: file_hash(root / 'baselines-complete' / name)
        for name in ('matches.json', 'report.json')})
    (root / 'baselines' / 'matches.json').write_text('[]')
    report = analysis.prepare(root, tmp_path / 'analysis')
    assert report['baseline_snapshot'] == 'baselines-complete'
    assert report['coverage']['simple_6_r0_cases'] == 1
    row = next(item for item in json.loads((tmp_path / 'analysis' / 'rows.json').read_text())
               if item['simple_6_r0'] is not None)
    assert row['simple_6_r0']['experiment'] == 'calibrated-luna-fresh-v1'
