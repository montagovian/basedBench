"""Protect human provenance and answer/evidence blinding in the correction packet."""
import json
from pathlib import Path

from PIL import Image
import pytest

from basedbench import calibration_analysis, calibration_review, targeted_corrections as review
from basedbench.curation_review import ReviewRequest
from basedbench.pipeline.curation_corpus import digest, file_hash, write_json


def hashes(directory):
    return {str(p.relative_to(directory)): file_hash(p) for p in directory.rglob('*') if p.is_file()}


@pytest.fixture
def sources(tmp_path):
    packet, snapshot = tmp_path / 'original', tmp_path / 'human'
    (packet / 'images').mkdir(parents=True)
    image = packet / 'images/temp.png'
    Image.new('RGB', (16, 16), 'green').save(image)
    sha = file_hash(image)
    image.rename(image.with_name(sha))
    cases = []
    for pid in review.TARGETS:
        inp = {'explanation': 'Original ' + pid, 'image_sha256': sha,
               'comment_evidence': 'ID: c1 | Score: 7\nSOURCE EVIDENCE',
               'answers': [{'source': 'original', 'text': 'Original ' + pid}]}
        cases.append({'post_id': pid, 'group_id': pid, 'input': inp, 'input_sha256': digest(inp),
                      'image_mime': 'image/png', 'stratum': 'audit', 'split': 'calibration', 'previous_feedback': []})
    write_json(packet / 'cases.json', cases)
    write_json(packet / 'rubric.json', calibration_review.RUBRIC)
    manifest = {'schema_version': 'curation-review-packet-v1', 'purpose': calibration_review.VERSION,
                'corpus_id': 'fixture', 'rubric_sha256': digest(calibration_review.RUBRIC), 'files': hashes(packet)}
    manifest['packet_id'] = digest(manifest)
    write_json(packet / 'manifest.json', manifest)
    store = calibration_review.CalibrationStore(packet)
    for pid in review.TARGETS:
        store.append(ReviewRequest(request_id=pid, post_id=pid, packet_id=manifest['packet_id'],
            input_sha256=store.cases[pid]['input_sha256'], fields={'quality_a': 'unclear'}, notes='PRIVATE human uncertainty'))
    calibration_analysis.freeze(packet, snapshot, [])
    plan = tmp_path / 'plan.md'
    plan.write_text('Fixed four-case plan')
    proposals = tmp_path / 'proposals.json'
    write_json(proposals, {'version': review.VERSION, 'author': 'assistant_manual',
        'source_snapshot_id': json.loads((snapshot / 'manifest.json').read_text())['snapshot_id'],
        'plan_sha256': file_hash(plan), 'proposals': [{
            'post_id': c['post_id'], 'input_sha256': c['input_sha256'],
            'original_text_sha256': digest(c['input']['explanation']),
            'text': 'Proposal ' + c['post_id'], 'supporting_comment_ids': ['c1'],
            'reference_notes': 'SUPPLEMENTAL evidence, not human gold'} for c in cases]})
    return packet, snapshot, proposals, plan


def test_preserve_originals_and_human_uncertainty_hide_sources_until_reveal(sources, tmp_path):
    before = [hashes(p) if p.is_dir() else file_hash(p) for p in sources]
    output = tmp_path / 'review'
    review.prepare(*sources, output)
    store = calibration_review.CalibrationStore(output)
    catalog = store.catalog()
    assert len(catalog['cases']) == 4 and all(len(c['answers']) == 2 for c in catalog['cases'])
    for hidden in ('PRIVATE', 'SUPPLEMENTAL', 'SOURCE EVIDENCE', 'assistant_manual', 'grounding_correction'):
        assert hidden not in json.dumps(catalog)
    assert all(c['latest'] is None and c['previously_discussed'] for c in catalog['cases'])
    assert [hashes(p) if p.is_dir() else file_hash(p) for p in sources] == before
    anchors = json.loads((output / 'human-anchors.json').read_text())['rows']
    assert all(a['event']['notes'] == 'PRIVATE human uncertainty' for a in anchors)
    c = catalog['cases'][0]
    result = store.append(ReviewRequest(request_id='reveal', post_id=c['post_id'],
        packet_id=catalog['packet_id'], input_sha256=c['input_sha256'],
        kind='reveal', reveal='comments', fields={'quality_a': 'unclear'}, notes='Still unsure'))
    assert 'SUPPLEMENTAL' in result['context']['comments']
    assert 'ID: c1 | Score: 7\nSOURCE EVIDENCE' in result['context']['comments']
    assert store.events()[0]['fields'] == {'quality_a': 'unclear'}
    assert store.events()[0]['notes'] == 'Still unsure'
    assert store.events()[0]['exposed_before'] == []
    with pytest.raises(FileExistsError):
        review.prepare(*sources, output)


@pytest.mark.parametrize('change', ['snapshot', 'plan', 'input', 'original', 'comment', 'selection', 'image'])
def test_reject_changed_or_unmatched_evidence(sources, tmp_path, change):
    packet, snapshot, proposals, plan = sources
    bundle = json.loads(proposals.read_text())
    if change == 'snapshot':
        bundle['source_snapshot_id'] = 'wrong'
    elif change == 'plan':
        plan.write_text('Changed scope')
    elif change == 'input':
        bundle['proposals'][0]['input_sha256'] = 'wrong'
    elif change == 'original':
        bundle['proposals'][0]['original_text_sha256'] = 'wrong'
    elif change == 'comment':
        bundle['proposals'][0]['supporting_comment_ids'] = ['invented']
    elif change == 'selection':
        bundle['proposals'].pop()
    elif change == 'image':
        next((packet / 'images').iterdir()).write_bytes(b'changed')
    write_json(proposals, bundle)
    with pytest.raises(ValueError):
        review.prepare(*sources, tmp_path / 'bad')
    assert not (tmp_path / 'bad').exists()
