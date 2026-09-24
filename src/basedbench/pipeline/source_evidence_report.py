"""Reconcile the frozen source-evidence replay without treating evidence as human gold."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import tempfile

from basedbench.pipeline.curation_corpus import digest, file_hash, write_json

VERSION = 'source-evidence-analysis-v1'
ARMS = ('original_evidence', 'external_evidence')
HUMAN_QUALITIES = ('ready', 'repair', 'unclear', 'conflicting')


def _read(path: Path):
    return json.loads(path.read_text())


def _verify_files(root: Path, files: dict[str, str]) -> None:
    if not isinstance(files, dict):
        raise ValueError('Invalid manifest shape')
    root = root.resolve()
    for relative, expected in files.items():
        name = Path(relative)
        path = root / name
        if (name.is_absolute() or '..' in name.parts or not path.resolve().is_relative_to(root)
                or not path.is_file() or file_hash(path) != expected):
            raise ValueError(f'Frozen source file changed: {relative}')


def _sources(root: Path) -> tuple[list[dict], list[dict], dict, dict, Path]:
    dataset, evaluation = root / 'dataset', root / 'evaluation'
    baseline = root / ('baselines-complete' if (root / 'baselines-complete').is_dir() else 'baselines')
    dataset_manifest = _read(dataset / 'manifest.json')
    if dataset_manifest.get('dataset_id') != digest({k: v for k, v in dataset_manifest.items() if k != 'dataset_id'}):
        raise ValueError('Dataset manifest identity changed')
    _verify_files(dataset, dataset_manifest['files'])
    baseline_manifest = _read(baseline / 'manifest.json')
    _verify_files(baseline, baseline_manifest)
    plan = _read(evaluation / 'plan.json')
    if plan.get('experiment_id') != digest({k: v for k, v in plan.items() if k != 'experiment_id'}):
        raise ValueError('Evaluation plan identity changed')
    _verify_files(evaluation, plan['files'])
    result_manifest = _read(evaluation / 'results-manifest.json')
    _verify_files(evaluation, result_manifest)
    for source_path, expected in plan['source_files'].items():
        if file_hash(Path(source_path)) != expected:
            raise ValueError(f'Frozen evaluation source changed: {source_path}')
    report = _read(evaluation / 'report.json')
    if not report.get('complete'):
        raise ValueError('Evaluation is still running; do not score a partial report')
    if report.get('experiment_id') != plan['experiment_id']:
        raise ValueError('Evaluation report belongs to a different plan')
    cases, matches = _read(dataset / 'cases.json'), _read(baseline / 'matches.json')
    return cases, matches, plan, report, baseline


def _unique_by(rows: list[dict], key: str, *, label: str) -> dict:
    result = {}
    for row in rows:
        identity = row[key]
        if identity in result:
            raise ValueError(f'Duplicate {label}: {identity}')
        result[identity] = row
    return result


def _outcome(result: dict | None, *, planned: bool, held: bool = False) -> dict:
    if held:
        return {'state': 'held', 'answer_quality': None, 'evidence_status': None,
                'verdict': None, 'error': 'image_hold', 'result': None}
    if not planned:
        return {'state': 'not_applicable', 'answer_quality': None, 'evidence_status': None,
                'verdict': None, 'error': None, 'result': None}
    if result is None:
        raise ValueError('Planned job lacks a result row')
    error = result.get('error')
    if error in {'not_attempted', 'unknown_interrupted_call'}:
        state = 'not_attempted' if error == 'not_attempted' else 'unknown_call'
    else:
        state = 'technical_error' if error else 'completed'
    if state == 'completed' and (result.get('answer_quality') not in {'pass', 'fail', 'uncertain'} or
                                 result.get('evidence_status') not in {'supported', 'insufficient',
                                                                      'competing_readings', 'uncertain'} or
                                 result.get('verdict') not in {'pass', 'fail', 'uncertain'}):
        raise ValueError('Completed checker result lacks separate decisions')
    return {'state': state, 'answer_quality': result.get('answer_quality') if state == 'completed' else None,
            'evidence_status': result.get('evidence_status') if state == 'completed' else None,
            'verdict': result.get('verdict') if state == 'completed' else None,
            'error': error, 'result': result if state in {'completed', 'technical_error'} else None}


def _baseline(row: dict | None) -> dict | None:
    if row is None:
        return None
    state = ('technical_error' if row['parsed'].get('error') or row['answer_quality'] is None or
             row['evidence_status'] is None or row['joint_verdict'] is None else 'completed')
    return {'state': state, 'experiment': row['experiment'],
            'answer_quality': row['answer_quality'], 'evidence_status': row['evidence_status'],
            'verdict': row['joint_verdict'], 'verdict_kind': row['verdict_kind'],
            'error': row['parsed'].get('error'), 'model': row['model']['actual_returned'],
            'prompt_hash': row['prompt_hash'], 'schema_hash': row['schema_hash'],
            'call_sha256': row['source']['call_sha256']}


def _delta(left: dict | None, right: dict | None, *, dimensions: tuple[str, ...]) -> dict:
    if left is None or right is None:
        return {'status': 'unpaired'}
    if left.get('state', 'completed') != 'completed' or right.get('state', 'completed') != 'completed':
        return {'status': 'incomplete_or_error'}
    changes = {name: {'from': left.get(name), 'to': right.get(name)} for name in dimensions
               if left.get(name) != right.get(name)}
    return {'status': 'changed' if changes else 'same', 'changes': changes}


def _group_mapping(root: Path, cases: list[dict]) -> tuple[dict[str, str], dict[str, list[str]], dict]:
    raw = {case['case_id']: str(case.get('group_id') or case['post_id']) for case in cases}
    path = root / 'grouping-audit.json'
    if not path.is_file():
        return raw, {case['case_id']: [] for case in cases}, {
            'source': 'dataset_group_id', 'verified': False, 'file_sha256': None}
    audit = _read(path)
    if (not isinstance(audit, dict) or audit.get('audit_id') !=
            digest({key: value for key, value in audit.items() if key != 'audit_id'})):
        raise ValueError('Grouping audit identity changed')
    if audit.get('dataset_manifest_sha256') != file_hash(root / 'dataset' / 'manifest.json'):
        raise ValueError('Grouping audit dataset manifest changed')
    for source_path, expected in audit['source_files'].items():
        if file_hash(Path(source_path)) != expected:
            raise ValueError('Grouping audit source changed')
    mapping = audit.get('case_group_ids')
    strata = audit.get('case_strata')
    if not isinstance(mapping, dict) or not isinstance(strata, dict):
        raise ValueError('Grouping audit lacks case_group_ids or case_strata')
    expected = {case['case_id'] for case in cases}
    if set(mapping) != expected or any(not isinstance(value, str) or not value for value in mapping.values()):
        raise ValueError('Grouping audit does not cover reconstructed cases')
    if set(strata) != expected or any(not isinstance(value, list) or
                                      any(not isinstance(item, str) for item in value) for value in strata.values()):
        raise ValueError('Grouping audit strata do not cover reconstructed cases')
    return mapping, strata, {'source': 'grouping_audit', 'verified': True,
                             'file_sha256': file_hash(path), 'audit_id': audit['audit_id']}


def _aggregate(rows: list[dict]) -> dict:
    by_quality = {}
    for quality in HUMAN_QUALITIES:
        subset = [row for row in rows if row['human_quality'] == quality]
        by_arm = {}
        for arm in ARMS:
            values = [row[arm] for row in subset]
            by_arm[arm] = {'cases': len(subset), 'state': dict(Counter(v['state'] for v in values)),
                           'answer_quality': dict(Counter(v['answer_quality'] for v in values if v['state'] == 'completed')),
                           'evidence_status': dict(Counter(v['evidence_status'] for v in values if v['state'] == 'completed')),
                           'combined_verdict': dict(Counter(v['verdict'] for v in values if v['state'] == 'completed')),
                           'error_case_ids': [row['case_id'] for row in subset if row[arm]['state'] in
                                              {'technical_error', 'unknown_call'}]}
        by_quality[quality] = by_arm
    return by_quality


def _summaries(rows: list[dict]) -> list[dict]:
    grouped = defaultdict(list)
    for row in rows:
        grouped[row['post_id']].append(row)
    return [{'post_id': pid, 'case_ids': [row['case_id'] for row in values],
             'answer_versions': len(values), 'human_qualities': sorted({row['human_quality'] for row in values}),
             'source_cohort': 'external_available' if any(row['source_cohort'] == 'external_available' for row in values)
                              else 'original_only',
             'original_answer_quality': dict(Counter(row['original_evidence']['answer_quality'] for row in values
                                                      if row['original_evidence']['state'] == 'completed')),
             'external_answer_quality': dict(Counter(row['external_evidence']['answer_quality'] for row in values
                                                      if row['external_evidence']['state'] == 'completed'))}
            for pid, values in sorted(grouped.items())]


def _prepare_in_place(root: Path, output: Path) -> dict:
    cases, matches, plan, evaluation, baseline_dir = _sources(root)
    by_case = _unique_by(cases, 'case_id', label='dataset case')
    jobs = _unique_by(plan['jobs'], 'key', label='evaluation job')
    if len(plan['jobs']) != plan['max_calls'] or evaluation['planned_calls'] != len(jobs):
        raise ValueError('Evaluation job count changed')
    results = _unique_by(evaluation['results'], 'key', label='evaluation result')
    if set(results) != set(jobs):
        raise ValueError('Evaluation results do not cover all planned jobs')
    if any(results[key]['case_id'] != job['case_id'] or results[key]['arm'] != job['arm']
           for key, job in jobs.items()):
        raise ValueError('Evaluation result identity changed')
    matched = defaultdict(list)
    matched_case_ids = set()
    for item in matches:
        if item['case_id'] not in by_case:
            raise ValueError('Baseline match refers to missing case')
        if item['input_identity']['dataset_input_sha256'] != by_case[item['case_id']]['input_sha256']:
            raise ValueError('Baseline exact-input identity changed')
        if (item['experiment'] in {'calibrated-luna-dev-v1', 'calibrated-luna-fresh-v1'}
                and item['condition'] == 'simple_6' and
                (item['model']['actual_returned'] != plan['model'] or
                 item['input_identity'].get('match') != 'exact_input_match')):
            raise ValueError('Simple Luna baseline is not a same-model exact-input match')
        matched[item['case_id']].append(item)
        matched_case_ids.add(item['case_id'])
    group_ids, case_strata, grouping = _group_mapping(root, cases)
    source_rows = _read(root / 'evaluation' / 'sources.json')
    source_by_post = defaultdict(list)
    for source in source_rows:
        if source.get('access_status') == 'accessible' and source.get('passage') and source.get('support_scope'):
            for pid in source['post_ids']:
                source_by_post[pid].append(source['source_id'])
    jobs_by_case = defaultdict(dict)
    for job in jobs.values():
        if job['case_id'] not in by_case or job['arm'] not in ARMS or job['arm'] in jobs_by_case[job['case_id']]:
            raise ValueError('Invalid or duplicate case/arm job')
        jobs_by_case[job['case_id']][job['arm']] = job
    rows = []
    for case in cases:
        cid = case['case_id']
        if digest(case['input']) != case['input_sha256']:
            raise ValueError('Dataset input identity changed')
        quality = case['human']['quality']
        if quality not in HUMAN_QUALITIES:
            raise ValueError('Unknown human quality')
        held = cid in plan['holds']
        arms = {}
        for arm in ARMS:
            job = jobs_by_case[cid].get(arm)
            arms[arm] = _outcome(results[job['key']]['result'] if job else None,
                                 planned=job is not None, held=held and arm == 'original_evidence')
        primary = [m for m in matched[cid] if m['experiment'] in
                   {'calibrated-luna-dev-v1', 'calibrated-luna-fresh-v1'}
                   and m['condition'] == 'simple_6' and m['repeat'] == 0]
        repeats = [m for m in matched[cid] if m['experiment'] == 'calibrated-luna-dev-v1'
                   and m['condition'] == 'simple_6' and m['repeat'] == 1]
        if len(primary) > 1 or len(repeats) > 1:
            raise ValueError('Duplicate simple_6 baseline repetition')
        baseline = _baseline(primary[0]) if primary else None
        row = {'case_id': cid, 'post_id': case['post_id'], 'input_sha256': case['input_sha256'],
               'group_id': group_ids[cid], 'raw_group_id': case.get('group_id'),
               'source_strata': case_strata[cid],
               'human_quality': quality, 'human': case['human'],
               'image_hold': plan['holds'].get(cid),
               'source_cohort': 'external_available' if source_by_post.get(case['post_id']) else 'original_only',
               'external_job_planned': 'external_evidence' in jobs_by_case[cid],
               'source_ids': sorted(source_by_post.get(case['post_id'], [])),
               'original_evidence': arms['original_evidence'], 'external_evidence': arms['external_evidence'],
               'simple_6_r0': baseline, 'simple_6_r1': _baseline(repeats[0]) if repeats else None,
               'other_baseline_trials': len(matched[cid]) - len(primary) - len(repeats)}
        row['original_vs_simple_6_r0'] = _delta(baseline, arms['original_evidence'],
            dimensions=('answer_quality', 'evidence_status', 'verdict'))
        row['simple_6_r0_vs_r1'] = _delta(baseline, row['simple_6_r1'],
            dimensions=('answer_quality', 'evidence_status', 'verdict'))
        row['original_vs_external'] = _delta(arms['original_evidence'], arms['external_evidence'],
            dimensions=('answer_quality', 'evidence_status', 'verdict'))
        if row['source_cohort'] == 'original_only' and arms['external_evidence']['state'] not in {'not_applicable', 'held'}:
            raise ValueError('External result without accessible source cohort')
        rows.append(row)
    rows.sort(key=lambda row: (row['post_id'], row['case_id']))
    posts = _summaries(rows)
    paired = [row for row in rows if row['external_job_planned']]
    baseline_paired = [row for row in rows if row['simple_6_r0'] is not None]
    cost_path = root / 'cost-reconciliation.json'
    cost_reconciliation = _read(cost_path) if cost_path.is_file() else None
    report = {'version': VERSION, 'dataset_id': _read(root / 'dataset' / 'manifest.json')['dataset_id'],
              'experiment_id': plan['experiment_id'], 'evaluation_complete': evaluation['complete'],
              'stop_reason': evaluation['stop_reason'], 'cost': evaluation['cost'],
              'baseline_snapshot': baseline_dir.name,
              'cost_basis': 'Evaluator accounted/estimated values use conservative reservation pricing; exact billed cost requires independent reconciliation.',
              'cost_reconciliation': cost_reconciliation,
              'coverage': {'cases': len(rows), 'posts': len(posts),
                           'answer_versions_beyond_first': len(rows) - len(posts),
                           'families': len({row['group_id'] for row in rows}),
                           'raw_dataset_families': len({row['raw_group_id'] for row in rows}),
                           'image_holds': sum(bool(row['image_hold']) for row in rows),
                           'original_jobs': sum('original_evidence' in jobs_by_case[row['case_id']] for row in rows),
                           'external_jobs': len(paired), 'completed_provider_calls': evaluation['completed_calls'],
                           'missing_provider_calls': evaluation['missing_calls'],
                           'matched_baseline_trials': len(matches),
                           'matched_baseline_cases': len(matched_case_ids),
                           'simple_6_r0_cases': len(baseline_paired),
                           'simple_6_r1_cases': sum(row['simple_6_r1'] is not None for row in rows)},
              'grouping': grouping, 'by_human_quality': _aggregate(rows),
              'historical_baselines': {'trials_by_experiment': dict(Counter(item['experiment'] for item in matches)),
                                        'trials_by_condition': dict(Counter(
                                            f"{item['experiment']}:{item['condition']}" for item in matches))},
              'source_cohorts': {cohort: {'cases': sum(row['source_cohort'] == cohort for row in rows),
                                          'posts': len({row['post_id'] for row in rows if row['source_cohort'] == cohort})}
                                 for cohort in ('external_available', 'original_only')},
              'source_strata': {stratum: {'cases': sum(stratum in row['source_strata'] for row in rows),
                                          'posts': len({row['post_id'] for row in rows
                                                        if stratum in row['source_strata']})}
                                for stratum in sorted({name for row in rows for name in row['source_strata']})},
              'paired_external': {'eligible_cases': len(paired),
                                  'completed_pairs': sum(row['original_vs_external']['status'] in {'same', 'changed'} for row in paired),
                                  'answer_changed_ids': [row['case_id'] for row in paired if
                                      'answer_quality' in row['original_vs_external'].get('changes', {})],
                                  'evidence_changed_ids': [row['case_id'] for row in paired if
                                      'evidence_status' in row['original_vs_external'].get('changes', {})],
                                  'combined_changed_ids': [row['case_id'] for row in paired if
                                      'verdict' in row['original_vs_external'].get('changes', {})],
                                  'incomplete_or_error_ids': [row['case_id'] for row in paired if
                                      row['original_vs_external']['status'] == 'incomplete_or_error']},
              'same_model_baseline': {'eligible_exact_input_r0_cases': len(baseline_paired),
                                      'completed_pairs': sum(row['original_vs_simple_6_r0']['status'] in
                                                             {'same', 'changed'} for row in baseline_paired),
                                      'answer_changed_ids': [row['case_id'] for row in baseline_paired if
                                          'answer_quality' in row['original_vs_simple_6_r0'].get('changes', {})],
                                      'evidence_changed_ids': [row['case_id'] for row in baseline_paired if
                                          'evidence_status' in row['original_vs_simple_6_r0'].get('changes', {})],
                                      'combined_changed_ids': [row['case_id'] for row in baseline_paired if
                                          'verdict' in row['original_vs_simple_6_r0'].get('changes', {})],
                                      'r1_variability_cases': [row['case_id'] for row in rows if row['simple_6_r1'] is not None],
                                      'r0_vs_r1_answer_changed_ids': [row['case_id'] for row in rows if
                                          'answer_quality' in row['simple_6_r0_vs_r1'].get('changes', {})],
                                      'r0_vs_r1_evidence_changed_ids': [row['case_id'] for row in rows if
                                          'evidence_status' in row['simple_6_r0_vs_r1'].get('changes', {})],
                                      'r0_vs_r1_combined_changed_ids': [row['case_id'] for row in rows if
                                          'verdict' in row['simple_6_r0_vs_r1'].get('changes', {})]},
              'known_human_answer_errors': {
                  arm: {'ready_failed_ids': [row['case_id'] for row in rows if row['human_quality'] == 'ready'
                                             and row[arm]['answer_quality'] == 'fail'],
                        'repair_passed_ids': [row['case_id'] for row in rows if row['human_quality'] == 'repair'
                                              and row[arm]['answer_quality'] == 'pass']}
                  for arm in ARMS},
              'limits': ['Cases sharing a post or family are correlated answer versions.',
                         'Source stratum counts overlap when a case appeared in multiple snapshots.',
                         'Human quality labels judge answers, not source-support status.',
                         'Historical simple_6 has the same model and exact input, but a different prompt/schema.',
                         'Repeat 1 is variability evidence, not an additional independent case.',
                         'Cap-stopped missing calls and technical errors are not answer failures.']}
    output.mkdir()
    write_json(output / 'rows.json', rows)
    write_json(output / 'posts.json', posts)
    write_json(output / 'report.json', report)
    inputs = {str(path): file_hash(path) for path in (root / 'dataset' / 'manifest.json',
              baseline_dir / 'manifest.json', root / 'evaluation' / 'plan.json',
              root / 'evaluation' / 'results-manifest.json')}
    if grouping['file_sha256']:
        inputs[str(root / 'grouping-audit.json')] = grouping['file_sha256']
    if cost_reconciliation is not None:
        inputs[str(cost_path)] = file_hash(cost_path)
    write_json(output / 'manifest.json', {'version': VERSION, 'code_sha256': file_hash(Path(__file__)),
        'inputs': inputs,
        'files': {name: file_hash(output / name) for name in ('rows.json', 'posts.json', 'report.json')}})
    return report


def prepare(root: Path, output: Path) -> dict:
    """Produce case/post-level analysis only from a completed, verified replay."""
    root, output = Path(root).resolve(), Path(output).resolve()
    if output.exists():
        raise FileExistsError('Refusing to overwrite an analysis')
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=output.name + '-preparing-', dir=output.parent) as scratch:
        stage = Path(scratch) / 'report'
        report = _prepare_in_place(root, stage)
        if output.exists():
            raise FileExistsError('Analysis destination appeared during preparation')
        stage.rename(output)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    report = prepare(args.root, args.output)
    print(json.dumps({'coverage': report['coverage'], 'cost': report['cost']}, indent=2))


if __name__ == '__main__':
    main()
