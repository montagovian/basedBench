"""Summarize a frozen human-review journal without rewriting any judgment."""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path

from basedbench.pipeline.curation_corpus import digest, file_hash

METHODS = ('order', 'rank', 'collate')
SLOTS = ('A', 'B', 'C')


def signature(pack):
    return [(e['comment_id'], e['start'], e['end'], e['text']) for e in pack['excerpts']]


def aggregate(rows):
    reviewed = [r for r in rows if r['feedback'] is not None]
    best = Counter(r['choice_method'] for r in reviewed)
    unique = Counter(r['choice_method'] for r in reviewed if len(r['chosen_identical_methods']) == 1)
    shared = Counter('+'.join(r['chosen_identical_methods']) for r in reviewed
                     if len(r['chosen_identical_methods']) > 1)
    ratings = {}
    for method in METHODS:
        values = [r['ratings_by_method'][method] for r in reviewed
                  if method in r['ratings_by_method']]
        ratings[method] = {key: dict(Counter(v[key] for v in values)) for key in ('clue', 'misleading')}
        ratings[method]['rated_cases'] = len(values)
    return {'planned': len(rows), 'reviewed': len(reviewed),
            'missing': [r['review_id'] for r in rows if r['feedback'] is None],
            'button_choices': {key: best[key] for key in (*METHODS, 'tie', 'unsure')},
            'decisive_button_choices': sum(best[m] for m in METHODS),
            'unique_list_choices': {m: unique[m] for m in METHODS},
            'shared_identical_choices': dict(shared), 'ratings': ratings}


def analyze(cases, events, packet_id):
    by_id = {c['review_id']: c for c in cases}
    if len(by_id) != len(cases):
        raise ValueError('Duplicate review case')
    states = {rid: {'revision': None, 'revealed': False, 'comments': False,
                    'reference': False, 'eligible': None, 'latest': None,
                    'feedback_count': 0, 'post_reveal_count': 0} for rid in by_id}
    ids, requests = set(), set()
    for event in events:
        rid = event['review_id']
        if rid not in states or event['packet_id'] != packet_id:
            raise ValueError('Event belongs to another packet or case')
        if event['event_id'] in ids or event['request_id'] in requests:
            raise ValueError('Duplicate journal event or request')
        ids.add(event['event_id'])
        requests.add(event['request_id'])
        state = states[rid]
        if event['base_revision'] != state['revision']:
            raise ValueError('Broken feedback revision chain')
        kind = event['kind']
        if kind == 'feedback':
            for field, expected in [('methods_revealed_before', state['revealed']),
                                    ('source_opened_before', state['comments']),
                                    ('reference_opened_before', state['reference'])]:
                if event[field] is not expected:
                    raise ValueError('Feedback exposure does not match journal chronology')
            available = {s for s, p in by_id[rid]['packs'].items() if p['status'] == 'completed'}
            if set(event['ratings']) != available:
                raise ValueError('Rating coverage differs from available packs')
            if event['most_useful'] not in available | {'tie', 'unsure'}:
                raise ValueError('Invalid best-pack choice')
            for rating in event['ratings'].values():
                if (set(rating) != {'clue', 'misleading'} or
                    rating['clue'] not in {'yes', 'partly', 'no', 'unsure'} or
                    rating['misleading'] not in {'yes', 'no', 'unsure'}):
                    raise ValueError('Invalid rating')
            state['revision'], state['latest'] = event['event_id'], event
            state['feedback_count'] += 1
            if state['revealed']:
                state['post_reveal_count'] += 1
            else:
                state['eligible'] = event
        elif kind == 'reveal':
            if state['revision'] is None or state['revealed']:
                raise ValueError('Invalid method reveal chronology')
            state['revealed'] = True
        elif kind == 'context' and event['source'] in ('comments', 'reference'):
            state[event['source']] = True
        else:
            raise ValueError('Unknown event kind')

    rows = []
    for case in cases:
        if (set(case['methods']) != set(SLOTS) or set(case['methods'].values()) != set(METHODS)
                or case['sample_kind'] not in ('sampled', 'diagnostic')):
            raise ValueError('Invalid case mapping or stratum')
        state = states[case['review_id']]
        event = state['eligible']
        choice = event['most_useful'] if event else None
        identical = sorted(case['methods'][s] for s in SLOTS
                           if choice in SLOTS and case['packs'][s]['status'] == 'completed'
                           and signature(case['packs'][s]) == signature(case['packs'][choice]))
        rows.append({'review_id': case['review_id'], 'family_id': case['family_id'],
                     'sample_kind': case['sample_kind'], 'feedback': event,
                     'choice_method': case['methods'].get(choice, choice),
                     'chosen_identical_methods': identical,
                     'ratings_by_method': {case['methods'][s]: value for s, value in event['ratings'].items()} if event else {},
                     'feedback_count': state['feedback_count'],
                     'post_reveal_feedback_count': state['post_reveal_count'],
                     'latest_feedback': state['latest'], 'methods_revealed': state['revealed']})
    strata = {kind: aggregate([r for r in rows if r['sample_kind'] == kind])
              for kind in ('sampled', 'diagnostic')}
    sampled = strata['sampled']
    comparisons = {}
    for method in ('rank', 'collate'):
        metrics, control = sampled['ratings'][method], sampled['ratings']['order']
        comparisons[method] = {
            'chosen_at_least_once': sampled['button_choices'][method] > 0,
            'chosen_at_least_twice_order': sampled['button_choices'][method] >= 2 * sampled['button_choices']['order'],
            'full_clue_count_no_lower': metrics['clue'].get('yes', 0) >= control['clue'].get('yes', 0),
            'misleading_count_no_higher': metrics['misleading'].get('yes', 0) <= control['misleading'].get('yes', 0),
            'equal_rating_coverage': metrics['rated_cases'] == control['rated_cases']}
    sufficient = sampled['decisive_button_choices'] >= 8
    screen = {'sampled_decisive_required': 8, 'sampled_decisive_observed': sampled['decisive_button_choices'],
              'sufficient_preferences': sufficient, 'arm_checks': comparisons,
              'met': sufficient and any(all(checks.values()) for checks in comparisons.values()),
              'interpretation': 'Original button-based rule; identical selected lists are separately reported and are not unique wins.'}
    return {'packet_id': packet_id, 'events': len(events),
            'event_kinds': dict(Counter(e['kind'] for e in events)),
            'strata': strata, 'all_reviewed_descriptive_only': aggregate(rows),
            'predeclared_screen': screen, 'cases': rows}


def from_snapshot(root):
    root = Path(root)
    manifest = json.loads((root / 'snapshot.json').read_text())
    if manifest['snapshot_id'] != digest({k: v for k, v in manifest.items() if k != 'snapshot_id'}):
        raise ValueError('Snapshot identity changed')
    for relative, sha in manifest['files'].items():
        path = (root / relative).resolve()
        if not path.is_relative_to(root.resolve()) or file_hash(path) != sha:
            raise ValueError('Frozen review artifact changed')
    packet = json.loads((root / 'review-manifest.json').read_text())
    if (packet['packet_id'] != digest({k: v for k, v in packet.items() if k != 'packet_id'})
            or packet['cases_sha256'] != file_hash(root / 'review-cases.json')):
        raise ValueError('Review packet changed')
    cases = json.loads((root / 'review-cases.json').read_text())
    events = [json.loads(line) for line in (root / 'events.jsonl').read_text().splitlines() if line.strip()]
    result = analyze(cases, events, packet['packet_id'])
    result['snapshot_id'] = manifest['snapshot_id']
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = from_snapshot(args.snapshot)
    if args.output:
        with args.output.open('x') as stream:
            stream.write(json.dumps(result, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps({key: value for key, value in result.items() if key != 'cases'}, indent=2))


if __name__ == '__main__':
    main()
