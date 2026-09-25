import copy

import pytest

from basedbench.pipeline.admission_report import summarize, render_casebook


def sample():
    cases = [{'post_id': str(i), 'input': {'image_sha256': None, 'comment_evidence': '<script>bad()</script>'},
              'provenance': {'subreddit': 'community', 'source_date': '2026-06-20T00:00:00Z'}} for i in range(3)]
    outcomes = []
    for i in range(3):
        components = {s: {'decision': 'pass', 'technical_status': 'ok', 'reason_codes': ['ok']}
                      for s in ['preflight', 'duplicates', 'content', 'answer', 'suitability']}
        outcomes.append({'post_id': str(i), 'decision': 'accept', 'technical_status': 'ok',
                         'reason_codes': ['all_passed'], 'components': components, 'answer_stages': {}})
    outcomes[1].update(decision='defer', technical_status='error', reason_codes=['missing_image', 'duplicate_uncertain'])
    outcomes[1]['components']['preflight'].update(decision='defer', technical_status='error')
    outcomes[1]['components']['duplicates']['decision'] = 'defer'
    for s in ['content', 'answer', 'suitability']:
        outcomes[1]['components'][s].update(decision='not_run', technical_status='not_run')
    outcomes[2]['answer_stages'] = {'generated_repair': {'status': 'proposed'}, 'generated_verify': {'verdict': 'pass'}}
    outcomes[2]['components']['answer']['repaired'] = True
    report = {'complete': True, 'experiment_id': 'run1', 'outcomes': outcomes, 'counts': {'accept': 2, 'defer': 1},
              'cost': {'estimated_usd': .3, 'unknown_usage_calls': 0}}
    notes = {'experiment_id': 'run1', 'items': {
        '0': {'assessment': 'no_issue_found', 'tags': ['reference', 'reference'], 'flags': []},
        '2': {'assessment': 'flagged', 'tags': ['reference'], 'flags': ['unsupported_claim'], 'note': '<img src=x onerror=bad()>'}}}
    return cases, report, notes


def test_overlapping_gaps_cost_and_inspection_do_not_inflate_quality():
    cases, report, notes = sample()
    s = summarize(cases, report, notes)
    assert s['exclusive_stopping_stage'] == {'accepted': 2, 'preflight': 1}
    assert s['component_decisions']['duplicates'] == {'pass': 2, 'defer': 1}
    assert s['technical_error_candidates'] == 1
    assert s['repair_attempts'] == s['accepted_after_repair'] == 1
    assert s['cost_per_automatic_accept_usd'] == .15
    assert s['inspection']['cost_per_inspected_unflagged_accept_usd'] == .3
    assert s['inspection']['exploratory_tags_overlapping']['reference']['inspected'] == 2
    assert s['inspection']['accepted_with_flags'] == 1
    assert s['coverage']['community']['community'] == {'total': 3, 'accept': 2, 'defer': 1}


def test_zero_accepts_unknown_cost_and_missing_inspections_are_not_perfect_scores():
    cases, report, notes = sample()
    s = summarize(cases, report, {})
    assert s['inspection']['uninspected_accepts'] == 2
    assert s['inspection']['cost_per_inspected_unflagged_accept_usd'] is None
    report['cost']['unknown_usage_calls'] = 1
    assert summarize(cases, report, notes)['cost_per_automatic_accept_usd'] is None
    report['counts'] = {'defer': 3}
    for outcome in report['outcomes']:
        outcome['decision'] = 'defer'
    assert summarize(cases, report, {})['cost_per_automatic_accept_usd'] is None


@pytest.mark.parametrize('mutation', ['incomplete', 'duplicate', 'missing', 'wrong_experiment', 'unknown_note', 'wrong_counts'])
def test_rejects_misleading_or_mismatched_assessments(mutation):
    cases, report, notes = sample()
    if mutation == 'incomplete':
        report['complete'] = False
    elif mutation == 'duplicate':
        report['outcomes'].append(copy.deepcopy(report['outcomes'][0]))
    elif mutation == 'missing':
        report['outcomes'].pop()
    elif mutation == 'wrong_experiment':
        notes['experiment_id'] = 'elsewhere'
    elif mutation == 'unknown_note':
        notes['items']['unknown'] = {}
    else:
        report['counts']['accept'] = 100
    with pytest.raises(ValueError):
        summarize(cases, report, notes)


def test_casebook_escapes_untrusted_comments_and_inspection(tmp_path):
    cases, report, notes = sample()
    page = render_casebook(cases, report, notes, summarize(cases, report, notes), tmp_path, tmp_path)
    assert '<script>bad()' not in page and '&lt;script&gt;bad()' in page
    assert '<img src=x' not in page and '&lt;img src=x' in page
    assert page.count('<article ') == 3
