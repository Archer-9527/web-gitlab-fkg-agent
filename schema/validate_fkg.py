#!/usr/bin/env python3
"""Validate FKG v0.1 structure and key graph invariants; not semantic truth."""
import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker


def walk(value):
    if isinstance(value, dict):
        yield value
        for item in value.values():
            yield from walk(item)
    elif isinstance(value, list):
        for item in value:
            yield from walk(item)


def atoms(field):
    return {x['id'] for x in walk(field) if x.get('kind') == 'atom'}


def has_cycle(vertices, pairs):
    adjacency = defaultdict(list)
    indegree = dict.fromkeys(vertices, 0)
    for source, target in pairs:
        adjacency[source].append(target)
        indegree.setdefault(source, 0)
        indegree[target] = indegree.get(target, 0) + 1
    stack = [x for x, degree in indegree.items() if degree == 0]
    count = 0
    while stack:
        source = stack.pop()
        count += 1
        for target in adjacency[source]:
            indegree[target] -= 1
            if indegree[target] == 0:
                stack.append(target)
    return count != len(indegree)


def validate(graph, schema, source_root=None):
    Draft202012Validator.check_schema(schema)
    errors = [f'structure {list(e.absolute_path)}: {e.message}'
              for e in Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(graph)]
    if errors:
        return errors
    digest = lambda data: hashlib.sha256(data).hexdigest()
    ids = set()
    for item in walk(graph):
        if 'id' in item:
            if item['id'] in ids:
                errors.append('duplicate ID: ' + item['id'])
            ids.add(item['id'])
    nodes = {n['id']: n for n in graph['nodes']}
    docs = {d['id']: d for d in graph['documents']}
    ev = {e['id']: e for e in graph['evidence']}
    for item in walk(graph):
        for eid in item.get('evidence_ids', []):
            if eid not in ev:
                errors.append('unknown evidence ID: ' + eid)
    for document in docs.values():
        if document['application_version'] != graph['application_version']:
            errors.append('document version mismatch: ' + document['id'])
        if (document['processing_status'] == 'failed') != (document['error'] is not None):
            errors.append('document error/status mismatch: ' + document['id'])
    for evidence in ev.values():
        if evidence['document_id'] not in docs:
            errors.append('unknown document: ' + evidence['document_id'])
        elif docs[evidence['document_id']]['processing_status'] != 'processed':
            errors.append('evidence from unprocessed document: ' + evidence['id'])
        if evidence['line_end'] < evidence['line_start']:
            errors.append('invalid line range: ' + evidence['id'])
        if digest(evidence['quote'].encode('utf-8')) != evidence['fragment_sha256']:
            errors.append('fragment hash mismatch: ' + evidence['id'])
    paths = [d['path'] for d in docs.values()]
    if len(paths) != len(set(paths)):
        errors.append('duplicate document path')
    manifest = ''.join(d['path'] + '\t' + d['content_sha256'] + '\n'
                       for d in sorted(graph['documents'], key=lambda d: d['path']))
    if digest(manifest.encode('utf-8')) != graph['source_snapshot']['manifest_sha256']:
        errors.append('manifest hash mismatch')
    if graph['coverage_status'] == 'complete':
        if any(d['processing_status'] != 'processed' for d in docs.values()):
            errors.append('complete coverage contains unprocessed documents')
        if any(x.get('status') == 'unresolved' for x in walk(graph)):
            errors.append('complete coverage contains unresolved fields')
    if graph['purpose'] == 'production' and graph['application'].lower() == 'gitlab':
        snapshot = graph['source_snapshot']
        if not snapshot['git_tag'] or not snapshot['commit']:
            errors.append('production GitLab graph requires a verified tag and commit')

    parents = defaultdict(list)
    children = defaultdict(list)
    owners = defaultdict(list)
    next_edges = defaultdict(list)
    strict_completions = []
    keys = set()
    for edge in graph['relations']:
        a, b = edge['source_id'], edge['target_id']
        kind = edge['relation_type']
        key = (kind, a, b, json.dumps(edge['details'], sort_keys=True, ensure_ascii=False))
        if key in keys:
            errors.append('duplicate relation: ' + edge['id'])
        keys.add(key)
        if a not in nodes or b not in nodes:
            errors.append('dangling relation: ' + edge['id'])
            continue
        source, target = nodes[a], nodes[b]
        types = source['node_type'], target['node_type']
        if a == b and not (kind == 'NEXT_STEP' and edge['details']['flow_kind'] == 'retry'):
            errors.append('unsupported self relation: ' + edge['id'])
        if kind == 'CONTAINS':
            if types not in [('Module','Module'), ('Module','Feature'), ('Feature','Feature')]:
                errors.append('invalid CONTAINS endpoint types: ' + edge['id'])
            parents[b].append(a)
            children[a].append(b)
        elif kind == 'HAS_STEP':
            if types != ('Feature','Step'):
                errors.append('invalid HAS_STEP endpoint types: ' + edge['id'])
            else:
                owners[b].append(a)
        elif kind == 'NEXT_STEP':
            if types != ('Step','Step'):
                errors.append('invalid NEXT_STEP endpoint types: ' + edge['id'])
            elif source['workflow_id'] != target['workflow_id']:
                errors.append('cross-workflow NEXT_STEP: ' + edge['id'])
            else:
                next_edges[source['workflow_id']].append(edge)
        elif kind == 'REQUIRES_FEATURE':
            if types != ('Feature','Feature'):
                errors.append('invalid REQUIRES_FEATURE endpoint types: ' + edge['id'])
        else:
            if any(t not in ('Feature','Step') for t in types):
                errors.append('invalid dependency endpoint types: ' + edge['id'])
                continue
            if kind == 'REQUIRES_COMPLETION' and edge['details']['guard'] is None:
                strict_completions.append((a, b))
            if kind == 'USES_OUTPUT_OF':
                consumer = atoms(source['preconditions'])
                producer = atoms(target['postconditions'])
                for binding in edge['details']['bindings']:
                    if binding['consumer_condition_id'] not in consumer or binding['producer_state_id'] not in producer:
                        errors.append('invalid output binding: ' + edge['id'])

    root = graph['root_module_id']
    if root not in nodes or nodes[root]['node_type'] != 'Module':
        errors.append('root must reference a Module')
    hierarchy = {nid for nid, node in nodes.items() if node['node_type'] != 'Step'}
    for nid in hierarchy:
        expected = 0 if nid == root else 1
        if len(parents[nid]) != expected:
            errors.append('wrong number of hierarchy parents: ' + nid)
    if has_cycle(hierarchy, [(a, b) for a, group in children.items() for b in group]):
        errors.append('CONTAINS cycle')
    reachable, pending = set(), [root]
    while pending:
        nid = pending.pop()
        if nid in reachable:
            continue
        reachable.add(nid)
        pending.extend(children[nid])
    if hierarchy - reachable:
        errors.append('hierarchy disconnected from root')
    workflows = {}
    for feature in (n for n in nodes.values() if n['node_type'] == 'Feature'):
        for workflow in feature['workflows']['items']:
            workflows[workflow['id']] = (feature['id'], workflow, feature['workflows']['status'])
    workflow_steps = defaultdict(list)
    for step in (n for n in nodes.values() if n['node_type'] == 'Step'):
        wf = workflows.get(step['workflow_id'])
        if len(owners[step['id']]) != 1:
            errors.append('Step must have exactly one owner: ' + step['id'])
        if wf is None or owners[step['id']] != [wf[0]]:
            errors.append('Step workflow/owner mismatch: ' + step['id'])
        workflow_steps[step['workflow_id']].append(step['id'])
    for wfid, (_, workflow, field_status) in workflows.items():
        if field_status == 'recorded' and not workflow_steps[wfid]:
            errors.append('recorded workflow has no steps: ' + wfid)
        edges = next_edges[wfid]
        if workflow['sequence_status'] == 'not_documented' and edges:
            errors.append('undocumented sequence has NEXT_STEP edges: ' + wfid)
        pairs = [(e['source_id'], e['target_id']) for e in edges if e['details']['flow_kind'] != 'retry']
        if has_cycle(workflow_steps[wfid], pairs):
            errors.append('workflow cycle without retry classification: ' + wfid)
    if has_cycle(set(nodes), strict_completions):
        errors.append('unconditional completion dependency cycle')

    if source_root is not None:
        base = Path(source_root).resolve()
        raw_documents = {}
        for document in docs.values():
            path = (base/document['path']).resolve()
            if not path.is_relative_to(base):
                errors.append('document path escapes source root: ' + document['id'])
                continue
            try:
                raw = path.read_bytes()
                raw_documents[document['id']] = raw.decode('utf-8').splitlines()
            except (OSError, UnicodeError) as exc:
                errors.append(f'cannot read source {document["id"]}: {exc}')
                continue
            if digest(raw) != document['content_sha256']:
                errors.append('source content hash mismatch: ' + document['id'])
        for evidence in ev.values():
            lines = raw_documents.get(evidence['document_id'])
            if lines is not None:
                start, end = evidence['line_start'], evidence['line_end']
                if end > len(lines) or '\n'.join(lines[start-1:end]) != evidence['quote']:
                    errors.append('source quote mismatch: ' + evidence['id'])
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('graph', type=Path)
    parser.add_argument('--schema', type=Path, default=Path(__file__).with_name('fkg.schema.json'))
    parser.add_argument('--source-root', type=Path)
    args = parser.parse_args()
    graph = json.loads(args.graph.read_text(encoding='utf-8'))
    schema = json.loads(args.schema.read_text(encoding='utf-8'))
    errors = validate(graph, schema, args.source_root)
    if errors:
        print('\n'.join(errors))
        return 1
    print('PASS: structure and implemented graph invariants. Source entailment and full coverage still require semantic review.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
