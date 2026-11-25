from copy import deepcopy
import pytest
from app.common import uid,canonical
from app.graphs import validate_graph,merge_patch,preview_update,affected_entities
from app.documents import diff_sources,chunks

def test_original_fixture_valid(sample):
    s,d,source,g,_=sample;assert validate_graph(g,source,d)==[]

@pytest.mark.parametrize('mutation,expected',[
 (lambda g:g['nodes'].append(deepcopy(g['nodes'][0])),'duplicate'),
 (lambda g:g['relations'][0].update(target_id='missing'),'dangling'),
 (lambda g:g['documents'][0].update(application_version='other'),'version'),
 (lambda g:g['evidence'][0].update(quote='invented'),'hash'),
 (lambda g:g['evidence'][0].update(line_start=10000,line_end=10000),'quote'),
 (lambda g:g['source_snapshot'].update(manifest_sha256='0'*64),'manifest'),
 (lambda g:g.update(coverage_status='complete'),'complete'),
 (lambda g:g['relations'].append(dict(deepcopy(g['relations'][0]),id='new_edge')),'duplicate'),
])
def test_invalid_graphs(sample,mutation,expected):
    s,d,source,g,_=sample;g=deepcopy(g);mutation(g);errors=validate_graph(g,source,d)
    assert errors and expected in ' '.join(errors).lower()

def test_cross_workflow_edge(sample):
    s,d,source,g,_=sample;g=deepcopy(g)
    edge=next(e for e in g['relations'] if e['relation_type']=='NEXT_STEP');edge['target_id']='step_api'
    assert any('workflow' in e.lower() for e in validate_graph(g,source,d))

def test_output_binding_invalid(sample):
    s,d,source,g,_=sample;g=deepcopy(g)
    edge=next(e for e in g['relations'] if e['relation_type']=='USES_OUTPUT_OF');edge['details']['bindings'][0]['producer_state_id']='missing'
    assert any('binding' in e for e in validate_graph(g,source,d))

def test_nested_and_or_preserved(sample):
    s,d,source,g,_=sample
    node=next(n for n in g['nodes'] if n['id']=='feat_submit')
    assert node['preconditions']['status']=='recorded'
    field=deepcopy(node['preconditions']);clone=deepcopy(node)
    patch={'operations':[{'collection':'nodes','op':'replace','id':node['id'],'before':node,'after':clone,'reason':'no semantic change'}]}
    out=merge_patch(g,patch)
    assert next(n for n in out['nodes'] if n['id']==node['id'])['preconditions']==field
    # Schema distinguishes unresolved and not_documented; neither invents expressions.
    clone['preconditions']={'status':'unresolved','expression':None}
    assert merge_patch(g,patch)['nodes']!=[]

def test_missing_node_delete_requires_relation_cleanup(sample):
    s,d,source,g,_=sample;node=next(n for n in g['nodes'] if n['id']=='feat_submit')
    patch={'operations':[{'collection':'nodes','op':'remove','id':node['id'],'before':node,'reason':'manual delete'}]}
    with pytest.raises(ValueError):preview_update(s,d,g['graph_id'],source['id'],patch,manual=True)
    assert s.get('graph',g['graph_id'])==g

def test_manual_edit_snapshot_id_lineage_and_idempotent_confirm(sample):
    s,d,source,g,_=sample;node=g['nodes'][0];after=deepcopy(node);after['aliases']=[dict(text='alternate',support=deepcopy(node['name']['support']))]
    patch={'operations':[{'collection':'nodes','op':'replace','id':node['id'],'before':node,'after':after,'reason':'human synonym review'}]}
    p=preview_update(s,d,g['graph_id'],source['id'],patch,manual=True)
    assert p['graph']['lineage_id']==g['lineage_id'];assert p['target_graph_id']!=g['graph_id']
    gid=s.save_graph(p['graph'],source['id'],base_id=g['graph_id'],changes=p['operations'],manual_ids=p['touched'],confirmation=p['id'])
    assert s.save_graph(p['graph'],source['id'],confirmation=p['id'])==gid
    assert s.get('graph',g['graph_id'])==g;assert node['id'] in s.manual_ids(gid)
    p2=deepcopy(patch);p2['operations'][0]['before']=after
    with pytest.raises(ValueError,match='manual edit conflicts'):preview_update(s,d,gid,source['id'],p2,manual=False)

def test_stale_before_rejected(sample):
    s,d,source,g,_=sample;n=g['nodes'][0]
    with pytest.raises(ValueError,match='conflict'):merge_patch(g,{'operations':[{'collection':'nodes','op':'replace','id':n['id'],'before':{},'after':n,'reason':'stale'}]})

def test_agent_cannot_accept(sample):
    s,d,source,g,_=sample;n=g['nodes'][0];after=deepcopy(n);after['name']['support']['review_status']='accepted'
    with pytest.raises(ValueError,match='self-accept'):merge_patch(g,{'operations':[{'collection':'nodes','op':'replace','id':n['id'],'before':n,'after':after,'reason':'model confidence'}]})

def test_document_move_preserves_business_ids(sample):
    s,d,old,g,tmp=sample;newdir=tmp/'new';newdir.mkdir();newdir.joinpath('renamed.md').write_bytes((d.source_root(old['id'])/'synthetic_manual.md').read_bytes())
    new=d.import_local(newdir,'demo-2.0','Schema Demo','Controlled synthetic')
    diff=diff_sources(old,new);assert diff['files'][0]['kind']=='moved'
    p=preview_update(s,d,g['graph_id'],new['id'],{'operations':[]})
    assert p['graph']['nodes']==g['nodes'];assert p['graph']['relations']==g['relations']
    assert {e['id'] for e in p['graph']['evidence']}=={e['id'] for e in g['evidence']}
    assert p['operations'] and all(o['collection']=='evidence' for o in p['operations'])

def test_rewrite_not_automatic_delete(sample):
    s,d,old,g,tmp=sample;p=tmp/'rewrite.md';p.write_text('Entirely rewritten content; search before deleting',encoding='utf-8');new=d.import_local(p,'demo-2.0','Schema Demo','Controlled synthetic')
    diff=diff_sources(old,new);assert any(x['kind']=='missing_unconfirmed' for x in diff['files'])
    with pytest.raises(ValueError,match='unresolved source'):preview_update(s,d,g['graph_id'],new['id'],{'operations':[]})

def test_import_failed_file_not_silent(env):
    s,d,tmp=env;p=tmp/'bad.md';p.write_bytes(b'\xff\xfe')
    src=d.import_local(p,'1.0');assert src['documents'][0]['processing_status']=='failed';assert src['documents'][0]['error']

def test_read_path_traversal_and_tamper(env):
    s,d,tmp=env
    with pytest.raises(ValueError):d.import_local('C:/Windows','1.0')
    p=tmp/'a.md';p.write_text('# A\nEvidence',encoding='utf-8');src=d.import_local(p,'1.0');did=src['documents'][0]['id']
    assert d.read(src['id'],did,1,2)['quote']=='# A\nEvidence'
    (d.source_root(src['id'])/'a.md').write_text('changed',encoding='utf-8')
    with pytest.raises(ValueError,match='modified'):d.read(src['id'],did)

def test_chunk_lines_exact():
    source='# A\nline\n## B\n1. x\n2. y\n';cs=chunks(source,size=2)
    assert cs[0]['heading_path']==['A'];assert all(c['quote']=='\n'.join(source.splitlines()[c['line_start']-1:c['line_end']]) for c in cs)

def test_production_local_rejected(env):
    s,d,tmp=env;p=tmp/'a.md';p.write_text('a')
    with pytest.raises(ValueError,match='unverified'):d.import_local(p,'15.0',purpose='production')
