"""Freeze actual human review revisions separately from assistant interpretation."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import fcntl
import json
from pathlib import Path
import shutil
import tempfile

from basedbench.calibration_review import CalibrationStore
from basedbench.pipeline.curation_corpus import digest, file_hash, write_json

VERSION = 'calibration-analysis-v1'


def freeze(packet: Path, output: Path, duplicate_pairs: list[dict]):
    if output.exists():
        raise FileExistsError('Use a new snapshot directory')
    store = CalibrationStore(packet)
    with (packet / 'events.jsonl').open() as handle:
        fcntl.flock(handle, fcntl.LOCK_SH)
        events = store._read_events(handle)
        handle.seek(0)
        raw = handle.read()
    latest = {e['post_id']: e for e in events if e['kind'] == 'feedback'}
    if set(latest) != set(store.cases):
        raise ValueError('Every case needs actual saved human feedback')
    parent = {pid: pid for pid in store.cases}
    def root(pid):
        while parent[pid] != pid:
            pid = parent[pid]
        return pid
    for pair in duplicate_pairs:
        a, b = pair['left'], pair['right']
        if a not in parent or b not in parent or pair['source'] != 'human_flag_then_assistant_image_inspection':
            raise ValueError('Invalid separately attributed duplicate evidence')
        parent[root(b)] = root(a)
    groups = {pid: root(pid) for pid in parent}
    counts = Counter(groups.values())
    cases, rows, pairs = [], [], []
    original_counts = defaultdict(Counter)
    for pid, c in store.cases.items():
        event = latest[pid]
        if any('quality_' + 'ab'[i] not in event['fields'] for i in range(len(c['input']['answers']))):
            raise ValueError('Missing answer judgment; partial feedback stays unresolved')
        judgments = []
        for i, answer in enumerate(c['input']['answers']):
            judgments.append({'source': answer['source'], 'text_sha256': digest(answer['text']),
                              'quality': event['fields']['quality_' + 'ab'[i]]})
        original = next(j for j in judgments if j['source'] == 'original')
        original_counts[c['stratum']][original['quality']] += 1
        inp = {k: c['input'][k] for k in ('explanation', 'comment_evidence', 'image_sha256')}
        cases.append({'case_id': pid, 'post_id': pid, 'input': inp, 'input_sha256': digest(inp),
                      'stratum': c['stratum'], 'original_quality': original['quality'],
                      'group_id': groups[pid], 'family_weight': 1 / counts[groups[pid]],
                      'human_event_id': event['event_id']})
        rows.append({'post_id': pid, 'stratum': c['stratum'], 'event': event,
                     'answers': judgments, 'group_id': groups[pid]})
        if len(judgments) == 2:
            alt = next(j for j in judgments if j['source'] != 'original')
            outcome = ('human_confirmed_repair' if original['quality'] == 'repair' and alt['quality'] == 'ready'
                       else 'both_acceptable' if original['quality'] == alt['quality'] == 'ready'
                       else 'neither_ready' if original['quality'] == alt['quality'] == 'repair'
                       else 'other_or_unresolved')
            pairs.append({'post_id': pid, 'outcome': outcome, 'original': original, 'alternative': alt,
                          'preference': event['fields'].get('preference')})
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix='.human-snapshot-', dir=output.parent))
    try:
        (staging / 'assets').mkdir()
        for c in cases:
            sha = c['input']['image_sha256']
            shutil.copyfile(packet / 'images' / sha, staging / 'assets' / sha)
        (staging / 'events.jsonl').write_text(raw)
        write_json(staging / 'cases.json', cases)
        write_json(staging / 'human-feedback.json', rows)
        write_json(staging / 'duplicate-inspection.json', duplicate_pairs)
        summary = {'case_count': len(cases), 'answer_judgments': sum(len(r['answers']) for r in rows),
                   'events': len(events), 'feedback_events': sum(e['kind'] == 'feedback' for e in events),
                   'comments_exposed_before_save': sum('comments' in e['exposed_before'] for e in latest.values()),
                   'original_by_stratum': {k: dict(v) for k, v in original_counts.items()},
                   'pair_outcomes': dict(Counter(p['outcome'] for p in pairs)), 'pairs': pairs,
                   'known_unique_families': len(set(groups.values())),
                   'limitations': ['Conditional exposed calibration sample, not a holdout.',
                     'Duplicate family overlay is separately attributed; all original judgments are preserved.',
                     'Human answer readiness does not certify three substantive supporting comments.',
                     'Repair/unclear labels and notes are retained literally, including ambiguous rationale.']}
        write_json(staging / 'summary.json', summary)
        manifest = {'version': VERSION, 'packet_id': store.manifest['packet_id'],
                    'packet_manifest_sha256': file_hash(packet / 'manifest.json'),
                    'code_sha256': file_hash(Path(__file__)),
                    'files': {str(p.relative_to(staging)): file_hash(p) for p in sorted(staging.rglob('*')) if p.is_file()}}
        manifest['snapshot_id'] = digest(manifest)
        write_json(staging / 'manifest.json', manifest)
        staging.rename(output)
        return summary
    finally:
        if staging.exists():
            shutil.rmtree(staging)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('packet', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--duplicate-pairs', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(freeze(args.packet, args.output, json.loads(args.duplicate_pairs.read_text())), indent=2))
