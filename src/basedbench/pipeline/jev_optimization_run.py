"""Finite GEPA search over a constrained Jev policy, with external accounting.

GEPA sees opaque examples and training-only diagnostic feedback. All paid calls
pass through ProviderStore; final outer evaluation starts after all searches.
"""
from __future__ import annotations

import argparse
import fcntl
from importlib.metadata import version
import json
import os
from pathlib import Path
import platform

from basedbench.pipeline.curation_corpus import canonical_json, digest, file_hash
from basedbench.pipeline.jev_decomposition_run import atomic
from basedbench.pipeline import jev_decomposition_questions as questions
from basedbench.pipeline import jev_optimization_policy as policy
from basedbench.pipeline import jev_optimization_protocol as protocol
from basedbench.pipeline.jev_optimization_io import BudgetStop, ProviderStore


REFLECTION_TEMPLATE = """Optimize a JSON policy for a fast typed classifier that decides whether
a candidate explanation gets the intended joke in a meme. Improve detection of
missing decoding steps while preserving complete answers. This is not a test of
whether the answer explains why humor is amusing, or whether the meme is suitable
for a benchmark. Do not require incidental facts, every comment, or a vote quota.
Source comments can be explanations, riffs, alternatives or unsupported claims.
Machine image observations can be wrong. Expected decisions are imperfect human
development labels; do not invent a missing rationale for them.

The current policy is:
<curr_param>

Training-only evidence and decisions:
<side_info>

Return exactly one replacement JSON object inside a single fenced code block.
Keep exactly these keys: version (integer 1); role_instruction, need_instruction,
coverage_instruction, verdict_instruction (generic strings, 50-2500 characters
each); essential_threshold, coverage_threshold, failure_threshold (numbers
0.4 through 0.95); aggregation (hybrid, evidence_only, or broad_guarded).
Role and need are classified before seeing the answer. Coverage checks each unit
against the unchanged answer. The last Choice returns pass/fail/uncertain.
Fixed rules: essential means need essential at essential_threshold; strong failure
means essential coverage missing or contradicted at failure_threshold; covered
means covered at coverage_threshold. Hybrid fails on strong essential failures
or native fail, passes only native pass plus all essential units covered, and
otherwise defers. Evidence_only uses essential coverage and defers if none are
essential. Broad_guarded follows native Choice except strong essential failures.
Keep rules generic. Never insert case IDs, literal answers, named example memes,
lookup tables, executable code, new keys or changes to labels or the evaluator.
Avoid overly strict omission checks that mistake background for required decoding.
"""


def code_identity() -> dict:
    here = Path(__file__).resolve().parent
    repo = here.parents[2]
    paths = [*sorted(here.glob('jev_optimization_*.py')),
             here / 'jev_decomposition_questions.py', here / 'jev_decomposition_run.py',
             here / 'curation_corpus.py', repo / 'pyproject.toml', repo / 'uv.lock']
    return {'files': {str(p.relative_to(repo)): file_hash(p) for p in paths},
            'python': platform.python_version(),
            'packages': {p: version(p) for p in ('gepa', 'scikit-learn', 'openai', 'httpx')},
            'reflection_template_sha256': digest(REFLECTION_TEMPLATE)}


def _choices(labels: list[str], winner: str) -> dict:
    return {'choice': winner, 'confidence': 1.,
            'probabilities': {label: float(label == winner) for label in labels}}


def fake_evidence(case: dict) -> tuple[dict, dict]:
    """Only for byte-limit preflight; these are never scored as model outputs."""
    roles, coverage = {}, {}
    for unit in policy.source_units(case):
        uid = unit['id']
        roles['role_' + uid] = _choices(
            ['core_decoding', 'context', 'riff', 'competing', 'irrelevant', 'unclear'], 'core_decoding')
        roles['need_' + uid] = _choices(['essential', 'helpful', 'unrelated', 'unclear'], 'essential')
        coverage['coverage_' + uid] = _choices(
            ['covered', 'missing', 'contradicted', 'not_applicable', 'unresolved'], 'covered')
    return roles, coverage


def prepare(source: Path, root: Path) -> dict:
    plan = protocol.load(root)[0] if (root / 'plan.json').exists() else protocol.prepare(source, root)
    _, cases = protocol.load(root)
    preflight, holds = [], []
    for cid in plan['case_ids']:
        row = cases[cid]
        try:
            roles, coverage = fake_evidence(row)
            bodies = (policy.role_requests(row, policy.SEED_POLICY)
                      + policy.coverage_requests(row, policy.SEED_POLICY, roles)
                      + [policy.verdict_request(row, policy.SEED_POLICY, roles, coverage)])
            for body in bodies:
                questions.validate_request(body)
            preflight.append({'case_id': cid, 'units': len(policy.source_units(row)),
                              'calls': len(bodies),
                              'questions': sum(len(b['questions']) for b in bodies),
                              'max_request_bytes': max(len(canonical_json(b).encode()) for b in bodies)})
        except ValueError as exc:
            holds.append({'case_id': cid, 'reason': str(exc)})
    preview_case = cases[plan['case_ids'][0]]
    previews = {'jev_stage_one': policy.role_requests(preview_case, policy.SEED_POLICY)[0],
                'reflection_template': REFLECTION_TEMPLATE,
                'reflection_fields': ['policy', 'training input', 'typed trace',
                                      'expected pass/fail', 'success/failure'],
                'reflection_excluded': ['exact human notes', 'provenance', 'images',
                                        'validation cases', 'outer-test cases']}
    from gepa.core.data_loader import ListDataLoader
    from gepa.strategies.instruction_proposal import InstructionProposalSignature
    prompt_sizes = []
    for fold in plan['folds']:
        train, _, _ = protocol.example_sets(plan, cases, fold['fold'])
        loader = ListDataLoader(train)
        sampler = BalancedTrainingSampler(train, cases, 4001 + fold['fold'])
        for _ in range(6):
            feedback = []
            for ex in loader.fetch(sampler.next_minibatch_ids(loader, None)):
                row = cases[ex['case_id']]
                roles, coverage = fake_evidence(row)
                result = policy.decide(row, policy.SEED_POLICY, roles, coverage,
                    {'adequacy': _choices(['pass', 'fail', 'uncertain'], 'pass')})
                feedback.append({'diagnostic_json': canonical_json(protocol.feedback(ex, row, result))})
            prompt = InstructionProposalSignature.prompt_renderer({
                'current_instruction_doc': canonical_json(policy.SEED_POLICY),
                'dataset_with_feedback': feedback, 'prompt_template': REFLECTION_TEMPLATE})
            prompt_sizes.append(len(prompt.encode('utf-8')))
            previews.setdefault('reflection_example_synthetic_trace', {
                'model': 'gpt-6-sol', 'input': prompt, 'reasoning': {'effort': 'medium'},
                'max_output_tokens': 4000, 'store': False, 'service_tier': 'default'})
    if max(prompt_sizes) > 40000:
        raise ValueError('Seed reflection input exceeds byte limit')
    manifest = {'version': 1, 'plan_sha256': file_hash(root / 'plan.json'),
                'identity': code_identity(), 'preflight': preflight, 'holds': holds,
                'max_proposals_per_fold': 6, 'max_metric_calls_per_fold': 200,
                'reflection_minibatch_size': 2,
                'reflection_sampling': 'one repair family plus paired-ready or rotating ready family',
                'seed_reflection_prompt_max_bytes': max(prompt_sizes),
                'authorization': 'User reviewed the finite $5 proposal and approved trying it; '
                    'human notes stay local; only training label-derived verdict feedback goes to OpenAI.',
                'request_preview_sha256': digest(previews)}
    frozen = root / 'execution.json'
    if frozen.exists():
        if json.loads(frozen.read_text()) != manifest:
            raise ValueError('Execution identity already frozen and differs')
    else:
        atomic(root / 'request-preview.json', previews)
        atomic(frozen, manifest)
    return {'eligible': len(plan['case_ids']), 'preflight_holds': holds,
            'seed_calls_upper': sum(x['calls'] for x in preflight),
            'seed_questions_upper': sum(x['questions'] for x in preflight),
            'seed_reflection_prompt_max_bytes': max(prompt_sizes),
            'identity': manifest['identity']}


def check_execution(root: Path) -> dict:
    saved = json.loads((root / 'execution.json').read_text())
    if (saved['identity'] != code_identity()
        or saved['plan_sha256'] != file_hash(root / 'plan.json')
        or saved['request_preview_sha256'] != digest(json.loads((root / 'request-preview.json').read_text()))):
        raise ValueError('Frozen execution code, environment, plan or preview changed')
    return saved


def execute_policy(row: dict, candidate: dict, store, phase: str) -> dict:
    roles, coverage = {}, {}
    # Compiler guards are explicit holds, never silent source truncation.
    try:
        role_bodies = policy.role_requests(row, candidate)
    except ValueError as exc:
        if not str(exc).startswith('Case held:'):
            raise
        return {'prediction': 'uncertain', 'trace': {'hold': str(exc)}}
    for body in role_bodies:
        roles.update(store.jev(body, phase))
    try:
        coverage_bodies = policy.coverage_requests(row, candidate, roles)
    except ValueError as exc:
        if not str(exc).startswith('Case held:'):
            raise
        return {'prediction': 'uncertain', 'trace': {'hold': str(exc)}}
    for body in coverage_bodies:
        coverage.update(store.jev(body, phase))
    try:
        body = policy.verdict_request(row, candidate, roles, coverage)
    except ValueError as exc:
        if not str(exc).startswith('Case held:'):
            raise
        return {'prediction': 'uncertain', 'trace': {'hold': str(exc)}}
    verdict = store.jev(body, phase)
    return policy.decide(row, candidate, roles, coverage, verdict)


class Evaluations:
    def __init__(self, root: Path, plan: dict, cases: dict, store):
        self.root, self.plan, self.cases, self.store = root, plan, cases, store
        self.path = root / 'evaluations.json'
        self.state = json.loads(self.path.read_text()) if self.path.exists() else {'complete': {}, 'pending': None}
        if self.state['pending'] is not None:
            raise BudgetStop('Interrupted case evaluation; preserve partial run for review')
        for key, sha in self.state['complete'].items():
            p = root / 'evaluations' / (key + '.json')
            if file_hash(p) != sha:
                raise ValueError('Evaluation cache changed')

    @staticmethod
    def key(row: dict, candidate: dict) -> str:
        # No gold or human notes influence model/cache identity.
        return digest({'policy': candidate, 'input': {
            'explanation': row['input']['explanation'], 'comments': row['comments'],
            'observation': row['observation']}})

    def evaluate(self, candidate: str | dict, example: dict, phase='search') -> dict:
        candidate = policy.parse_policy(candidate)
        row = self.cases[example['case_id']]
        key = self.key(row, candidate)
        path = self.root / 'evaluations' / (key + '.json')
        if key in self.state['complete']:
            item = json.loads(path.read_text())
            if item['key'] != key or item['policy'] != candidate:
                raise ValueError('Evaluation identity mismatch')
            return item['result']
        ceiling = self.plan['max_case_evaluations']
        if phase == 'search':
            ceiling -= self.plan['final_evaluation_reserve']
        if len(self.state['complete']) >= ceiling:
            raise BudgetStop('Actual case-policy evaluation ceiling reached')
        self.state['pending'] = key
        atomic(self.path, self.state)
        result = execute_policy(row, candidate, self.store, phase)
        atomic(path, {'key': key, 'policy': candidate, 'result': result, 'phase': phase})
        self.state['complete'][key] = file_hash(path)
        self.state['pending'] = None
        atomic(self.path, self.state)
        return result

    def evaluator(self, candidate: str, example: dict) -> tuple[float, dict]:
        result = self.evaluate(candidate, example)
        row = self.cases[example['case_id']]
        info = protocol.feedback(example, row, result)
        # GEPA's recursive markdown renderer is verbose: preserve exact feedback
        # in compact JSON instead. No examples/labels are provided otherwise.
        return protocol.score(example, row, result['prediction']), (
            {'diagnostic_json': canonical_json(info)} if info else {})


class BalancedTrainingSampler:
    """Spend the small proposal budget on both classes, with paired contrasts.

    Labels are consulted locally. The sampler can access training examples only;
    it rotates repair families, preferring their corrected ready versions.
    """
    def __init__(self, train: list[dict], cases: dict, seed: int):
        self.train, self.cases, self.seed, self.step = train, cases, seed, 0
        self.allowed = {e['case_id'] for e in train}
        if any(e['partition'] != 'train' for e in train):
            raise ValueError('Sampler received non-training example')

    def next_minibatch_ids(self, loader, state):
        ids = list(loader.all_ids())
        items = loader.fetch(ids)
        by_case = {item['case_id']: item_id for item_id, item in zip(ids, items, strict=True)}
        if set(by_case) != self.allowed:
            raise ValueError('Sampler loader contains different examples')
        repairs = [cid for cid in by_case if self.cases[cid]['gold'] == 'repair']
        ready = [cid for cid in by_case if self.cases[cid]['gold'] == 'ready']
        families = sorted({self.cases[cid]['group_id'] for cid in repairs},
                          key=lambda group: digest([self.seed, group]))
        group = families[self.step % len(families)]
        variants = sorted(cid for cid in repairs if self.cases[cid]['group_id'] == group)
        repair = variants[(self.step // len(families)) % len(variants)]
        matches = [cid for cid in ready if self.cases[cid]['group_id'] == group]
        choices = sorted(matches or ready, key=lambda cid: digest([self.seed, cid]))
        positive = choices[self.step % len(choices)]
        self.step += 1
        return [by_case[repair], by_case[positive]]


def select_candidate(candidates: list[dict], validation: list[dict], cases: dict, evaluations: Evaluations) -> tuple[dict, dict]:
    target = sum(cases[e['case_id']]['gold'] == 'ready'
                 and cases[e['case_id']]['baseline']['broad'] == 'pass' for e in validation)
    stats = []
    for index, candidate in enumerate(candidates):
        predictions = {e['case_id']: evaluations.evaluate(candidate, e)['prediction'] for e in validation}
        stats.append({'index': index,
            'ready_passed': sum(cases[c]['gold'] == 'ready' and p == 'pass' for c, p in predictions.items()),
            'repair_caught': sum(cases[c]['gold'] == 'repair' and p == 'fail' for c, p in predictions.items()),
            'uncertain': sum(p == 'uncertain' for p in predictions.values())})
    eligible = [s for s in stats if s['ready_passed'] >= target]
    selected = max(eligible, key=lambda s: (s['repair_caught'], s['ready_passed'], -s['uncertain'], -s['index'])) if eligible else stats[0]
    return candidates[selected['index']], {'candidates': stats, 'broad_ready_target': target,
                                         'selected_index': selected['index'], 'seed_fallback': not eligible}


def search_fold(root: Path, plan: dict, cases: dict, fold_id, evaluations: Evaluations, store, manifest: dict) -> dict:
    from gepa.optimize_anything import optimize_anything, GEPAConfig, EngineConfig, ReflectionConfig
    from gepa.strategies.instruction_proposal import InstructionProposalSignature
    train, validation, _ = protocol.example_sets(plan, cases, fold_id)
    directory = root / 'search' / str(fold_id)
    frozen = directory / 'frozen.json'
    if frozen.exists():
        item = json.loads(frozen.read_text())
        if item['sha256'] != digest(item['payload']):
            raise ValueError('Frozen fold result changed')
        return item['payload']
    if directory.exists():
        raise BudgetStop('Incomplete GEPA fold exists; no automatic search restart')
    directory.mkdir(parents=True)
    reflections = []
    abort = None

    def check_abort():
        if abort is not None:
            raise BudgetStop('Reflection aborted; no further provider calls') from abort

    def reflect(prompt):
        nonlocal abort
        check_abort()
        try:
            if len(reflections) >= manifest['max_proposals_per_fold']:
                raise BudgetStop('Reflection proposal cap')
            raw = store.reflect(prompt, 'search')
            parsed = policy.parse_policy(InstructionProposalSignature.output_extractor(raw)['new_instruction'])
            reflections.append(policy.policy_id(parsed))
            atomic(directory / 'reflections.json', reflections)
            return '```json\n' + canonical_json(parsed) + '\n```'
        except Exception as exc:
            # GEPA 0.1.4 can swallow/retry proposer exceptions. Make the abort
            # sticky across callbacks, evaluator calls, and the returned result.
            abort = exc
            atomic(directory / 'reflection-abort.json', {'type': type(exc).__name__, 'reason': str(exc)})
            raise

    def evaluate(candidate, example):
        check_abort()
        return evaluations.evaluator(candidate, example)

    result = optimize_anything(canonical_json(policy.SEED_POLICY), evaluator=evaluate,
        dataset=train, valset=validation,
        config=GEPAConfig(engine=EngineConfig(run_dir=str(directory / 'gepa'),
            seed=4001 + int(fold_id), max_candidate_proposals=manifest['max_proposals_per_fold'],
            max_metric_calls=manifest['max_metric_calls_per_fold'], parallel=False,
            capture_stdio=False, raise_on_exception=True, track_best_outputs=False,
            frontier_type='instance', use_cloudpickle=False),
            reflection=ReflectionConfig(reflection_lm=reflect,
                reflection_minibatch_size=manifest['reflection_minibatch_size'],
                batch_sampler=BalancedTrainingSampler(train, cases, 4001 + int(fold_id)),
                skip_perfect_score=False, perfect_score=None,
                reflection_prompt_template=REFLECTION_TEMPLATE)))
    check_abort()
    candidates = [policy.parse_policy(next(iter(candidate.values()))) for candidate in result.candidates]
    winner, selection = select_candidate(candidates, validation, cases, evaluations)
    payload = {'fold': fold_id, 'policy': winner, 'policy_id': policy.policy_id(winner),
               'selection': selection, 'reflections': reflections,
               'gepa_metric_calls': result.total_metric_calls,
               'gepa_candidate_count': len(candidates)}
    atomic(directory / 'gepa-result.json', result.to_dict())
    atomic(frozen, {'payload': payload, 'sha256': digest(payload)})
    return payload


def run(root: Path, *, api_key='', jev_api_key='') -> dict:
    root = Path(root).resolve()
    with (root / 'run.lock').open('a') as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        plan, cases = protocol.load(root)
        manifest = check_execution(root)
        if (root / 'complete.json').exists():
            return replay(root)
        store = ProviderStore(root, plan, api_key=api_key, jev_api_key=jev_api_key)
        try:
            evaluations = Evaluations(root, plan, cases, store)
            winners = []
            for fold in plan['folds']:
                print('Searching fold', fold['fold'], flush=True)
                winners.append(search_fold(root, plan, cases, fold['fold'], evaluations, store, manifest))
                print('Fold frozen', fold['fold'], store.report(), flush=True)
            atomic(root / 'policies.json', winners)
            records = []
            for winner in winners:
                _, _, test = protocol.example_sets(plan, cases, winner['fold'])
                for method, candidate in [('seed', policy.SEED_POLICY), ('optimized', winner['policy'])]:
                    for example in test:
                        result = evaluations.evaluate(candidate, example, 'final')
                        records.append({'case_id': example['case_id'], 'fold': winner['fold'],
                                        'method': method, 'prediction': result['prediction'],
                                        'policy_id': policy.policy_id(candidate), 'result': result})
                        atomic(root / 'records.json', records)
                print('Final fold evaluated', winner['fold'], flush=True)
            report = protocol.summarize(cases, records)
            report['provider_ledger'] = store.report()
            report['actual_case_evaluations'] = len(evaluations.state['complete'])
            report['status'] = 'complete'
            report['excluded'] = plan.get('excluded', [])
            atomic(root / 'report.json', report)
            final_paths = [root / 'report.json', root / 'policies.json', root / 'records.json',
                           root / 'evaluations.json', root / 'provider-ledger.json']
            final_paths += sorted((root / 'search').glob('*/frozen.json'))
            atomic(root / 'complete.json', {'files': {str(p.relative_to(root)): file_hash(p) for p in final_paths}})
            return report
        except BaseException as exc:
            atomic(root / 'partial.json', {'status': 'partial', 'exception_type': type(exc).__name__,
                                          'reason': str(exc), 'provider_ledger': store.report()})
            raise
        finally:
            store.close()


def replay(root: Path) -> dict:
    """Recompute all final decisions and metrics from verified cached calls."""
    check_execution(root)
    plan, cases = protocol.load(root)
    complete = json.loads((root / 'complete.json').read_text())
    for relative, sha in complete['files'].items():
        if file_hash(root / relative) != sha:
            raise ValueError('Completed output changed: ' + relative)
    store = ProviderStore(root, plan)
    try:
        Evaluations(root, plan, cases, store)  # Verify every case-result hash too.
        winners = {w['fold']: w for w in json.loads((root / 'policies.json').read_text())}
        records = json.loads((root / 'records.json').read_text())
        for row in records:
            candidate = policy.SEED_POLICY if row['method'] == 'seed' else winners[row['fold']]['policy']
            recomputed = execute_policy(cases[row['case_id']], candidate, store, 'final')
            if recomputed != row['result']:
                raise ValueError('Decision replay mismatch: ' + row['case_id'])
        summary = protocol.summarize(cases, records)
        report = json.loads((root / 'report.json').read_text())
        ledger = store.report()
        if ledger['pending_calls'] or ledger['stop_reason'] is not None or ledger != report['provider_ledger']:
            raise ValueError('Provider accounting replay mismatch or unresolved calls')
        if any(report[k] != value for k, value in summary.items()):
            raise ValueError('Metric replay mismatch')
        return {'status': 'verified_replay', 'final_decisions': len(records), 'report': report}
    finally:
        store.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['prepare', 'run', 'replay'])
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--source', type=Path)
    parser.add_argument('--env-file', type=Path)
    args = parser.parse_args()
    if args.command == 'prepare':
        if not args.source:
            parser.error('--source required for prepare')
        result = prepare(args.source.resolve(), args.root.resolve())
    elif args.command == 'replay':
        result = replay(args.root.resolve())
    else:
        from dotenv import dotenv_values
        local = dotenv_values(args.env_file) if args.env_file else {}
        result = run(args.root.resolve(), api_key=os.getenv('OPENAI_API_KEY') or local.get('OPENAI_API_KEY', ''),
                     jev_api_key=os.getenv('JEV_API_KEY') or os.getenv('TYPESAFE_API_KEY')
                     or local.get('JEV_API_KEY') or local.get('TYPESAFE_API_KEY', ''))
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
