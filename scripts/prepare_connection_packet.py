"""Freeze issue #16's declared development packet without modifying source runs."""
import argparse
import json
import shutil
from pathlib import Path

from basedbench.pipeline.curation_corpus import file_hash, write_json


def prepare(spec, pilot, inspection, historical, output):
    if output.exists():
        raise FileExistsError('Packet already exists')
    selection = json.loads(spec.read_text())
    pilot_cases = {c['post_id']: c for c in json.loads((pilot / 'cases.json').read_text())}
    outcomes = {r['post_id']: r for r in json.loads((pilot / 'report.json').read_text())['outcomes']}
    notes = json.loads(inspection.read_text())['items']
    old_cases = {c['case_id']: c for c in json.loads((historical / 'cases.json').read_text())}
    old_results = {r['case_id']: r for r in json.loads((historical / 'report.json').read_text())['results']}
    (output / 'assets').mkdir(parents=True)
    cases = []
    for cid, group in selection['pilot_cases'].items():
        original, baseline = pilot_cases[cid], outcomes[cid]
        # Include a declined proposal when one exists; never manufacture a baseline answer.
        proposal = baseline['answer_stages'].get('generate', {}).get('explanation')
        case = {'case_id': cid, 'post_id': cid, 'group': group,
                'input': {**original['input'], 'explanation': baseline['candidate_answer'] or proposal or ''},
                'human': original['human'], 'development_hypothesis': notes[cid],
                'baseline': baseline, 'source': str(pilot), 'provenance': original['provenance']}
        cases.append(case)
        sha = case['input']['image_sha256']
        shutil.copyfile(pilot / 'assets' / sha, output / 'assets' / sha)
    for cid, group in selection['historical_cases'].items():
        original = old_cases[cid]
        cases.append({**original, 'group': group, 'baseline': old_results[cid], 'source': str(historical)})
        sha = original['input']['image_sha256']
        shutil.copyfile(historical / 'assets' / sha, output / 'assets' / sha)
    write_json(output / 'cases.json', cases)
    write_json(output / 'selection.json', selection)
    source_paths = [spec, inspection, *[p / name for p in (pilot, historical) for name in ('cases.json', 'plan.json', 'report.json')]]
    write_json(output / 'source-files.json', {str(p): file_hash(p) for p in source_paths})
    return len(cases)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--spec', type=Path, default=Path('docs/experiments/connection-packet-v1.json'))
    parser.add_argument('--pilot', type=Path, default=Path('data/backfill/admission-june20-26-v1'))
    parser.add_argument('--inspection', type=Path, default=Path('data/backfill/admission-june20-26-analysis-v1/assistant-inspection.json'))
    parser.add_argument('--historical', type=Path, default=Path('data/curation/answer-eval-v3'))
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(prepare(**vars(args)))
