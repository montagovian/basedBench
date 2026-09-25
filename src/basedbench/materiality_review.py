"""Reuse exact human anchors and prepare two unresolved materiality judgments offline."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import tempfile

from PIL import Image

from basedbench.calibration_review import CalibrationStore, RUBRIC, STATIC, VERSION as UI_VERSION
from basedbench.pipeline.connection_eval import verify_files
from basedbench.pipeline.curation_corpus import digest, file_hash, write_json

VERSION = 'materiality-boundary-v1'
UNRESOLVED = ('1u2ywbz', '1u8dptp')


def identified_manifest(directory, filename, identity):
    value = json.loads((directory / filename).read_text())
    if digest({k: v for k, v in value.items() if k != identity}) != value[identity]:
        raise ValueError('Source manifest identity changed')
    verify_files(directory, value['files'])
    return value


def human_anchors(packet, snapshot):
    """Join the frozen human event to its exact displayed texts, without interpreting it."""
    store = CalibrationStore(packet)
    manifest = identified_manifest(snapshot, 'manifest.json', 'snapshot_id')
    if (manifest['packet_id'] != store.manifest['packet_id']
            or manifest['packet_manifest_sha256'] != file_hash(packet / 'manifest.json')):
        raise ValueError('Human snapshot and review packet do not match')
    events = [json.loads(line) for line in (snapshot / 'events.jsonl').read_text().splitlines() if line.strip()]
    latest = {e['post_id']: e for e in events if e['kind'] == 'feedback'}
    feedback = json.loads((snapshot / 'human-feedback.json').read_text())
    if (len(feedback) != len(store.cases) or {r['post_id'] for r in feedback} != set(store.cases)
            or set(latest) != set(store.cases)):
        raise ValueError('Human snapshot does not cover the original packet')
    anchors = []
    for row in feedback:
        case, event = store.cases[row['post_id']], row['event']
        if (event != latest[row['post_id']] or event['kind'] != 'feedback'
                or event['packet_id'] != store.manifest['packet_id']
                or event['input_sha256'] != case['input_sha256']):
            raise ValueError('Human event provenance mismatch')
        answers = case['input']['answers']
        if len(row['answers']) != len(answers):
            raise ValueError('Human answer coverage mismatch')
        for slot, (answer, judgment) in enumerate(zip(answers, row['answers'])):
            if (judgment['text_sha256'] != digest(answer['text'])
                    or judgment['source'] != answer['source']
                    or judgment['quality'] != event['fields'].get('quality_' + 'ab'[slot])):
                raise ValueError('Human answer identity or judgment mismatch')
        anchors.append({**row, 'answers': [{**judgment, 'text': answer['text']}
                                         for answer, judgment in zip(answers, row['answers'])]})
    return manifest, anchors


def prepare(packet: Path, snapshot: Path, source: Path, output: Path):
    if output.exists():
        raise FileExistsError('Use a new packet directory; never replace human feedback')
    human_manifest, anchors = human_anchors(packet, snapshot)
    plan = identified_manifest(source, 'plan.json', 'experiment_id')
    if plan['version'] != 'capacity-comparison-v1':
        raise ValueError('Expected the completed capacity comparison')
    verify_files(source, json.loads((source / 'results-manifest.json').read_text()))
    rows = json.loads((source / 'cases.json').read_text())
    by_id = {c['case_id']: c for c in rows}
    if len(by_id) != len(rows) or not set(UNRESOLVED) <= set(by_id):
        raise ValueError('Missing or duplicate unresolved identities')
    human_ids = {r['post_id'] for r in anchors}
    human_groups = {r['group_id'] for r in anchors}
    selected = [by_id[pid] for pid in UNRESOLVED]
    if (len({c['group_id'] for c in selected}) != len(selected)
            or any(c.get('original_quality') is not None or c['case_id'] in human_ids
                   or c['group_id'] in human_groups for c in selected)):
        raise ValueError('Unresolved review must not relabel an existing human answer or family')
    sources = {'human_packet': packet / 'manifest.json', 'human_snapshot': snapshot / 'manifest.json',
               'capacity_plan': source / 'plan.json', 'capacity_results': source / 'results-manifest.json'}
    source_hashes = {key: file_hash(path) for key, path in sources.items()}
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix='.materiality-', dir=output.parent))
    try:
        (staging / 'images').mkdir()
        cases = []
        for c in selected:
            sha = c['input']['image_sha256']
            image = source / 'assets' / sha
            if file_hash(image) != sha:
                raise ValueError('Source image identity mismatch')
            with Image.open(image) as img:
                mime = Image.MIME[img.format]
                img.verify()
            shutil.copyfile(image, staging / 'images' / sha)
            inp = {k: c['input'][k] for k in ('image_sha256', 'explanation', 'comment_evidence')}
            inp['answers'] = [{'source': 'original', 'text': inp['explanation']}]
            cases.append({'post_id': c['case_id'], 'input': inp, 'input_sha256': digest(inp),
                          'image_mime': mime, 'split': 'calibration', 'stratum': 'targeted_boundary',
                          'group_id': c['group_id'], 'previous_feedback': [],
                          'provenance': {'source_experiment_id': plan['experiment_id'],
                                         'source_input_sha256': digest(c['input']),
                                         'previous_model_and_assistant_exposure': True}})
        cases.sort(key=lambda c: digest([VERSION, 'display', c['post_id']]))
        write_json(staging / 'cases.json', cases)
        write_json(staging / 'rubric.json', RUBRIC)
        write_json(staging / 'human-anchors.json', {'source_snapshot_id': human_manifest['snapshot_id'],
                   'interpretation': 'Literal human judgments and notes; no inferred defect categories.',
                   'rows': anchors})
        write_json(staging / 'selection.json', {
            'selected_ids': list(UNRESOLVED), 'selection_author': 'assistant',
            'rule': 'Two already exposed, human-unlabeled cases probing whether existing decoding is adequate or an omitted phrase is material. Original answers only; no generated alternatives or desired labels.',
            'not_selected': 'Existing human judgments remain anchors. Other stress cases stay unadjudicated; this is not an archive-wide queue.',
            'human_labels_available': False, 'new_api_calls': 0, 'cost_usd': 0})
        if source_hashes != {key: file_hash(path) for key, path in sources.items()}:
            raise ValueError('Source manifests changed during preparation')
        manifest = {
            'schema_version': 'curation-review-packet-v1', 'purpose': UI_VERSION, 'study_version': VERSION,
            'corpus_id': digest(source_hashes), 'rubric_sha256': digest(RUBRIC),
            'counts': {'targeted_boundary': len(cases)}, 'paired_cases': 0,
            'existing_human_cases': len(anchors), 'existing_human_answers': sum(len(r['answers']) for r in anchors),
            'new_api_calls': 0, 'cost_usd': 0, 'source_hashes': source_hashes,
            'implementation_hashes': {p.name: file_hash(p) for p in [Path(__file__), *sorted(STATIC.glob('*'))]},
            'limitations': ['Selected exposed development cases, not a holdout or accuracy sample.',
                            'Assistant selection is not a human judgment.',
                            'Existing human anchors, model opinions and case selection reasons are hidden during review.',
                            'Source-support sufficiency and suitability remain separate from explanation adequacy.'],
            'files': {str(p.relative_to(staging)): file_hash(p) for p in sorted(staging.rglob('*')) if p.is_file()}}
        manifest['packet_id'] = digest(manifest)
        write_json(staging / 'manifest.json', manifest)
        CalibrationStore(staging)
        staging.rename(output)
        return manifest
    finally:
        if staging.exists():
            shutil.rmtree(staging)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('packet', type=Path)
    p.add_argument('snapshot', type=Path)
    p.add_argument('source', type=Path)
    p.add_argument('output', type=Path)
    args = p.parse_args()
    result = prepare(args.packet, args.snapshot, args.source, args.output)
    print(json.dumps({k: result[k] for k in ('packet_id', 'counts', 'existing_human_cases', 'existing_human_answers', 'new_api_calls')}, indent=2))
