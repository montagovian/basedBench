"""Fresh human evidence must not inherit outcome selection, overlap or invented labels."""
import json
from pathlib import Path
import sqlite3

import numpy as np
from PIL import Image
import pytest

from basedbench import fresh_audit as audit
from basedbench.calibration_review import CalibrationStore
from basedbench.curation_review import ReviewRequest
from basedbench.pipeline import duplicate_audit
from basedbench.pipeline.curation_corpus import digest, file_hash, write_json


def test_remaining_census_excludes_all_prior_selection_including_held_rows():
    source = {'eligibility': [{'post_id':p, 'eligible':p!='old-exclusion'} for p in ['human','prior-kept','prior-held','new-a','new-b','old-exclusion']], 'random_ids':['human']}
    selected = audit.remaining_pool(source, ['prior-kept','prior-held'], expected=2)
    assert set(selected)=={'new-a','new-b'}
    source['eligibility'].reverse()
    assert audit.remaining_pool(source,['prior-held','prior-kept'],expected=2)==selected
    with pytest.raises(ValueError,match='pool changed'):
        audit.remaining_pool(source,['prior-kept'],expected=2)


def test_exposure_distinguishes_evaluated_cases_from_pool_membership():
    value={'cases':[{'case_id':'evaluated'}], 'jobs':[{'case_id':'dispatched'}],
           'reference_ids':['reference'], 'input_hashes':{'checked':'abc'},
           'selected_ids':['prior-held'], 'eligibility':[{'post_id':'merely-eligible'}],
           'files':{'candidate-path':'hash'}, 'exposure_scan':[{'post_id':'scan-only'}]}
    assert audit.exposure_ids(value)=={'evaluated','dispatched','reference','checked','prior-held'}


@pytest.fixture
def database(tmp_path,monkeypatch):
    conn=sqlite3.connect(':memory:');conn.row_factory=sqlite3.Row
    conn.executescript('''CREATE TABLE memes(post_id TEXT,created_utc TEXT,subreddit TEXT);
    CREATE TABLE ground_truths(post_id TEXT,explanation TEXT,created_at TEXT,consensus_model TEXT);
    CREATE TABLE llm_calls(id INTEGER,post_id TEXT,role TEXT,verdict TEXT,error TEXT,created_at TEXT);
    INSERT INTO memes VALUES('new','2026-06-08','source');
    INSERT INTO ground_truths VALUES('new','Exact original','2026-09-01','legacy-model');
    INSERT INTO llm_calls VALUES(1,'new','consensus','consensus',NULL,'2026-09-01');''')
    image=tmp_path/'image.png';Image.new('RGB',(30,30),'green').save(image)
    record={'image_path':str(image),'image':{'sha256':file_hash(image)}}
    monkeypatch.setattr(audit,'_historical_input',lambda _: {'explanation':'Exact original','comment_evidence':'Original comments'})
    yield conn,record,tmp_path
    conn.close()


def test_recover_retains_exact_provenance_and_refuses_ambiguous_generation(database):
    conn,record,root=database
    c=audit.recover(conn,'new',record,root)
    assert c['input']['answers']==[{'source':'original','text':'Exact original'}]
    assert c['provenance']['generation_model']=='legacy-model'
    assert c['provenance']['generation_call_id']==1
    assert c['input_sha256']==digest(c['input'])
    conn.execute("INSERT INTO llm_calls VALUES(2,'new','consensus','consensus',NULL,'2026-09-01')")
    with pytest.raises(ValueError,match='ambiguous'):
        audit.recover(conn,'new',record,root)


@pytest.mark.parametrize('change',['answer','image'])
def test_recover_rejects_changed_evidence(database,change):
    conn,record,root=database
    if change=='answer':conn.execute("UPDATE ground_truths SET explanation='Changed answer'")
    else:Path(record['image_path']).write_bytes(b'changed')
    with pytest.raises(ValueError,match='changed'):
        audit.recover(conn,'new',record,root)


def test_retrieval_holds_transitive_exposure_exact_copy_and_semantic_neighbors(tmp_path,monkeypatch):
    # Exercise actual byte/pixel identity plus saved-vector selection. Stub expensive
    # near/crop work, whose algorithms have their own image regression tests.
    records=[]
    for i,pid in enumerate(['prior','family','copy','semantic']):
        im=tmp_path/f'{pid}.png';Image.new('RGB',(30,30),('red','green','red','blue')[i]).save(im)
        records.append({'post_id':pid,'image_path':str(im),'image':duplicate_audit.fingerprint(im,tmp_path)})
    monkeypatch.setattr(audit.audit,'image_evidence',lambda *a:None)
    monkeypatch.setattr(audit.crop,'crop_evidence',lambda *a:None)
    vectors=np.array([[1,0,0],[0,1,0],[0,0,1],[.8,0,.6]])
    rows=audit.screen(['family','copy','semantic'],records,{'prior':'g','family':'g'}, {'prior'},set(),tmp_path,vectors,[{'post_id':r['post_id']} for r in records])
    assert len(rows)==3 and all(r['status']=='family_or_exposure_hold' for r in rows)
    assert any(e['method']=='prior_exposure_or_family' for e in rows[0]['retrieval_candidates_not_gold'])
    assert any(e['match']=='prior' and e['method']!='minilm' for e in rows[1]['retrieval_candidates_not_gold'])
    assert any(e['method']=='minilm' and e['match']=='prior' for e in rows[2]['retrieval_candidates_not_gold'])


@pytest.fixture
def built_packet(tmp_path):
    output=tmp_path/'packet';output.mkdir()
    image=tmp_path/'source.png';Image.new('RGB',(30,30),'orange').save(image);sha=file_hash(image)
    inp={'image_sha256':sha,'explanation':'Untouched answer','comment_evidence':'Hidden comments',
         'answers':[{'source':'original','text':'Untouched answer'}]}
    candidates={'new':{'post_id':'new','input':inp,'input_sha256':digest(inp),'image_path':str(image),
        'image_mime':'image/png','split':'calibration','stratum':'hidden-stratum','previous_feedback':[],
        'group_id':'new','provenance':{'generation_model':'hidden-model','old_opinion':'hidden-criticism'}}}
    selection={'selected_ids':['new','held'],'seed':'frozen'}
    write_json(output/'selection-before-screen.json',selection)
    screening=[{'post_id':'new','status':'eligible'},{'post_id':'held','status':'family_or_exposure_hold'}]
    before=file_hash(image)
    summary=audit.build_packet(output,candidates,screening,selection,{},Path.cwd())
    assert file_hash(image)==before
    return output,summary


def test_packet_preserves_denominators_blinds_review_and_checkpoints_actual_feedback(built_packet):
    packet,summary=built_packet
    assert summary['selected']==2 and summary['reviewable']==1 and summary['new_api_calls']==0
    assert len(json.loads((packet/'screening.json').read_text()))==2
    store=CalibrationStore(packet);catalog=store.catalog();serialized=json.dumps(catalog)
    for secret in ['hidden-model','hidden-criticism','hidden-stratum','Hidden comments']:
        assert secret not in serialized
    assert store.events()==[]
    html=(packet/'ui/index.html').read_text()
    assert '1 original explanations from a fixed pool of 2' in html and '50 cases:' not in html
    req=ReviewRequest(request_id='reveal',post_id='new',packet_id=store.manifest['packet_id'],
                     input_sha256=store.cases['new']['input_sha256'],kind='reveal',reveal='comments',fields={'quality_a':'unclear'})
    revealed=store.append(req)
    assert revealed['event']['exposed_before']==[] and revealed['state']['latest'] is None
    assert revealed['context']['comments']=='Hidden comments'
    saved=store.append(req.model_copy(update={'request_id':'save','kind':'feedback','reveal':None,'fields':{'quality_a':'ready','reason_a':'evidence'},'notes':'Answer ready; source support unresolved'}))
    assert saved['event']['fields']['quality_a']=='ready'
    assert saved['event']['exposed_before']==['comments']
    assert len(CalibrationStore(packet).events())==2
    with pytest.raises(FileExistsError):audit.prepare(Path.cwd(),packet)


def test_all_holds_are_recorded_without_substitutions(tmp_path):
    out=tmp_path/'empty';out.mkdir()
    rows=[{'post_id':'held','status':'input_hold','input_error':'missing_image'}]
    with pytest.raises(ValueError,match='All selected'):
        audit.build_packet(out,{},rows,{'selected_ids':['held']},{},Path.cwd())
    assert json.loads((out/'screening.json').read_text())==rows
    assert not (out/'manifest.json').exists()
