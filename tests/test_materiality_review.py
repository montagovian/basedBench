"""A new review must preserve exact human judgments and keep model hypotheses hidden."""
import json
from pathlib import Path

from PIL import Image
import pytest

from basedbench import calibration_review, calibration_analysis, materiality_review as review
from basedbench.curation_review import ReviewRequest
from basedbench.pipeline.curation_corpus import digest, file_hash, write_json


def hashes(directory):
    return {str(p.relative_to(directory)): file_hash(p) for p in directory.rglob('*') if p.is_file()}


def seal(directory, name, identity, value):
    value = {k: v for k, v in value.items() if k not in {identity, 'files'}}
    value['files'] = {k: v for k, v in hashes(directory).items() if k != name}
    value[identity] = digest(value)
    write_json(directory / name, value)


@pytest.fixture
def sources(tmp_path):
    packet, snapshot, source = [tmp_path / name for name in ('human-packet', 'human-snapshot', 'model-source')]
    (packet / 'images').mkdir(parents=True)
    image = packet / 'images' / 'temporary.png'
    Image.new('RGB', (16, 16), 'green').save(image)
    sha = file_hash(image)
    image.rename(image.with_name(sha))
    cases = []
    for pid in ('accepted-pair', 'qualified-repair'):
        answers = [{'source': 'original', 'text': 'Short original ' + pid}]
        if pid == 'accepted-pair':
            answers.append({'source': 'prior-repair', 'text': 'Longer alternative'})
        inp = {'image_sha256': sha, 'explanation': answers[0]['text'],
               'comment_evidence': 'Original source comments', 'answers': answers}
        cases.append({'post_id': pid, 'input': inp, 'input_sha256': digest(inp), 'group_id': pid,
                      'image_mime': 'image/png', 'split': 'calibration', 'stratum': 'targeted', 'previous_feedback': []})
    write_json(packet / 'cases.json', cases)
    write_json(packet / 'rubric.json', calibration_review.RUBRIC)
    seal(packet, 'manifest.json', 'packet_id', {
        'schema_version': 'curation-review-packet-v1', 'purpose': calibration_review.VERSION,
        'corpus_id': 'test-fixture', 'rubric_sha256': digest(calibration_review.RUBRIC)})
    store = calibration_review.CalibrationStore(packet)
    for pid, fields, note in [('accepted-pair', {'quality_a':'ready', 'quality_b':'ready', 'preference':'b'}, ''),
                              ('qualified-repair', {'quality_a':'repair'}, 'Not sure about benchmark fit')]:
        store.append(ReviewRequest(request_id=pid, post_id=pid, packet_id=store.manifest['packet_id'],
                                   input_sha256=store.cases[pid]['input_sha256'], fields=fields, notes=note))
    calibration_analysis.freeze(packet, snapshot, [])
    (source / 'assets').mkdir(parents=True)
    (source / 'assets' / sha).write_bytes((packet / 'images' / sha).read_bytes())
    rows = [{'case_id': pid, 'group_id': pid,
             'input': {'image_sha256': sha, 'explanation': 'Unreviewed explanation ' + pid,
                       'comment_evidence': 'Unreviewed source comments'}} for pid in review.UNRESOLVED]
    write_json(source / 'cases.json', rows)
    write_json(source / 'results.json', {'opinion': 'Hidden model verdict'})
    write_json(source / 'results-manifest.json', {'results.json': file_hash(source / 'results.json')})
    seal(source, 'plan.json', 'experiment_id', {'version': 'capacity-comparison-v1'})
    return packet, snapshot, source


def test_prepare_preserves_human_texts_qualifiers_preference_and_all_sources(sources, tmp_path):
    before = [hashes(p) for p in sources]
    output = tmp_path / 'boundary'
    result = review.prepare(*sources, output)
    anchors = json.loads((output / 'human-anchors.json').read_text())['rows']
    assert [a['quality'] for a in anchors[0]['answers']] == ['ready', 'ready']
    assert anchors[0]['event']['fields']['preference'] == 'b'
    assert anchors[1]['event']['notes'] == 'Not sure about benchmark fit'
    assert anchors[1]['answers'][0]['quality'] == 'repair'
    assert all(digest(a['text']) == a['text_sha256'] for r in anchors for a in r['answers'])
    assert [hashes(p) for p in sources] == before
    assert result['existing_human_answers'] == 3 and result['new_api_calls'] == 0
    store = calibration_review.CalibrationStore(output)
    catalog = store.catalog()
    assert {c['post_id'] for c in catalog['cases']} == set(review.UNRESOLVED)
    for hidden in ('Hidden model verdict', 'Not sure about benchmark fit', 'Longer alternative', 'Unreviewed source comments'):
        assert hidden not in json.dumps(catalog)
    assert store.events() == []
    assert all(c['latest'] is None for c in catalog['cases'])
    with pytest.raises(FileExistsError):
        review.prepare(*sources, output)


@pytest.mark.parametrize('change', ['text', 'quality', 'event'])
def test_refuse_mismatched_human_provenance_even_in_rehashed_snapshot(sources, tmp_path, change):
    packet, snapshot, source = sources
    path = snapshot / 'human-feedback.json'
    rows = json.loads(path.read_text())
    if change == 'text':
        rows[0]['answers'][0]['text_sha256'] = digest('invented alternative')
    elif change == 'quality':
        rows[0]['answers'][0]['quality'] = 'repair'
    else:
        rows[0]['event']['notes'] = 'Assistant rewrote the human note'
    write_json(path, rows)
    seal(snapshot, 'manifest.json', 'snapshot_id', json.loads((snapshot / 'manifest.json').read_text()))
    with pytest.raises(ValueError, match='mismatch'):
        review.prepare(*sources, tmp_path / 'boundary')
    assert not (tmp_path / 'boundary').exists()


def test_refuse_tampered_frozen_input(sources, tmp_path):
    (sources[2] / 'cases.json').write_text('[]')
    with pytest.raises(ValueError):
        review.prepare(*sources, tmp_path / 'boundary')


@pytest.mark.parametrize('change', ['label', 'family'])
def test_do_not_reask_existing_human_judgments_or_families(sources, tmp_path, change):
    source = sources[2]
    rows = json.loads((source / 'cases.json').read_text())
    rows[0]['original_quality' if change == 'label' else 'group_id'] = 'ready' if change == 'label' else 'accepted-pair'
    write_json(source / 'cases.json', rows)
    seal(source, 'plan.json', 'experiment_id', json.loads((source / 'plan.json').read_text()))
    with pytest.raises(ValueError, match='relabel'):
        review.prepare(*sources, tmp_path / 'boundary')
