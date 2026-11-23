"""Exercise the loaded agent's actual validation tool without LLM or main writes.

Creates one temporary read-only workflow, runs all three validator outcomes,
checks protected files are unchanged, and removes only the temporary file.
"""
from __future__ import annotations
import argparse
import copy
import json
from pathlib import Path
import sys
import time
from uuid import uuid4

import requests

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'agent_runtime'), str(ROOT / 'scripts')]
from build_tool_loop_workflow import Graph, ports
from workflow_parser import parse_workflow
from workflow_validator import validate_workflow


def probe_graph(iterator, bootstrap, include_recovery=False):
    declaration = copy.deepcopy(next(t for t in iterator['metadata']['tools'] if t['name'] == 'workspace.prepare_main_update'))
    template = next(n for n in iterator['nodes'] if n['id'] == 'evolution_validate')
    if template['arguments']['parameters'] != declaration['input_ports'] or template['arguments']['outputs'] != declaration['output_ports']:
        raise ValueError('live iterator node does not match its declared tool interface')
    g = Graph()
    g.doc['description'] = 'Read-only runtime tool probe: no LLM, no main update, no checkpoint operations.'
    inputs = [('file_id', 'content'), ('revision', 'number')] + [('proposal_' + case, 'content') for case in ['unchanged', 'ready', 'rejected']]
    if include_recovery:
        inputs += [('stable_file_id', 'content'), ('checkpoint_seq', 'number')]
    outputs = [(case + '_' + field, 'content') for case in ['unchanged', 'ready', 'rejected'] for field in ['status', 'error']]
    if include_recovery:
        outputs += [('recovery_versions', 'content')]
    g.doc['input_ports'] = ports(inputs)
    g.doc['output_ports'] = ports(outputs)
    g.doc['metadata']['tools'] = [declaration]
    if include_recovery:
        g.doc['metadata']['tools'].append(copy.deepcopy(next(t for t in bootstrap['metadata']['tools'] if t['name'] == 'workspace.get_file_recovery_plan')))
    g.node('in', 'input', arguments={}, workflowPorts=[{'id': 'workflow:' + n, 'name': n, 'type': t} for n, t in inputs])
    previous = 'in'
    for case in ['unchanged', 'ready', 'rejected']:
        g.node(case, 'tool', arguments=copy.deepcopy(template['arguments']))
        g.chain(previous, case)
        for name, kind in [('file_id', 'content'), ('revision', 'number')]:
            g.data('in', 'workflow:' + name, case, name, kind)
        g.data('in', 'workflow:proposal_' + case, case, 'proposal')
        previous = case
    if include_recovery:
        recovery = next(n for n in bootstrap['nodes'] if n.get('arguments', {}).get('tool') == 'workspace.get_file_recovery_plan')
        g.node('recovery', 'tool', arguments=copy.deepcopy(recovery['arguments']))
        g.chain(previous, 'recovery')
        for name, kind in [('file_id', 'content'), ('stable_file_id', 'content'), ('checkpoint_seq', 'number')]:
            g.data('in', 'workflow:' + name, 'recovery', name, kind)
        previous = 'recovery'
    g.node('out', 'output', arguments={}, workflowPorts=[{'id': 'workflow:' + n, 'name': n, 'type': t} for n, t in outputs])
    g.chain(previous, 'out')
    for case in ['unchanged', 'ready', 'rejected']:
        for field in ['status', 'error']:
            g.data(case, field, 'out', 'workflow:' + case + '_' + field)
    if include_recovery:
        g.data('recovery', 'versions', 'out', 'workflow:recovery_versions')
    validate_workflow(g.doc)
    parse_workflow(g.doc)
    return g.doc


def run(url, prefix, report_dir, include_recovery=False):
    report_dir.mkdir(parents=True, exist_ok=True)
    def api(method, path, payload=None):
        response = requests.request(method, url.rstrip('/') + '/api/' + path, json=payload, timeout=(3, 15))
        response.raise_for_status()
        return response.json()
    files = {x['name']: x for x in api('GET', 'files')['items']}
    roles = ['main.flow', 'stable-main.flow', 'experience.md', 'iterator.flow', 'bootstrap.flow']
    before = {role: api('GET', 'files/' + files[prefix + '-' + role]['file_id']) for role in roles}
    (report_dir / 'before.json').write_text(json.dumps(before, ensure_ascii=False, indent=2), encoding='utf-8')
    current = before['main.flow']
    iterator = json.loads(before['iterator.flow']['content'])
    main_id = current['file_id']
    binding = next(n for n in iterator['nodes'] if n['id'] == 'evolution_read_main_file_id')
    if binding['arguments']['append_items'] != [{'type': 'fixed', 'value': main_id}]:
        raise ValueError('live iterator is not bound to the expected main file ID')
    bootstrap = json.loads(before['bootstrap.flow']['content'])
    for node_id, role in [('recovery_plan_file_id', 'main.flow'), ('recovery_plan_stable_file_id', 'stable-main.flow')]:
        bound = next(n for n in bootstrap['nodes'] if n['id'] == node_id)
        if bound['arguments']['append_items'] != [{'type': 'fixed', 'value': before[role]['file_id']}]:
            raise ValueError('live recovery has an incorrect file ID binding: ' + node_id)
    candidate = json.loads(current['content'])
    ready = copy.deepcopy(candidate)
    prompt = next(n for n in ready['nodes'] if n['id'] == 'prompt')
    prompt['arguments']['append_items'].append({'type': 'fixed', 'value': '\nRead-only validation probe: "put" C:\\temp\\apple.'})
    inputs = {'file_id': main_id, 'revision': current['revision'],
              'proposal_unchanged': current['content'], 'proposal_ready': json.dumps(ready),
              'proposal_rejected': '{invalid json'}
    if include_recovery:
        inputs.update({'stable_file_id': before['stable-main.flow']['file_id'], 'checkpoint_seq': 0})
    graph = probe_graph(iterator, bootstrap, include_recovery)
    (report_dir / 'probe.flow').write_text(json.dumps(graph, ensure_ascii=False, indent=2), encoding='utf-8')
    caller = 'bootstrap.flow' if include_recovery else 'iterator.flow'
    permissions = {'runtime': {'read': before[caller]['permissions']['runtime']['read'], 'write': 0},
                   'required': {'read': 2, 'write': 4},
                   'checkpoints': {'read': False, 'create': False, 'restore': False}}
    terminal = 'runtime-tool-probe-' + uuid4().hex
    name = terminal + '.flow'
    created = api('POST', 'files', {'name': name, 'content': json.dumps(graph), 'permissions': permissions})
    report = {'workflow_name': name, 'probe_file_id': created['file_id'], 'main_file_id': main_id,
              'main_revision': current['revision'], 'llm_calls': 0, 'candidate_writes': 0,
              'caller_read_level': permissions['runtime']['read'], 'include_recovery': include_recovery}
    try:
        report['queued'] = api('POST', 'processes', {'workflow_file_id': created['file_id'], 'terminal_id': terminal, 'inputs': inputs})
        print('Probe queued: ' + name, flush=True)
        deadline = time.monotonic() + 50
        result = None
        while time.monotonic() < deadline:
            snapshots = api('GET', 'process-logs?limit=100')['items']
            matches = [p for p in snapshots if p.get('terminal_id') == terminal and p.get('process_type') == 'workflow']
            if matches and matches[0].get('status') in ['completed', 'failed', 'terminated']:
                result = matches[0]
                break
            time.sleep(0.75)
        if result is None:
            raise TimeoutError('probe did not finish in 50 seconds; inspect runtime logs')
        (report_dir / 'process.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        report.update({'process_id': result['process_id'], 'status': result['status'], 'output': result.get('output'), 'error': result.get('error')})
        if result['status'] != 'completed':
            raise RuntimeError('probe failed: ' + str(result.get('error')))
        for case in ['unchanged', 'ready', 'rejected']:
            if result['output'].get(case + '_status') != case:
                raise AssertionError('unexpected tool result: ' + json.dumps(result['output']))
        if include_recovery:
            versions = json.loads(result['output']['recovery_versions'])
            if not isinstance(versions, list):
                raise AssertionError('recovery versions must be a JSON array')
            expected = [] if current['content'] == before['stable-main.flow']['content'] else [{'content': before['stable-main.flow']['content'], 'checkpoint_seq': 0, 'source': 'stable'}]
            if versions != expected:
                raise AssertionError('unexpected stable recovery plan')
            report['output'] = {key: value for key, value in result['output'].items() if key != 'recovery_versions'}
            report['recovery_version_count'] = len(versions)
            report['recovery_checkpoint_seq'] = 0
        report['protected_files_unchanged'] = {}
        for role, original in before.items():
            after = api('GET', 'files/' + original['file_id'])
            unchanged = all(after.get(key) == original.get(key) for key in ['revision', 'content', 'permissions'])
            report['protected_files_unchanged'][role] = unchanged
            if not unchanged:
                raise AssertionError('file changed during probe: ' + role)
        report['success'] = True
        print(json.dumps(report, ensure_ascii=True, indent=2), flush=True)
        return report
    finally:
        # Never enumerate/delete other files; this is the exact freshly created ID.
        api('DELETE', 'files/' + created['file_id'] + '?revision=' + str(created['revision']))
        report['probe_file_deleted'] = True
        (report_dir / 'result.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://127.0.0.1:8081')
    parser.add_argument('--prefix', default='alfworld-hard-paired')
    parser.add_argument('--report-dir', type=Path, default=ROOT / 'tmp/runtime-tool-probe')
    parser.add_argument('--include-recovery', action='store_true', help='Also test recovery with bootstrap read level; no historical checkpoint traversal.')
    args = parser.parse_args()
    run(args.url, args.prefix, args.report_dir, args.include_recovery)
