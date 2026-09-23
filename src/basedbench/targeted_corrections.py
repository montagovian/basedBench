"""Freeze four assistant proposals for human comparison without rewriting originals."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import shutil
import tempfile

from basedbench.calibration_review import CalibrationStore, RUBRIC, STATIC, VERSION as UI_VERSION
from basedbench.curation_review import make_server
from basedbench.materiality_review import human_anchors
from basedbench.pipeline.curation_corpus import digest, file_hash, write_json

VERSION = 'targeted-corrections-v1'
TARGETS = {'1u8acxi': 'grounding_correction', '1u9czw9': 'grounding_correction',
           '1u96sfo': 'interpretation', '1u1cqvx': 'interpretation'}


def prepare(packet: Path, snapshot: Path, proposals: Path, plan: Path, output: Path):
    if output.exists():
        raise FileExistsError('Use a new packet; never overwrite inputs or human feedback')
    source_manifest, anchors = human_anchors(packet, snapshot)
    store = CalibrationStore(packet)
    bundle = json.loads(proposals.read_text())
    if (bundle.get('version') != VERSION or bundle.get('author') != 'assistant_manual'
            or bundle.get('source_snapshot_id') != source_manifest['snapshot_id']
            or bundle.get('plan_sha256') != file_hash(plan)):
        raise ValueError('Proposal provenance does not match the frozen human inputs and plan')
    records = bundle['proposals']
    by_id = {r['post_id']: r for r in records}
    if len(records) != len(TARGETS) or set(by_id) != set(TARGETS):
        raise ValueError('Expected exactly the four planned cases, without replacements')
    for pid, proposal in by_id.items():
        case = store.cases[pid]
        original = next(a for a in case['input']['answers'] if a['source'] == 'original')
        if (proposal['input_sha256'] != case['input_sha256']
                or proposal['original_text_sha256'] != digest(original['text'])
                or not isinstance(proposal.get('text'), str) or not proposal['text'].strip()
                or proposal['text'].strip() == original['text'].strip()):
            raise ValueError('Proposal is empty, unchanged or attached to different evidence')
        comment_ids = set(re.findall(r'^ID: (\w+) \|', case['input']['comment_evidence'], re.M))
        if not set(proposal['supporting_comment_ids']) <= comment_ids:
            raise ValueError('Proposal cites a comment outside its original context')
        if file_hash(packet / 'images' / case['input']['image_sha256']) != case['input']['image_sha256']:
            raise ValueError('Original image bytes changed')
        if not isinstance(proposal.get('reference_notes'), str):
            raise ValueError('Reference notes must be explicitly supplied, even if blank')

    sources = {str(p.resolve()): file_hash(p) for p in
               [packet / 'manifest.json', snapshot / 'manifest.json', proposals, plan]}
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix='.targeted-corrections-', dir=output.parent))
    try:
        (staging / 'images').mkdir()
        cases = []
        for pid, stratum in TARGETS.items():
            original_case, proposal = store.cases[pid], by_id[pid]
            original = next(a for a in original_case['input']['answers'] if a['source'] == 'original')
            answers = [dict(original), {'source': VERSION + '/assistant_proposal', 'text': proposal['text']}]
            answers.sort(key=lambda a: digest([VERSION, pid, 'answer-order', a['source']]))
            inp = {k: original_case['input'][k] for k in ('image_sha256', 'explanation', 'comment_evidence')}
            if proposal['reference_notes']:
                inp['comment_evidence'] += ('\n\n=== Supplemental reference notes ===\n'
                    'Assistant-researched context, not original Reddit comments or extra Reddit supporters.\n'
                    + proposal['reference_notes'])
            inp['answers'] = answers
            shutil.copyfile(packet / 'images' / inp['image_sha256'], staging / 'images' / inp['image_sha256'])
            cases.append({'post_id': pid, 'input': inp, 'input_sha256': digest(inp),
                          'image_mime': original_case['image_mime'], 'group_id': original_case['group_id'],
                          'split': 'calibration', 'stratum': stratum,
                          'previous_feedback': [{'source_snapshot_id': source_manifest['snapshot_id']}],
                          'provenance': {'source_input_sha256': original_case['input_sha256'],
                              'original_comment_evidence_sha256': digest(original_case['input']['comment_evidence']),
                              'original_generation': original_case.get('provenance', {}),
                              'proposal_author': 'assistant_manual', 'previously_exposed': True}})
        cases.sort(key=lambda c: digest([VERSION, 'display', c['post_id']]))
        write_json(staging / 'cases.json', cases)
        write_json(staging / 'rubric.json', RUBRIC)
        write_json(staging / 'human-anchors.json', {'source_snapshot_id': source_manifest['snapshot_id'],
            'interpretation': 'Exact previous judgments; hidden during review and never replaced.', 'rows': anchors})
        write_json(staging / 'original-cases.json', [store.cases[pid] for pid in TARGETS])
        shutil.copyfile(proposals, staging / 'proposals.json')
        shutil.copyfile(plan, staging / 'plan.md')
        shutil.copytree(STATIC, staging / 'ui')
        html = (staging / 'ui/index.html').read_text()
        html = html.replace('Human calibration · round 2', 'Targeted explanation review')
        html = html.replace('50 cases: 20 targeted examples and 30 random cached examples, mixed together. This is calibration, not an untouched test set. Model identities and past opinions stay hidden.',
            'Four previously reviewed cases, with two answers each. Judge both as written. Earlier labels and answer authorship stay hidden; your earlier feedback remains intact. If competing readings prevent a usable reference, choose Cannot judge yet and explain briefly. Source support and suitability stay separate from answer readiness.')
        html = html.replace('Useful for an unfamiliar reference or a source-support question. Your draft is recorded before the reveal.',
            'Shows original comments and clearly separated reference notes where available. Reference notes are not additional Reddit supporters. Your draft is recorded before the reveal.')
        (staging / 'ui/index.html').write_text(html)
        if sources != {p: file_hash(Path(p)) for p in sources}:
            raise ValueError('Source files changed during preparation')
        manifest = {'schema_version': 'curation-review-packet-v1', 'purpose': UI_VERSION,
                    'study_version': VERSION, 'corpus_id': digest(sources), 'rubric_sha256': digest(RUBRIC),
                    'counts': {'grounding_correction': 2, 'interpretation': 2}, 'paired_cases': 4,
                    'seed': VERSION, 'new_api_calls': 0, 'cost_usd': 0, 'source_hashes': sources,
                    'implementation_hashes': {str(p.resolve()): file_hash(p) for p in
                        [Path(__file__), Path(__file__).with_name('calibration_review.py'), *sorted(STATIC.glob('*'))]},
                    'limitations': ['Exposed assistant-authored proposals, not validated repairs or an accuracy sample.',
                        'New original-answer judgments are contextual revisions, not replacements for prior events.',
                        'Source-support sufficiency and suitability remain separate; ambiguity may remain unresolved.',
                        'Supplemental reference notes do not establish Reddit consensus or portrait identities.'],
                    'files': {str(p.relative_to(staging)): file_hash(p) for p in sorted(staging.rglob('*')) if p.is_file()}}
        manifest['packet_id'] = digest(manifest)
        write_json(staging / 'manifest.json', manifest)
        CalibrationStore(staging)
        staging.rename(output)
        return manifest
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    build = sub.add_parser('prepare')
    for name in ('packet', 'snapshot', 'proposals', 'plan', 'output'):
        build.add_argument(name, type=Path)
    serve = sub.add_parser('serve')
    serve.add_argument('packet', type=Path)
    serve.add_argument('--port', type=int, default=9879)
    args = parser.parse_args()
    if args.command == 'prepare':
        result = prepare(args.packet, args.snapshot, args.proposals, args.plan, args.output)
        print(json.dumps({k: result[k] for k in ('packet_id', 'counts', 'paired_cases', 'new_api_calls')}, indent=2))
    else:
        server = make_server(args.packet, args.port, store=CalibrationStore(args.packet), static_dir=args.packet / 'ui')
        print(f'Targeted explanation review: http://127.0.0.1:{server.server_port}/', flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()


if __name__ == '__main__':
    main()
