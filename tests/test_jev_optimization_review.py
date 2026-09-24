import hashlib
import json

import pytest

from basedbench import jev_optimization_review as review
from basedbench.pipeline.jev_optimization_protocol import summarize


def _write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')


def _fixture():
    cases, records = [], []
    for i in range(94):
        ready = i < 77
        text = '<img src=x onerror=alert(1)> The exact punchline.' if i == 77 else 'A clear reversal.'
        group = f'g{i}' if ready or i >= 83 else f'g{i-77}'
        case = {'case_id': f'case{i}', 'group_id': group, 'gold': 'ready' if ready else 'repair',
                'input': {'explanation': '<script>alert(1)</script>' if i == 77 else 'The reversal.'},
                'comments': [{'id': 'reader', 'text': text}],
                'baseline': {'broad': 'pass', 'combined': 'pass', 'calibrated': 'pass'}}
        cases.append(case)
        unit = {'id': 'u0', 'comment_id': 'reader', 'start': 0, 'end': len(text), 'text': text}
        for method in ('seed', 'optimized'):
            prediction = 'fail' if method == 'optimized' and i == 77 else 'pass'
            result = {'prediction': prediction, 'trace': {'reason_codes': ['strong_essential_failure'
                       if prediction == 'fail' else 'native_and_essential_covered'],
                       'units': [{'unit': unit, 'essential': True,
                                  'coverage': {'choice': 'missing' if prediction == 'fail' else 'covered'}}]}}
            records.append({'case_id': case['case_id'], 'method': method,
                            'prediction': prediction, 'result': result})
    report = summarize(cases, records)
    report.update(status='complete', provider_ledger={'spent_or_reserved_usd': 0.53})
    return cases, records, report


def test_complete_page_counts_changed_union_and_escapes_case_data(tmp_path):
    cases, records, report = _fixture()
    page = review.complete_html(report, cases, records)
    assert 'Did optimization help?' in page
    assert 'did not meet the preset development screen' in page
    assert '<td>Optimized policy</td><td>77/77</td><td>1/17</td><td>0</td>' in page
    assert 'Changed cases (1)' in page
    assert 'reader:0–' in page
    assert '&lt;img src=x onerror=alert(1)&gt;' in page
    assert '&lt;script&gt;alert(1)&lt;/script&gt;' in page
    assert '<script>alert(1)</script>' not in page
    assert 'All 94 case inputs and labels' in page
    assert 'Both versions judged correctly' in page
    bad = json.loads(json.dumps(report))
    bad['metrics']['optimized']['ready_passes'] = 1
    with pytest.raises(ValueError, match='Report differs'):
        review.complete_html(bad, cases, records)


def test_partial_page_reports_stop_without_quality_claims_and_writes_only_review(tmp_path):
    root = tmp_path / 'run'
    root.mkdir()
    _write(root / 'partial.json', {'reason': '<bad provider response>',
           'provider_ledger': {'calls': 117, 'spent_or_reserved_usd': .0657, 'pending_calls': 1}})
    target = review.render(root)
    page = target.read_text()
    assert target == root / 'review' / 'partial.html'
    assert 'Run stopped before comparison' in page
    assert '&lt;bad provider response&gt;' in page
    assert 'No quality result is available yet' in page
    assert '$0.0657' in page
    assert 'Did optimization help?' not in page
    with pytest.raises(ValueError, match='dedicated'):
        review.render(root, tmp_path / 'elsewhere')
    with pytest.raises(FileExistsError):
        review.render(root)


def test_stopped_diagnostic_is_specific_and_hash_checked(tmp_path):
    root = tmp_path / 'run'
    root.mkdir()
    _write(root / 'partial.json', {'reason': '<raw parser error>',
           'provider_ledger': {'calls': 118, 'spent_or_reserved_usd': .0657, 'pending_calls': 1}})
    _write(root / 'stop-analysis.json', {'response_problem': {'choice': 'missing',
           'probabilities': {'covered': .45, 'missing': .44}},
           'total_attempted_calls': 118, 'total_accounted_usd': .06565371,
           'reflections_completed': 2, 'actual_case_evaluations_completed': 41,
           'outer_folds_completed': 0, 'final_cases_evaluated': 0})
    files = {name: hashlib.sha256((root / name).read_bytes()).hexdigest()
             for name in ('partial.json', 'stop-analysis.json')}
    _write(root / 'stopped-manifest.json', {'files': files})
    page = review.render(root).read_text()
    assert 'chose <b>missing</b> at 0.44' in page
    assert '<b>covered</b> had the higher probability 0.45' in page
    assert 'first fold stopped after 2 reflection proposals' in page
    assert '0 final cases completed' in page
    assert 'invalid provider response as an abstention' in page
    assert '<summary>Technical error</summary>' in page
    (root / 'review' / 'partial.html').unlink()
    _write(root / 'stop-analysis.json', {'tampered': True})
    with pytest.raises(ValueError, match='hash mismatch'):
        review.render(root)


def test_complete_render_requires_hashed_final_artifacts(tmp_path):
    cases, records, report = _fixture()
    root = tmp_path / 'run'
    root.mkdir()
    for name, value in [('cases.json', cases), ('records.json', records),
                        ('report.json', report), ('policies.json', [])]:
        _write(root / name, value)
    files = {name: hashlib.sha256((root / name).read_bytes()).hexdigest()
             for name in ('report.json', 'records.json', 'policies.json')}
    _write(root / 'complete.json', {'files': files})
    assert review.render(root).is_file()
    (root / 'review' / 'index.html').unlink()
    _write(root / 'records.json', [])
    with pytest.raises(ValueError, match='hash mismatch'):
        review.render(root)
