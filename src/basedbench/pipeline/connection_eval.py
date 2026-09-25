"""Bounded, source-first development comparison; never changes admission or labels.

This is deliberately separate from the frozen answer/admission implementations.
An evidence map is a fallible model proposal, not a new gold annotation.
"""
from __future__ import annotations

import argparse
import asyncio
import fcntl
import json
import math
import re
import shutil
from collections import Counter
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from basedbench.pipeline import answer_eval as answers, curation_checks as checks
from basedbench.pipeline import curation_llm as transport
from basedbench.pipeline.curation_corpus import canonical_json, digest, file_hash, write_json

VERSION = 'connection-eval-v1'
STAGES = ('map', 'check', 'repair', 'verify')
COMMON = answers.COMMON + """
Preserve the three-substantive-comment requirement for the shared reading, not a quota per fact.
An explanation may draw on ordinary cultural knowledge to decode a reference visible in the image;
do not invent comments or claim commenters said something they did not. Keep image facts,
comment-supported interpretations, and comment-only extra jokes separate. Enumerating several
agreeing comments is not enough: examine supplied disagreement too. Where authorial sincerity or
parody is disputed but the visible mechanism is shared, explain that mechanism neutrally. Do not
assert parody, endorsement or a factual allegation merely because it seems likely.
Easy puns, literal misunderstandings, reference recognition and ordinary text screenshots can all
be good tasks. Do not require a hidden twist, sophisticated inference, or every peripheral detail.
Only flag suitability when a specific missing connection leaves object identification, transcription
or serious context in place of a recoverable joke. Uncertain suitability is a hypothesis, not rejection.
"""
MAP = COMMON + """
You have the image and comments, WITHOUT a candidate answer. Establish the task before judging an
answer. Record the visible setup, a neutral account of the shared joke, and its essential connections.
For a multi-part joke, decode the essential panels/references and sound-alike words concretely.
Saying 'these are puns' or naming a meme format is not decoding it. Distinguish an essential series
of punchlines from optional decorative details. Do not import additional examples from comments.
Audit every supplied comment ID once with its role and a short, specific description of what it
actually contributes. A bare reaction such as 'sweet summer child', vote count, link, or keyword
echo does not explain the joke. Concise comments CAN count if they convey the relevant connection.
Record materially competing readings, with their citations and whether neutral wording resolves
them; do not invent speculative alternatives. Status supported requires a recoverable task, at
least three substantive comments supporting its shared reading, and no unresolved core conflict.
Otherwise use insufficient_support, competing_readings or no_recoverable_connection. These statuses
do not say the meme is bad or an existing explanation is wrong. Keep entries concise.
"""
CHECK = COMMON + """
Evaluate the candidate AS WRITTEN against the raw image and comments. The source-first map is a
fallible aid: correct its errors explicitly, including unnecessary connections. Audit every mapped
connection as covered, missing, wrong or not_required. Decode essential wordplays/panels before
deciding coverage. Do not mentally repair a format-level summary and then pass it.
List unsupported material claims separately. Recheck cited comments for substantive support and
competing readings. Fail a concrete answer defect; use uncertain for evidence shortfall or unresolved
task/interpretation. Do not confuse lack of three comments with a demonstrated wrong answer.
If neutral wording can remove unsupported intent while keeping a supported joke, mark that as a
repairable unsupported addition, not an irresolvable competing core. Pass correct concise answers.
Citation debris is mechanical: record it separately from semantic defects. Do not quote source IDs
inside a replacement explanation. No replacement is requested in this check.
"""
REPAIR = COMMON + """
Make one bounded repair of the supplied answer using the image and original comments. The map and
critique are fallible. Address concrete missing or mistaken connections, remove unsupported intent
and comment-only embellishments, and preserve correct content. Decode essential wordplays/panels;
a format summary is insufficient. Do not lengthen for trivia. Keep source IDs exclusively in the
evidence_comment_ids field, never in explanation prose. Return insufficient_evidence when three
substantive comments do not support the shared reading or competing core meanings remain unresolved.
"""


class Connection(answers.StrictModel):
    key: str = Field(min_length=1, max_length=40)
    visible_anchor: str = Field(min_length=1, max_length=220)
    decoding: str = Field(min_length=1, max_length=400)
    evidence_comment_ids: list[str]


class CommentRole(answers.StrictModel):
    comment_id: str
    role: Literal['substantive_support', 'competing', 'reaction', 'context_only', 'extra_joke']
    contribution: str = Field(min_length=1, max_length=240)


class CompetingReading(answers.StrictModel):
    reading: str = Field(min_length=1, max_length=400)
    evidence_comment_ids: list[str]
    resolution: Literal['neutral_core', 'unsupported_by_image', 'unresolved_core']
    reason: str = Field(min_length=1, max_length=400)


class EvidenceMap(answers.StrictModel):
    image_setup: str = Field(min_length=1, max_length=800)
    shared_reading: str = Field(min_length=1, max_length=900)
    connections: list[Connection] = Field(max_length=30)
    comment_roles: list[CommentRole] = Field(max_length=30)
    competing_readings: list[CompetingReading] = Field(max_length=8)
    task: Literal['recoverable', 'unclear', 'observation_only']
    status: Literal['supported', 'insufficient_support', 'competing_readings', 'no_recoverable_connection']
    reason: str = Field(min_length=1, max_length=900)

    @model_validator(mode='after')
    def consistent(self):
        keys = [c.key for c in self.connections]
        ids = [c.comment_id for c in self.comment_roles]
        if len(keys) != len(set(keys)) or len(ids) != len(set(ids)):
            raise ValueError('Connections and comment roles must be unique')
        if self.status == 'supported' and (
            self.task != 'recoverable' or not keys
            or sum(c.role == 'substantive_support' for c in self.comment_roles) < 3
            or any(c.resolution == 'unresolved_core' for c in self.competing_readings)
        ):
            raise ValueError('Supported map requires a task, three substantive comments and resolved core')
        return self


class Coverage(answers.StrictModel):
    key: str
    status: Literal['covered', 'missing', 'wrong', 'not_required']
    reason: str = Field(min_length=1, max_length=400)


class AnswerCheck(answers.StrictModel):
    coverage: list[Coverage] = Field(max_length=30)
    unsupported_claims: list[str] = Field(max_length=10)
    map_corrections: list[str] = Field(max_length=10)
    verdict: Literal['pass', 'fail', 'uncertain']
    defects: list[Literal['missing_core_connection', 'unsupported_addition', 'visual_contradiction',
                         'competing_readings', 'insufficient_evidence', 'no_recoverable_connection']]
    reason: str = Field(min_length=1, max_length=1200)
    evidence_comment_ids: list[str]
    citation_debris: bool

    @model_validator(mode='after')
    def consistent(self):
        if len({c.key for c in self.coverage}) != len(self.coverage):
            raise ValueError('Coverage keys must be unique')
        if self.verdict == 'pass' and (self.defects or self.unsupported_claims
            or any(c.status in {'missing', 'wrong'} for c in self.coverage)
            or len(set(self.evidence_comment_ids)) < 3):
            raise ValueError('A pass requires coverage, supported claims and three citations')
        if self.verdict == 'fail' and not self.defects:
            raise ValueError('Failure requires a concrete defect')
        return self


def clean_citations(text: str, ids: list[str]) -> tuple[str, list[str]]:
    """Remove only bracket groups wholly composed of supplied source IDs.

    Ordinary brackets and mixed/unknown text survive; any remaining known ID
    blocks a clean export instead of guessing how to edit the sentence.
    """
    known = set(ids)
    def replace(match):
        tokens = re.split(r'[\s,;]+', match.group(1).strip())
        return '' if tokens and set(tokens) <= known else match.group(0)
    cleaned = re.sub(r'\[([^\[\]]+)\]', replace, text)
    cleaned = re.sub(r' +([.,;:!?])', r'\1', cleaned)
    cleaned = re.sub(r' {2,}', ' ', cleaned).strip()
    remaining = [i for i in ids if re.search(r'(?<!\w)' + re.escape(i) + r'(?!\w)', cleaned)]
    return cleaned, remaining


def make_request(case, stage, directory, *, mapping=None, explanation=None, critique=None):
    if stage not in STAGES:
        raise ValueError('Unknown connection stage')
    evidence = {'comment_evidence': case['input']['comment_evidence']}
    if stage != 'map':
        evidence.update(candidate_answer=explanation, source_first_map=mapping)
    if stage == 'repair':
        evidence['fallible_critique'] = critique
    schema = (EvidenceMap if stage == 'map' else answers.Draft if stage == 'repair' else AnswerCheck).model_json_schema()
    ids = answers.citation_ids(case)
    def constrain(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key == 'evidence_comment_ids':
                    if ids:
                        child['items']['enum'] = ids
                    else:
                        child['maxItems'] = 0
                elif key == 'comment_id' and isinstance(child, dict):
                    child['enum'] = ids
                constrain(child)
        elif isinstance(value, list):
            for child in value:
                constrain(child)
    constrain(schema)
    content = transport.request_content(case, 'image', directory)
    content[0] = {'type': 'input_text', 'text': canonical_json(evidence)}
    prompt = MAP if stage == 'map' else REPAIR if stage == 'repair' else CHECK
    return {'model': checks.MODEL, 'instructions': prompt,
            'input': [{'role': 'user', 'content': content}],
            'text': {'format': {'type': 'json_schema', 'name': 'joke_connections', 'strict': True, 'schema': schema}, 'verbosity': 'low'},
            'reasoning': {'effort': 'medium'}, 'max_output_tokens': 5200 if stage == 'map' else 3600,
            'store': False, 'service_tier': 'default', 'truncation': 'disabled',
            'prompt_cache_key': 'basedbench-connections-' + digest(prompt)[:24]}


def parse(case, stage, call, mapping=None):
    if call.get('error'):
        return {'error': call['error']}
    try:
        model = call['response']['model']
        if call['status'] != 'completed' or not (model == checks.MODEL or model.startswith(checks.MODEL + '-')):
            raise ValueError('Expected completed Luna response; no fallback')
        schema = EvidenceMap if stage == 'map' else answers.Draft if stage == 'repair' else AnswerCheck
        value = schema.model_validate_json(call['output_text']).model_dump()
        ids = set(answers.citation_ids(case))
        def validate_ids(obj):
            if isinstance(obj, dict):
                for key, child in obj.items():
                    if key == 'evidence_comment_ids' and not set(child) <= ids:
                        raise ValueError('Citation outside supplied evidence')
                    validate_ids(child)
            elif isinstance(obj, list):
                for child in obj:
                    validate_ids(child)
        validate_ids(value)
        if stage == 'map' and {r['comment_id'] for r in value['comment_roles']} != ids:
            raise ValueError('Map must audit every supplied comment exactly once')
        if stage in {'check', 'verify'}:
            if {c['key'] for c in value['coverage']} != {c['key'] for c in mapping['connections']}:
                raise ValueError('Coverage must audit every mapped connection')
            if value['verdict'] == 'pass' and mapping['status'] != 'supported':
                raise ValueError('Pass cannot override unresolved evidence map')
            supported = {r['comment_id'] for r in mapping['comment_roles'] if r['role'] == 'substantive_support'}
            if value['verdict'] == 'pass' and not set(value['evidence_comment_ids']) <= supported:
                raise ValueError('Pass cites comments not mapped as substantive support')
        if stage == 'repair' and value['status'] == 'proposed':
            cleaned, remaining = clean_citations(value['explanation'], sorted(ids))
            if remaining or cleaned != value['explanation']:
                raise ValueError('Repair contains source IDs in explanation prose')
        return value
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        return {'error': str(exc)}


async def evaluate(case, invoke):
    values = {'map': await invoke('map')}
    mapping = values['map']
    result = {'case_id': case['case_id'], 'post_id': case['post_id'], 'stages': values,
              'status': 'unresolved', 'explanation': None, 'repaired': False}
    if mapping.get('error'):
        return {**result, 'status': 'error'}
    original = case['input']['explanation']
    if not original:
        return {**result, 'status': 'evidence_only'}
    cleaned, remaining = clean_citations(original, answers.citation_ids(case))
    result['mechanical_cleanup'] = {'changed': cleaned != original, 'remaining_ids': remaining}
    values['check'] = await invoke('check', mapping=mapping, explanation=cleaned)
    check = values['check']
    if check.get('verdict') == 'pass' and not remaining:
        return {**result, 'status': 'model_supported', 'explanation': cleaned}
    repairable = check.get('verdict') == 'fail' and mapping['status'] == 'supported' and not set(
        check['defects']).intersection({'insufficient_evidence', 'competing_readings', 'no_recoverable_connection'})
    if repairable:
        values['repair'] = await invoke('repair', mapping=mapping, explanation=cleaned, critique=check)
        if values['repair'].get('status') == 'proposed':
            proposal = values['repair']['explanation']
            values['verify'] = await invoke('verify', mapping=mapping, explanation=proposal)
            if values['verify'].get('verdict') == 'pass':
                return {**result, 'status': 'model_supported', 'explanation': proposal, 'repaired': True}
    if any(v.get('error') for v in values.values()):
        result['status'] = 'error'
    return result


def code_hashes():
    return answers.code_hashes() | {'connection_eval': file_hash(Path(__file__))}


def prepare(packet: Path, output: Path, *, budget_usd=.25):
    if output.exists():
        raise FileExistsError('Use a new experiment directory')
    if not math.isfinite(budget_usd) or not 0 < budget_usd <= .25:
        raise ValueError('Issue #16 permits at most $0.25 total')
    cases = json.loads((packet / 'cases.json').read_text())
    if not cases or len({c['case_id'] for c in cases}) != len(cases):
        raise ValueError('Nonempty unique case identities required')
    for case in cases:
        if not re.fullmatch(r'[a-zA-Z0-9_-]+', case['case_id']):
            raise ValueError('Invalid case ID')
        sha = case['input']['image_sha256']
        if not re.fullmatch(r'[a-f0-9]{64}', sha) or file_hash(packet / 'assets' / sha) != sha:
            raise ValueError('Invalid image evidence')
    shutil.copytree(packet, output)
    (output / 'calls').mkdir()
    (output / 'requests').mkdir()
    # Worst dynamic payloads are bounded by serialized UTF-8 length as well as tokens.
    bounds = {}
    for case in cases:
        for stage in STAGES:
            body = make_request(case, stage, output, mapping=None, explanation=case['input']['explanation'])
            if stage != 'map':
                # 48 KB of JSON map + answer/critique slack. Actual requests must fit this bound.
                body['input'][0]['content'][0]['text'] += 'x' * 48000
            bounds[case['case_id'] + '.' + stage] = checks.request_bound(body, stage)
    plan = {'version': VERSION, 'budget_usd': budget_usd, 'model': checks.MODEL, 'prices': checks.PRICES,
            'code_hashes': code_hashes(), 'max_calls': len(bounds), 'request_bounds_usd': bounds,
            'input_hashes': {c['case_id']: digest(c['input']) for c in cases},
            'prompts': {'map': MAP, 'check': CHECK, 'repair': REPAIR}, 'automatic_retries': 0,
            'files': {str(p.relative_to(output)): file_hash(p) for p in sorted(output.rglob('*')) if p.is_file()},
            'independent_validation': False, 'max_repairs_per_answer': 1}
    plan['experiment_id'] = digest(plan)
    write_json(output / 'plan.json', plan)
    return plan


def verify_files(output, manifest):
    for relative, sha in manifest.items():
        path = (output / relative).resolve()
        if not path.is_relative_to(output.resolve()) or file_hash(path) != sha:
            raise ValueError('Frozen artifact changed: ' + relative)


async def run(output: Path, *, budget_usd: float, api_key='', client=None):
    import openai
    plan = json.loads((output / 'plan.json').read_text())
    if plan['version'] != VERSION or digest({k: v for k, v in plan.items() if k != 'experiment_id'}) != plan['experiment_id']:
        raise ValueError('Invalid plan identity')
    if plan['code_hashes'] != code_hashes() or budget_usd != plan['budget_usd']:
        raise ValueError('Implementation/cap changed; use a new experiment')
    verify_files(output, plan['files'])
    owned = client is None
    if owned:
        client = openai.AsyncOpenAI(api_key=api_key, max_retries=0, timeout=180)
    try:
        with (output / 'run.lock').open('w') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if (output / 'results-manifest.json').exists():
                verify_files(output, json.loads((output / 'results-manifest.json').read_text()))
            budget = checks.Budget(plan, output)
            halted = any(json.loads(p.read_text()).get('fatal_provider_error') for p in (output / 'calls').glob('*.json'))
            results = []
            for case in json.loads((output / 'cases.json').read_text()):
                async def invoke(stage, **kwargs):
                    nonlocal halted
                    key = case['case_id'] + '.' + stage
                    body = make_request(case, stage, output, **kwargs)
                    if checks.request_bound(body, stage) > plan['request_bounds_usd'][key] + 1e-12:
                        raise ValueError('Adaptive request exceeds frozen allowance')
                    request_path = output / 'requests' / (key + '.json')
                    if request_path.exists() and json.loads(request_path.read_text()) != body:
                        raise ValueError('Request changed during replay')
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
                    return parse(case, stage, call, kwargs.get('mapping'))
                results.append(await evaluate(case, invoke))
                write_json(output / 'results.json', results)
                print(f"Recorded {len(results)} cases; accounted ${sum(budget.charges.values()):.5f}/${budget.limit:.2f}", flush=True)
            calls = [json.loads(p.read_text()) for p in sorted((output / 'calls').glob('*.json'))]
            report = {'experiment_id': plan['experiment_id'], 'cases': len(results),
                      'statuses': dict(Counter(r['status'] for r in results)),
                      'checks': dict(Counter(r['stages'].get('check', {}).get('verdict', 'not_checked') for r in results)),
                      'repairs_verified': sum(r['repaired'] for r in results),
                      'calls': len(calls), 'completed_calls': sum(c['status'] == 'completed' for c in calls),
                      'parse_errors': sum(bool(s.get('error')) for r in results for s in r['stages'].values()),
                      'cost_estimate_usd': sum(answers.exact_cost(c) or 0 for c in calls),
                      'accounted_usd': sum(budget.charges.values()), 'allowance_violation': budget.violated,
                      'unknown_usage_calls': sum(c.get('usage') is None for c in calls),
                      'budget_usd': budget.limit, 'independent_validation': False}
            write_json(output / 'report.json', report)
            write_json(output / 'results-manifest.json', {str(p.relative_to(output)): file_hash(p)
                for p in sorted(output.rglob('*')) if p.is_file()
                and (p.parent.name in {'calls', 'requests'} or p.name in {'results.json', 'report.json'})})
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
    paid = sub.add_parser('run')
    paid.add_argument('output', type=Path)
    paid.add_argument('--budget-usd', type=float, required=True)
    args = parser.parse_args()
    if args.command == 'prepare':
        plan = prepare(args.packet, args.output)
        print(json.dumps({k: plan[k] for k in ('experiment_id', 'budget_usd', 'max_calls')}))
    else:
        import os
        from dotenv import dotenv_values
        key = os.getenv('OPENAI_API_KEY') or dotenv_values('.env').get('OPENAI_API_KEY')
        print(json.dumps(asyncio.run(run(args.output, budget_usd=args.budget_usd, api_key=key))))


if __name__ == '__main__':
    main()
