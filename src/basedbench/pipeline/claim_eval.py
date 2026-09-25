"""Bounded direct-claim comparison with source-checked quotes and blind verification.

The existing checker is sampled on the same inputs. Neither arm changes admission
or human labels. Exact quotes establish source identity, never semantic truth.
"""
from __future__ import annotations

import argparse
import asyncio
from collections import Counter
import copy
import fcntl
import json
import math
from pathlib import Path
import re
import shutil
from typing import Literal

from pydantic import Field

from basedbench.pipeline import answer_eval as answers, connection_eval as prior
from basedbench.pipeline import curation_checks as checks, curation_llm as transport
from basedbench.pipeline.curation_corpus import canonical_json, digest, file_hash, write_json

VERSION = 'claim-eval-v1'
STAGES = ('baseline', 'check', 'repair', 'verify')
CASE_IDS = ('1ueh8cd', '1udr4rh', '1ucl7ul', '1udlwwn', '1ubvmoj', '1ubuulz',
            '1ue3n4g', '1jley2r', '1mksov2', '198kcl9', '1ufpe81', '1udvihp',
            '1uc4qnv', '1uc6d4d', '1ucsgt3', '1uf4jf1', '1uc7iqc',
            '1o96j16-corrected', '1fpageg', '1j5w6z3')
CHECK = answers.COMMON + """
Audit the candidate exactly as written using only this image and these comments.
This is an explanation check, not a taste or suitability assessment. Simple jokes,
ordinary text screenshots and short accurate explanations are useful. Peripheral
names, trivia and decorative details need not be included.

1. Decode each ESSENTIAL connection concretely. For a series of separate puns or
panels, list their individual decoding; do not group them under 'wordplay', 'national
stereotypes' or a format name. For a reference joke, connect the pictured action or
placement to the reference. Mark covered only if an exact span of the candidate
actually communicates that connection. Your own decoding does not repair an
incomplete candidate. Copy the shortest sufficient answer_span, or null if absent.
2. Audit material claims with exact answer spans. Distinguish supported statements,
unsupported additions, minority embellishments, and disputed attribution. Ordinary
cultural knowledge can decode a visible reference; do not fabricate source claims.
3. Separately inspect literal assertions of intent, parody, mockery, endorsement,
and real-world truth. Copy those answer spans. If the mechanism is shared but intent
is disputed, the candidate must itself use neutral or appropriately qualified wording.
A neutral shared_reading in YOUR response does not fix the candidate's stronger claim.
4. Audit every comment under its supplied ID. Copy a short exact excerpt and explain
its contribution. Count supports_shared_reading only when that comment substantively
conveys the SAME core connection described in shared_reading. A reaction, keyword,
background fact, unrelated side joke or different proposed punchline does not count.
Concise comments can count; three comments are required overall, not three per fact.
Do not merge incompatible readings to reach three. Set unresolved_core_conflict only
for unresolved incompatible joke mechanisms, not a sincerity dispute that neutral
attribution resolves. Keep image content separate from commenters' invented extras.

No overall verdict is requested: software derives it from coverage, claim/intent
findings, supporting-comment roles and core conflict. Quote text exactly without
ellipses or corrections; whitespace differences alone are allowed. Keep findings
brief, specific and grounded. Do not write a replacement answer in this check.
"""
REPAIR = answers.REPAIR + """
Address the supplied concrete findings while preserving correct content. Decode
essential wordplay and panel connections instead of summarizing their format.
Remove unsupported intent attribution; distinguish the meme's implication from
real-world fact. Do not use reactions, side jokes or conflicting readings to reach
three supporting comments. Return insufficient_evidence when support is inadequate.
Put source IDs only in evidence_comment_ids, never in the explanation. Write the
replacement directly, without commentary about the original answer or this review.
"""


class Connection(answers.StrictModel):
    visible_anchor: str = Field(min_length=1, max_length=180)
    decoding: str = Field(min_length=1, max_length=400)
    answer_span: str | None = Field(max_length=1200)
    coverage: Literal['covered', 'missing', 'wrong']


class Claim(answers.StrictModel):
    answer_span: str = Field(min_length=1, max_length=1200)
    status: Literal['supported', 'unsupported', 'minority_embellishment', 'disputed']
    reason: str = Field(min_length=1, max_length=300)


class Intent(answers.StrictModel):
    answer_spans: list[str] = Field(max_length=8)
    status: Literal['no_attribution', 'supported_or_qualified', 'unsupported', 'disputed']
    reason: str = Field(min_length=1, max_length=400)


class Contribution(answers.StrictModel):
    excerpt: str = Field(min_length=1, max_length=300)
    role: Literal['supports_shared_reading', 'competing_reading', 'reaction', 'context_only', 'extra_joke']
    contribution: str = Field(min_length=1, max_length=240)


class DirectCheck(answers.StrictModel):
    shared_reading: str = Field(min_length=1, max_length=700)
    required_connections: list[Connection] = Field(min_length=1, max_length=30)
    material_claims: list[Claim] = Field(min_length=1, max_length=12)
    intent: Intent
    comments: dict[str, Contribution]
    unresolved_core_conflict: bool
    conflict_reason: str = Field(max_length=500)


def comment_bodies(case):
    text = case['input']['comment_evidence']
    headers = list(re.finditer(r'(?m)^ID: (\S+) \| Score:[^\n]*\n', text))
    result = {}
    for i, header in enumerate(headers):
        cid = header.group(1)
        if cid in result:
            raise ValueError('Duplicate source comment ID')
        result[cid] = text[header.end():headers[i + 1].start() if i + 1 < len(headers) else len(text)].strip()
    if set(result) != set(answers.citation_ids(case)):
        raise ValueError('Malformed comment evidence')
    return result


def contains(source, span):
    return bool(span and span.strip()) and ' '.join(span.split()) in ' '.join(source.split())


def make_request(case, stage, directory, *, explanation=None, critique=None):
    if stage not in STAGES:
        raise ValueError('Unknown direct-check stage')
    candidate = explanation if explanation is not None else case['input']['explanation']
    if stage == 'baseline':
        return answers.make_request(case, 'original_check', directory, explanation=candidate)
    if stage == 'repair':
        body = answers.make_request(case, 'original_repair', directory, explanation=candidate)
        schema = body['text']['format']['schema']
    else:
        body = answers.make_request(case, 'original_check', directory, explanation=candidate)
        schema = DirectCheck.model_json_schema()
        entries = {cid: {'$ref': '#/$defs/Contribution'} for cid in answers.citation_ids(case)}
        schema['properties']['comments'] = {'type': 'object', 'properties': entries,
            'required': list(entries), 'additionalProperties': False}
    evidence = {'candidate_answer': candidate, 'comment_evidence': case['input']['comment_evidence']}
    if stage == 'repair':
        evidence['fallible_findings'] = critique
    body['input'][0]['content'][0]['text'] = canonical_json(evidence)
    body['instructions'] = REPAIR if stage == 'repair' else CHECK
    body['text']['format'] = {'type': 'json_schema', 'name': 'direct_joke_claims', 'strict': True, 'schema': schema}
    body['max_output_tokens'] = 3200 if stage == 'repair' else 5200
    body['prompt_cache_key'] = 'basedbench-direct-' + digest(body['instructions'])[:24]
    return body


def derive(value):
    """Single verdict source: findings cannot be overridden by a separate pass."""
    defects = []
    if any(c['coverage'] != 'covered' for c in value['required_connections']):
        defects.append('missing_or_wrong_connection')
    if any(c['status'] != 'supported' for c in value['material_claims']):
        defects.append('unsupported_material_claim')
    if value['intent']['status'] in {'unsupported', 'disputed'}:
        defects.append('unsupported_intent')
    ids = [cid for cid, c in value['comments'].items() if c['role'] == 'supports_shared_reading']
    evidence_defects = []
    if len(ids) < 3:
        evidence_defects.append('insufficient_substantive_support')
    if value['unresolved_core_conflict']:
        evidence_defects.append('unresolved_core_conflict')
    verdict = 'fail' if defects else 'uncertain' if evidence_defects else 'pass'
    return {**value, 'verdict': verdict, 'defects': defects, 'evidence_defects': evidence_defects,
            'evidence_comment_ids': ids, 'repairable': bool(defects) and not evidence_defects}


def parse(case, stage, call, explanation):
    if stage == 'baseline':
        return answers.parse(case, 'original_check', call)
    if call.get('error'):
        return {'error': call['error']}
    try:
        model = call['response']['model']
        if call['status'] != 'completed' or not (model == checks.MODEL or model.startswith(checks.MODEL + '-')):
            raise ValueError('Expected completed Luna response')
        if stage == 'repair':
            value = answers.parse(case, 'original_repair', call)
            if value.get('status') == 'proposed':
                cleaned, remaining = prior.clean_citations(value['explanation'], answers.citation_ids(case))
                if cleaned != value['explanation'] or remaining:
                    raise ValueError('Repair includes source IDs in prose')
            return value
        value = DirectCheck.model_validate_json(call['output_text']).model_dump()
        comments = comment_bodies(case)
        if set(value['comments']) != set(comments):
            raise ValueError('Every supplied comment must be audited exactly once')
        for cid, contribution in value['comments'].items():
            if not contains(comments[cid], contribution['excerpt']):
                raise ValueError('Comment excerpt is not from its source: ' + cid)
        for connection in value['required_connections']:
            span = connection['answer_span']
            if (span is not None and not contains(explanation, span)) or (connection['coverage'] == 'covered' and not span):
                raise ValueError('Coverage must cite literal candidate text')
        spans = [c['answer_span'] for c in value['material_claims']] + value['intent']['answer_spans']
        if any(not contains(explanation, span) for span in spans):
            raise ValueError('Claim/intent span is not literal candidate text')
        intent = value['intent']
        if (intent['status'] == 'no_attribution') != (not intent['answer_spans']):
            raise ValueError('Intent finding and cited spans disagree')
        return derive(value)
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        return {'error': str(exc)}


async def evaluate(case, invoke):
    cleaned, remaining = prior.clean_citations(case['input']['explanation'], answers.citation_ids(case))
    values = {'baseline': await invoke('baseline', explanation=cleaned)}
    values['check'] = await invoke('check', explanation=cleaned)
    result = {'case_id': case['case_id'], 'post_id': case['post_id'], 'stages': values,
              'status': 'unresolved', 'explanation': None, 'repaired': False,
              'mechanical_cleanup': {'changed': cleaned != case['input']['explanation'], 'remaining_ids': remaining}}
    check = values['check']
    if check.get('verdict') == 'pass' and not remaining:
        return {**result, 'status': 'model_supported', 'explanation': cleaned}
    if check.get('repairable'):
        values['repair'] = await invoke('repair', explanation=cleaned, critique=check)
        if values['repair'].get('status') == 'proposed':
            proposal = values['repair']['explanation']
            values['verify'] = await invoke('verify', explanation=proposal)
            if values['verify'].get('verdict') == 'pass':
                return {**result, 'status': 'model_supported', 'explanation': proposal, 'repaired': True}
    if any(v.get('error') for k, v in values.items() if k != 'baseline'):
        result['status'] = 'error'
    return result


def code_hashes():
    return prior.code_hashes() | {'claim_eval': file_hash(Path(__file__))}


def prepare(packet: Path, output: Path, *, case_ids=CASE_IDS, budget_usd=.25):
    if output.exists():
        raise FileExistsError('Use a new experiment directory')
    if not math.isfinite(budget_usd) or not 0 < budget_usd <= .25:
        raise ValueError('Maximum total model cap is $0.25')
    source = {c['case_id']: c for c in json.loads((packet / 'cases.json').read_text())}
    if not case_ids or len(case_ids) > 20 or len(set(case_ids)) != len(case_ids):
        raise ValueError('Select one to twenty unique development cases')
    cases = [copy.deepcopy(source[cid]) for cid in case_ids]
    for case in cases:
        if not re.fullmatch(r'[A-Za-z0-9_-]+', case['case_id']) or not case['input']['explanation']:
            raise ValueError('A safe case ID and original candidate answer are required')
        comment_bodies(case)
        sha = case['input']['image_sha256']
        if not re.fullmatch('[a-f0-9]{64}', sha) or file_hash(packet / 'assets' / sha) != sha:
            raise ValueError('Invalid image evidence')
    for folder in ('assets', 'calls', 'requests'):
        (output / folder).mkdir(parents=True)
    for case in cases:
        sha = case['input']['image_sha256']
        shutil.copyfile(packet / 'assets' / sha, output / 'assets' / sha)
    write_json(output / 'cases.json', cases)
    bounds = {}
    for case in cases:
        cleaned, _ = prior.clean_citations(case['input']['explanation'], answers.citation_ids(case))
        for stage in STAGES:
            body = make_request(case, stage, output, explanation=cleaned)
            if stage in {'repair', 'verify'}:
                body['input'][0]['content'][0]['text'] += 'x' * 48000
            bounds[case['case_id'] + '.' + stage] = checks.request_bound(body, stage)
    plan = {'version': VERSION, 'budget_usd': budget_usd, 'model': checks.MODEL, 'prices': checks.PRICES,
            'code_hashes': code_hashes(), 'request_bounds_usd': bounds, 'max_calls': len(bounds),
            'max_concurrency': 3, 'automatic_retries': 0, 'max_repairs_per_answer': 1,
            'source_files': {str((packet / 'cases.json').resolve()): file_hash(packet / 'cases.json')},
            'input_hashes': {c['case_id']: digest(c['input']) for c in cases},
            'prompts': {'baseline': answers.CHECK, 'check': CHECK, 'repair': REPAIR},
            'independent_validation': False, 'human_validation': False,
            'files': {str(p.relative_to(output)): file_hash(p) for p in sorted(output.rglob('*')) if p.is_file()}}
    plan['experiment_id'] = digest(plan)
    write_json(output / 'plan.json', plan)
    return plan


async def run(output: Path, *, api_key='', client=None):
    import openai
    plan = json.loads((output / 'plan.json').read_text())
    if plan['version'] != VERSION or plan['code_hashes'] != code_hashes() or digest({k: v for k, v in plan.items() if k != 'experiment_id'}) != plan['experiment_id']:
        raise ValueError('Frozen plan/code changed')
    prior.verify_files(output, plan['files'])
    for name, sha in plan['source_files'].items():
        if file_hash(Path(name)) != sha:
            raise ValueError('Original packet changed')
    owned = client is None
    if owned:
        client = openai.AsyncOpenAI(api_key=api_key, max_retries=0, timeout=180)
    try:
        with (output / 'run.lock').open('w') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if (output / 'results-manifest.json').exists():
                prior.verify_files(output, json.loads((output / 'results-manifest.json').read_text()))
            budget = checks.Budget(plan, output)
            halted = any(json.loads(p.read_text()).get('fatal_provider_error') for p in (output / 'calls').glob('*.json'))
            results = []
            cases = json.loads((output / 'cases.json').read_text())
            semaphore = asyncio.Semaphore(plan['max_concurrency'])
            async def one_case(case):
                async with semaphore:
                    async def invoke(stage, **kwargs):
                        nonlocal halted
                        key = case['case_id'] + '.' + stage
                        body = make_request(case, stage, output, **kwargs)
                        if checks.request_bound(body, stage) > plan['request_bounds_usd'][key] + 1e-12:
                            raise ValueError('Request exceeds frozen allowance')
                        request_path = output / 'requests' / (key + '.json')
                        if request_path.exists() and json.loads(request_path.read_text()) != body:
                            raise ValueError('Request changed on replay')
                        if not request_path.exists():
                            write_json(request_path, body)
                        path = output / 'calls' / (key + '.json')
                        if halted and not path.exists():
                            return {'error': 'fatal_provider_stop'}
                        row = {'post_id': case['case_id'], 'input_sha256': plan['input_hashes'][case['case_id']]}
                        await transport.collect_calls(client, [row], output, output, {**plan, 'arms': [stage]},
                            concurrency=1, request_factory=lambda *_: body, budget=budget)
                        call = json.loads(path.read_text())
                        if call['post_id'] != case['case_id'] or call['arm'] != stage or call.get('request_content_sha256') not in {None, digest(body)}:
                            raise ValueError('Saved call identity mismatch')
                        if call.get('request_content_sha256') is None and call['status'] not in {'unknown', 'not_started'}:
                            raise ValueError('Response missing request provenance')
                        halted |= bool(call.get('fatal_provider_error'))
                        if budget.violated:
                            return {'error': 'budget_allowance_violation'}
                        return parse(case, stage, call, kwargs['explanation'])
                    results.append(await evaluate(case, invoke))
                    results.sort(key=lambda r: r['case_id'])
                    write_json(output / 'results.json', results)
                    print(f'Recorded {len(results)}/{len(cases)}; accounted ${sum(budget.charges.values()):.5f}/$0.25', flush=True)
            await asyncio.gather(*(one_case(case) for case in cases))
            calls = [json.loads(p.read_text()) for p in sorted((output / 'calls').glob('*.json'))]
            report = {'experiment_id': plan['experiment_id'], 'cases': len(results),
                'statuses': dict(Counter(r['status'] for r in results)),
                'original_verdicts': {stage: dict(Counter(r['stages'][stage].get('verdict', 'error') for r in results)) for stage in ('baseline', 'check')},
                'repairs_verified': sum(r['repaired'] for r in results),
                'calls': len(calls), 'completed_calls': sum(c['status'] == 'completed' for c in calls),
                'parse_errors': sum(bool(v.get('error')) for r in results for v in r['stages'].values()),
                'cost_estimate_usd': sum(answers.exact_cost(c) or 0 for c in calls),
                'accounted_usd': sum(budget.charges.values()), 'allowance_violation': budget.violated,
                'unknown_usage_calls': sum(c.get('usage') is None for c in calls),
                'budget_usd': budget.limit, 'independent_validation': False}
            write_json(output / 'report.json', report)
            write_json(output / 'results-manifest.json', {str(p.relative_to(output)): file_hash(p) for p in sorted(output.rglob('*'))
                if p.is_file() and (p.parent.name in {'calls', 'requests'} or p.name in {'results.json', 'report.json'})})
            return report
    finally:
        if owned:
            await client.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    prep = sub.add_parser('prepare')
    prep.add_argument('packet', type=Path)
    prep.add_argument('output', type=Path)
    execute = sub.add_parser('run')
    execute.add_argument('output', type=Path)
    args = parser.parse_args()
    if args.command == 'prepare':
        plan = prepare(args.packet, args.output)
        print(json.dumps({k: plan[k] for k in ('experiment_id', 'budget_usd', 'max_calls')}))
    else:
        import os
        from dotenv import dotenv_values
        key = os.getenv('OPENAI_API_KEY') or dotenv_values('.env').get('OPENAI_API_KEY')
        print(json.dumps(asyncio.run(run(args.output, api_key=key))))


if __name__ == '__main__':
    main()
