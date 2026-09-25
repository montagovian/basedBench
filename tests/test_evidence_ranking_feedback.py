from copy import deepcopy

import pytest

from basedbench.evidence_ranking_feedback import analyze


def case(rid='R01', kind='sampled', identical=False):
    def pack(text):
        return {'status': 'completed', 'excerpts': [{'comment_id': text, 'start': 0, 'end': len(text), 'text': text}]}
    return {'review_id': rid, 'family_id': rid, 'sample_kind': kind,
            'methods': dict(zip('ABC', ('order', 'rank', 'collate'))),
            'packs': {'A': pack('first'), 'B': pack('second'), 'C': pack('second' if identical else 'third')}}


def feedback(rid='R01', eid='save1', base=None, choice='B', exposed=False):
    return {'review_id': rid, 'packet_id': 'packet', 'event_id': eid, 'request_id': eid,
            'base_revision': base, 'kind': 'feedback', 'most_useful': choice,
            'ratings': {s: {'clue': 'yes', 'misleading': 'no'} for s in 'ABC'},
            'methods_revealed_before': exposed, 'source_opened_before': False,
            'reference_opened_before': False, 'note': 'exact human note'}


def test_skips_revisions_identical_preferences_and_strata_are_not_pooled():
    cases = [case(identical=True), case('R02'), case('R03', 'diagnostic')]
    first = feedback()
    second = feedback(eid='save2', base='save1', choice='C')
    diag = feedback('R03', eid='diag', choice='A')
    result = analyze(cases, [first, second, diag], 'packet')
    sample = result['strata']['sampled']
    assert sample['reviewed'] == 1 and sample['missing'] == ['R02']
    assert sample['button_choices']['collate'] == 1
    assert sample['unique_list_choices']['collate'] == 0
    assert sample['shared_identical_choices'] == {'collate+rank': 1}
    assert result['strata']['diagnostic']['button_choices']['order'] == 1
    assert result['cases'][0]['feedback']['note'] == 'exact human note'
    assert result['cases'][0]['feedback_count'] == 2
    assert result['predeclared_screen']['sampled_decisive_observed'] == 1
    assert result['predeclared_screen']['met'] is False


def test_post_reveal_revision_is_retained_but_cannot_replace_blinded_judgment():
    first = feedback()
    reveal = {'review_id': 'R01', 'packet_id': 'packet', 'event_id': 'reveal',
              'request_id': 'reveal', 'base_revision': 'save1', 'kind': 'reveal'}
    revision = feedback(eid='save2', base='save1', choice='A', exposed=True)
    result = analyze([case()], [first, reveal, revision], 'packet')
    row = result['cases'][0]
    assert row['choice_method'] == 'rank'
    assert row['latest_feedback']['most_useful'] == 'A'
    assert row['post_reveal_feedback_count'] == 1
    dishonest = deepcopy(revision)
    dishonest['methods_revealed_before'] = False
    with pytest.raises(ValueError, match='exposure'):
        analyze([case()], [first, reveal, dishonest], 'packet')


def test_eight_sampled_choices_required_and_diagnostics_do_not_fill_quota():
    cases = [case(f'R{i:02}') for i in range(8)] + [case('D', 'diagnostic')]
    events = [feedback(f'R{i:02}', eid=f's{i}') for i in range(7)] + [feedback('D', eid='d')]
    assert not analyze(cases, events, 'packet')['predeclared_screen']['met']
    events.append(feedback('R07', eid='s7'))
    assert analyze(cases, events, 'packet')['predeclared_screen']['met']
    events[-1]['ratings']['B']['misleading'] = 'yes'
    assert not analyze(cases, events, 'packet')['predeclared_screen']['met']


def test_event_identity_and_revision_validation():
    one = feedback()
    with pytest.raises(ValueError, match='Duplicate journal'):
        analyze([case()], [one, one], 'packet')
    bad = feedback(eid='s2', base='wrong')
    with pytest.raises(ValueError, match='revision'):
        analyze([case()], [one, bad], 'packet')
    with pytest.raises(ValueError, match='another packet'):
        analyze([case()], [one], 'wrong-packet')
