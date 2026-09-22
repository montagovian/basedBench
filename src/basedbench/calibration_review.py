"""Prepare an offline explanation-calibration packet; never relabel source data."""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import re
import shutil
import sqlite3
import tempfile

from PIL import Image

from basedbench.curation_review import ReviewRequest, ReviewStore, make_server
from basedbench.pipeline.curation_corpus import _historical_input, digest, file_hash, write_json

VERSION = 'explanation-calibration-v1'
STATIC = Path(__file__).with_name('calibration_static')
QUALITY = {'ready': 'Good enough to grade', 'repair': 'Material defect', 'unclear': 'Cannot judge yet'}
REASONS = {'wrong': 'Wrong connection or reference', 'missing': 'Missing an essential connection',
           'unsupported': 'Unsupported interpretation', 'optional': 'Optional improvement only',
           'evidence': 'Too little source support', 'other': 'Other / explain in note'}
RUBRIC = {'version': VERSION, 'principles': [
    'Would this explanation let you grade whether another model got the same joke?',
    'A short answer can be ready. Extra detail, difficulty and a theory of why humor works are not required.',
    'Both answers can be acceptable. A preference for one does not make the other defective.',
    'If there is a material defect, name the missing or wrong connection. Optional improvements remain optional.',
    'Source-support uncertainty can be recorded separately from answer correctness. Leave unresolved judgments unresolved.',
], 'fields': {**{f'quality_{slot}': {'label': f'Answer {slot.upper()}', 'options': QUALITY} for slot in ('a', 'b')},
              **{f'reason_{slot}': {'label': 'Optional reason', 'options': REASONS} for slot in ('a', 'b')},
              'preference': {'label': 'Optional preference', 'options': {'a': 'Prefer A', 'b': 'Prefer B', 'equal': 'No preference'}}}}


def sample_groups(rows, count, seed, blocked):
    """Choose by frozen hash order, at most one member per known family."""
    used = set(blocked)
    selected = []
    for row in sorted(rows, key=lambda r: digest([seed, 'random', r['post_id']])):
        if row['group_id'] not in used:
            selected.append(row)
            used.add(row['group_id'])
        if len(selected) == count:
            return selected
    raise ValueError(f'Only {len(selected)} eligible distinct groups; need {count}')


def family_groups(records, edges, families):
    parents = {r['post_id']: r['post_id'] for r in records}

    def root(pid):
        parents.setdefault(pid, pid)
        while parents[pid] != pid:
            parents[pid] = parents[parents[pid]]
            pid = parents[pid]
        return pid

    def union(a, b):
        a, b = sorted((root(a), root(b)))
        parents[b] = a

    seen = {}
    for row in records:
        keys = [('image', row.get('image', {}).get('pixel_sha256'))]
        if row.get('text_source') in {'explanation', 'stored_explanation'}:
            keys.append(('text', ' '.join(row['text'].casefold().split())))
        for key in keys:
            if key[1]:
                if key in seen:
                    union(row['post_id'], seen[key])
                seen[key] = row['post_id']
    for edge in edges:
        union(edge['left'], edge['right'])  # Candidate links are conservative exclusions, not gold duplicates.
    for family in families:
        for pid in family[1:]:
            union(family[0], pid)
    return {pid: root(pid) for pid in parents}


def prepare(root: Path, output: Path, *, random_count=30, seed=VERSION):
    if output.exists():
        raise FileExistsError('Use a new packet directory; feedback and frozen inputs must be preserved')
    root = root.resolve()
    source_hashes = {}

    def read(relative):
        path = root / relative
        source_hashes[relative] = file_hash(path)
        return json.loads(path.read_text())

    targets = read('data/backfill/claim-eval-v1/cases.json')
    if len(targets) != 20:
        raise ValueError('Expected the frozen 20-case targeted comparison')
    alternatives = {}
    # Latest valid proposed repair wins; a failed verification is not human rejection.
    for directory in ('connection-eval-v1', 'connection-schema-v2', 'claim-eval-v1'):
        for result in read(f'data/backfill/{directory}/results.json'):
            repair = result['stages'].get('repair', {})
            if repair.get('status') == 'proposed' and isinstance(repair.get('explanation'), str):
                alternatives[result['post_id']] = {'text': repair['explanation'],
                    'source': f'{directory}/repair', 'workflow_status': result['status']}

    audit = read('data/backfill/duplicate-audit-v1/inputs.json')
    edges = read('data/backfill/duplicate-audit-v1/report.json')['edges']
    families = read('data/backfill/duplicate-audit-v1/known_families.json')
    groups = family_groups(audit, edges, families)
    database = root / 'data/basedbench.db'
    source_hashes['data/basedbench.db'] = file_hash(database)
    conn = sqlite3.connect(database.as_uri() + '?mode=ro', uri=True)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute('PRAGMA query_only = ON')
        conn.execute('BEGIN')
        # Cached answers outside the release's date coverage; no human review row.
        rows = [dict(r) for r in conn.execute("""
            SELECT m.*, g.explanation, g.created_at AS generated_at, g.consensus_model
            FROM memes m JOIN ground_truths g USING(post_id) LEFT JOIN reviews r USING(post_id)
            WHERE m.created_utc >= '2026-06-07' AND r.post_id IS NULL
              AND length(trim(g.explanation)) > 0 ORDER BY m.post_id
        """)]
        blocked_ids = {r[0] for r in conn.execute('SELECT post_id FROM reviews UNION SELECT post_id FROM consensus_eval_items UNION SELECT post_id FROM consensus_regression UNION SELECT post_id FROM gate_feedback')}
        blocked_ids.update(c['post_id'] for c in targets)
        candidates = {r['post_id'] for r in rows}
        exposure_files = []
        names = {'cases.json', 'plan.json', 'events.jsonl', 'reassessments.jsonl', 'inspection.json',
                 'assistant-inspection.json', 'selection.json', 'decisions.jsonl', 'components.jsonl'}
        pattern = re.compile(r'(?<![a-zA-Z0-9])(' + '|'.join(map(re.escape, sorted(candidates))) + r')(?![a-zA-Z0-9])') if candidates else None
        for directory in ('data/curation', 'data/backfill', 'docs'):
            for path in sorted((root / directory).rglob('*')):
                if path.is_file() and (path.name in names or path.suffix == '.md'):
                    if output.resolve() == path or output.resolve() in path.parents:
                        continue
                    matches = set(pattern.findall(path.read_text())) if pattern else set()
                    relative = str(path.relative_to(root))
                    exposure_files.append({'path': relative, 'sha256': file_hash(path), 'matched_ids': sorted(matches)})
                    blocked_ids.update(matches)
        blocked = {groups.get(pid, pid) for pid in blocked_ids}
        eligibility, eligible = [], []
        for row in rows:
            pid = row['post_id']
            group = groups.get(pid, pid)
            reason = 'previous_review_or_exposure_family' if group in blocked else None
            image_path = Path(row['local_image_path'] or '')
            if not image_path.is_absolute():
                image_path = root / image_path
            if not reason:
                try:
                    with Image.open(image_path) as img:
                        img.verify()
                except (OSError, ValueError):
                    reason = 'unavailable_image'
            calls = list(conn.execute("""SELECT * FROM llm_calls WHERE post_id=? AND role='consensus'
                AND verdict='consensus' AND error IS NULL
                AND abs(julianday(created_at)-julianday(?))*86400 < 2 ORDER BY id""", (pid, row['generated_at'])))
            model_input = None
            if not reason:
                try:
                    if len(calls) != 1:
                        raise ValueError('Ambiguous generation')
                    model_input = _historical_input(dict(calls[0]))
                    if model_input['explanation'] != row['explanation'].strip():
                        raise ValueError('Stored explanation differs')
                except (ValueError, KeyError, TypeError):
                    reason = 'unrecoverable_generation_context'
            eligibility.append({'post_id': pid, 'group_id': group, 'eligible': reason is None, 'exclusion': reason})
            if not reason:
                eligible.append({'post_id': pid, 'group_id': group, 'input': model_input,
                    'image_path': image_path, 'provenance': {'created_utc': row['created_utc'],
                    'subreddit': row['subreddit'], 'generation_model': row['consensus_model'],
                    'generation_call_id': calls[0]['id'], 'generation_record_sha256': digest(dict(calls[0]))}})
        selected = sample_groups(eligible, random_count, seed, blocked)
    finally:
        conn.close()
    if file_hash(database) != source_hashes['data/basedbench.db']:
        raise ValueError('Database changed during packet preparation; retry using a stable snapshot')

    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix='.calibration-', dir=output.parent))
    try:
        (staging / 'images').mkdir()
        cases = []
        sources = [dict(post_id=c['post_id'], group_id=groups.get(c['post_id'], c['post_id']),
                        input=c['input'], image_path=root / 'data/backfill/claim-eval-v1/assets' / c['input']['image_sha256'],
                        provenance=c['provenance'], stratum='targeted', human=c.get('human', {})) for c in targets]
        sources += [dict(r, stratum='random_cached') for r in selected]
        for row in sources:
            pid = row['post_id']
            image_path = row['image_path']
            sha = file_hash(image_path)
            with Image.open(image_path) as img:
                mime = Image.MIME[img.format]
            shutil.copyfile(image_path, staging / 'images' / sha)
            answers = [{'text': row['input']['explanation'], 'source': 'original'}]
            alt = alternatives.get(pid) if row['stratum'] == 'targeted' else None
            if alt and alt['text'].strip() != answers[0]['text'].strip():
                answers.append(alt)
            answers.sort(key=lambda a: digest([seed, pid, 'answer-order', a['source']]))
            model_input = {**row['input'], 'image_sha256': sha, 'answers': answers}
            cases.append({'post_id': pid, 'input': model_input, 'input_sha256': digest(model_input),
                          'group_id': row['group_id'], 'split': 'calibration', 'stratum': row['stratum'],
                          'image_mime': mime, 'provenance': row['provenance'],
                          'historical_human_feedback': row.get('human', {}), 'previous_feedback': []})
        cases.sort(key=lambda c: digest([seed, 'display', c['post_id']]))
        selection = {'seed': seed, 'eligibility': eligibility, 'exposure_scan': exposure_files,
                     'random_ids': [r['post_id'] for r in selected], 'targeted_ids': [c['post_id'] for c in targets],
                     'rule': 'Frozen 20 targeted cases plus hash-sampled distinct known groups from cached, unreviewed June 7+ answer-bearing posts. Exclude prior review/eval/exposure families; require valid cached image and uniquely recoverable generation context. No quality inspection or replacement after selection.'}
        write_json(staging / 'cases.json', cases)
        write_json(staging / 'rubric.json', RUBRIC)
        write_json(staging / 'selection.json', selection)
        manifest = {'schema_version': 'curation-review-packet-v1', 'purpose': VERSION,
                    'corpus_id': digest(source_hashes), 'rubric_sha256': digest(RUBRIC),
                    'counts': dict(Counter(c['stratum'] for c in cases)),
                    'paired_cases': sum(len(c['input']['answers']) == 2 for c in cases),
                    'random_pool': {'cached_answer_rows': len(rows), 'eligible': len(eligible),
                                    'exclusions': dict(Counter(r['exclusion'] for r in eligibility if r['exclusion']))},
                    'new_api_calls': 0, 'cost_usd': 0, 'source_hashes': source_hashes,
                    'implementation_hashes': {str(p.relative_to(root)): file_hash(p)
                        for p in [Path(__file__), *sorted(STATIC.glob('*'))]},
                    'limitations': ['Calibration, not an untouched test set.',
                        'Random sample is conditional on cached successful legacy generation and assets; it does not estimate full admission yield.',
                        'Duplicate retrieval exposure persists; known families are incomplete.',
                        'Targeted assistant hypotheses are not human gold. Historical feedback remains in its original source.',
                        'A/B source identities and strata are hidden during review; comments can be revealed with a logged draft checkpoint.'],
                    'files': {p.relative_to(staging).as_posix(): file_hash(p) for p in sorted(staging.rglob('*')) if p.is_file()}}
        manifest['packet_id'] = digest(manifest)
        write_json(staging / 'manifest.json', manifest)
        staging.rename(output)
        return manifest
    finally:
        if staging.exists():
            shutil.rmtree(staging)


class CalibrationStore(ReviewStore):
    def __init__(self, packet):
        super().__init__(packet)
        if self.manifest.get('purpose') != VERSION or self.rubric != RUBRIC:
            raise ValueError('Not an explanation-calibration packet')
        for c in self.cases.values():
            if not 1 <= len(c['input']['answers']) <= 2:
                raise ValueError('Expected one or two answers')

    def question_copy(self):
        return None  # The complete wording is frozen in this packet's rubric.

    def catalog(self):
        events = self.events()
        return {'packet_id': self.manifest['packet_id'], 'token': self.token, 'rubric': self.rubric,
                'cases': [{'post_id': c['post_id'], 'input_sha256': c['input_sha256'],
                           'image_url': '/image/' + c['post_id'],
                           'answers': [a['text'] for a in c['input']['answers']],
                           **self.state(c['post_id'], events)} for c in self.cases.values()]}

    def context(self, pid, reveal):
        if reveal != 'comments':
            raise ValueError('Only source comments are available during this calibration')
        return {'comments': self.cases[pid]['input']['comment_evidence']}

    def append(self, request: ReviewRequest):
        if request.reveal not in (None, 'comments'):
            raise ValueError('Model opinions are hidden during calibration')
        case = self.cases.get(request.post_id)
        if case and len(case['input']['answers']) == 1 and set(request.fields) & {'quality_b', 'reason_b', 'preference'}:
            raise ValueError('This case has only one answer')
        return super().append(request)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    build = sub.add_parser('prepare')
    build.add_argument('output', type=Path)
    build.add_argument('--root', type=Path, default=Path.cwd())
    web = sub.add_parser('serve')
    web.add_argument('packet', type=Path)
    web.add_argument('--port', type=int, default=8767)
    args = parser.parse_args()
    if args.command == 'prepare':
        result = prepare(args.root, args.output)
        print(json.dumps({k: result[k] for k in ('packet_id', 'counts', 'paired_cases', 'random_pool', 'new_api_calls')}))
    else:
        server = make_server(args.packet, args.port, store=CalibrationStore(args.packet), static_dir=STATIC)
        print(f'Explanation calibration: http://127.0.0.1:{server.server_port}/', flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()


if __name__ == '__main__':
    main()
