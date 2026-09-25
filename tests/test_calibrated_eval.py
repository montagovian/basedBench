"""Cost isolation, label isolation and repeatable human-calibrated comparisons."""
import asyncio
import json
from pathlib import Path

import pytest
from PIL import Image

from basedbench.pipeline import calibrated_eval as ev
from basedbench.pipeline.curation_corpus import digest, file_hash, write_json


def case_and_dir(tmp_path):
    (tmp_path/'assets').mkdir()
    p=tmp_path/'test.png'; Image.new('RGB',(40,40),'blue').save(p)
    sha=file_hash(p);p.rename(tmp_path/'assets'/sha)
    return {'case_id':'test','post_id':'test','input':{'explanation':'A written answer.',
        'comment_evidence':'ID: a | Score: 4\nfirst\nID: b | Score: 3\nsecond\nID: c | Score: 2\nthird',
        'image_sha256':sha},'original_quality':'repair','human_note':'SECRET REVIEW NOTE'},tmp_path


def test_request_keeps_human_labels_and_other_answers_out(tmp_path):
    c,d=case_and_dir(tmp_path)
    old=ev.request(c,'baseline_56',d)
    a,b=(ev.request(c,arm,d) for arm in ['simple_56','simple_6'])
    assert old['instructions']==ev.answers.CHECK
    assert a['instructions']==b['instructions']==ev.SIMPLE
    assert a['input']==b['input']==old['input']
    assert 'SECRET REVIEW NOTE' not in json.dumps(a)
    assert 'original_quality' not in json.dumps(a)
    assert a['model']=='gpt-5.6-luna' and b['model']=='gpt-6-luna'
    assert a['text']['format']['schema']==b['text']['format']['schema']
    assert a['reasoning']==b['reasoning']=={'effort':'medium'}


def test_support_hold_is_not_intrinsic_answer_failure(tmp_path):
    c,_=case_and_dir(tmp_path)
    value={'answer_quality':'pass','evidence_status':'insufficient','material_defects':[],
           'missing_or_wrong_connection':None,'supporting_comment_ids':['a','b'],'reason':'Only two support it.'}
    call={'status':'completed','response':{'model':'gpt-6-luna'},'output_text':json.dumps(value)}
    result=ev.parse(c,'simple_6',call)
    assert result['answer_quality']=='pass' and result['verdict']=='uncertain'
    value['evidence_status']='supported'
    assert 'error' in ev.parse(c,'simple_6',call|{'output_text':json.dumps(value)})
    value['supporting_comment_ids']=['a','b','invented']
    assert 'error' in ev.parse(c,'simple_6',call|{'output_text':json.dumps(value)})
    value['supporting_comment_ids']=['a','b','c']
    assert ev.parse(c,'simple_6',call|{'output_text':json.dumps(value)})['verdict']=='pass'


def test_new_model_rates_cache_writes_and_context_surcharge():
    u={'input_tokens':10000,'output_tokens':1000,'input_tokens_details':{'cached_tokens':2000,'cache_write_tokens':3000}}
    assert ev.price(u,'gpt-6-luna')==pytest.approx(.001395)
    assert ev.price(u,'gpt-6-luna',conservative=True)==pytest.approx(.00175)
    assert ev.price({'input_tokens':300000,'output_tokens':1000},'gpt-6-luna')==pytest.approx(.06075)
    assert ev.price(None,'gpt-6-luna') is None
    assert ev.price({'input_tokens':-1,'output_tokens':0},'gpt-6-luna') is None
    assert ev.bound({'model':'gpt-6-luna','max_output_tokens':2400}) >= ev.price({'input_tokens':1050000,'output_tokens':2400},'gpt-6-luna',conservative=True)


def test_unknown_spending_stops_other_model_dispatch_and_survives_restart(tmp_path):
    (tmp_path/'calls').mkdir()
    plan={'budget_usd':1,'experiment_id':'id','request_bounds_usd':{'p.a':.3,'q.b':.3},
          'jobs':[{'key':'p.a','model':'gpt-6-luna'},{'key':'q.b','model':'gpt-5.6-luna'}]}
    b=ev.Budget(plan,tmp_path)
    assert b.reserve('p','a')==.3
    call={'experiment_id':'id','post_id':'p','arm':'a','usage':None}
    b.settle('p','a',call)
    assert b.unknown and b.reserve('q','b') is None
    write_json(tmp_path/'calls/p.a.json',call)
    restarted=ev.Budget(plan,tmp_path)
    assert restarted.unknown and restarted.reserve('q','b') is None


def test_repeats_are_family_distinct_and_outcome_independent():
    cases=[{'case_id':str(i),'group_id':str(i//2),'original_quality':'ready' if i<12 else 'repair' if i<22 else 'unclear'} for i in range(24)]
    chosen=ev.select_repeats(cases)
    assert len(chosen)==10
    assert chosen==ev.select_repeats(list(reversed(cases)))
    assert len({c['group_id'] for c in cases if c['case_id'] in chosen})==10


def test_completed_replay_never_calls_provider(tmp_path):
    output=tmp_path/'run';(output/'calls').mkdir(parents=True)
    report={'done':True};write_json(output/'report.json',report)
    write_json(output/'results-manifest.json',{'report.json':file_hash(output/'report.json')})
    plan={'version':ev.VERSION,'code_hashes':ev.code_hashes(),'files':{}}
    plan['experiment_id']=digest(plan);write_json(output/'plan.json',plan)
    class NoCalls:
        @property
        def responses(self):raise AssertionError('Paid request during frozen replay')
    assert asyncio.run(ev.run(output,client=NoCalls()))==report


def test_animation_is_retained_as_input_error_without_silent_frame_substitution(tmp_path):
    p=tmp_path/'animated.gif'
    Image.new('RGB',(20,20),'red').save(p,save_all=True,append_images=[Image.new('RGB',(20,20),'blue')],duration=100,loop=0)
    assert ev.image_error(p)=='animated_image_not_supported_by_frozen_image_interface'
    assert ev.image_error(tmp_path/'missing.png')=='missing_or_invalid_image'
