from copy import deepcopy
import pytest
from app.common import canonical,sha
from app.documents import diff_sources
from app.graphs import validate_graph,preview_update,affected_entities,merge_patch
from app.experiments import compare_graphs

def test_and_or_nested_roundtrip_and_duplicate_claim_rejected(sample):
    _,docs,src,g,_=sample;g=deepcopy(g);node=next(n for n in g['nodes'] if n['id']=='feat_submit')
    expr=node['preconditions']['expression'];a,b=expr['items'];extra=deepcopy(a);extra['id']='claim_alternative'
    expr['items']=[a,{'kind':'any','items':[b,extra]}]
    assert not validate_graph(g,src,docs)
    copy=merge_patch(g,{'operations':[]});assert copy==g
    extra['id']=a['id'];assert any('duplicate ID' in e for e in validate_graph(g,src,docs))

def test_unknown_is_not_empty_requirement(sample):
    _,docs,src,g,_=sample;g=deepcopy(g);node=next(n for n in g['nodes'] if n['node_type']=='Step')
    node['preconditions']={'status':'not_documented','expression':{'kind':'all','items':[]}}
    assert validate_graph(g,src,docs)
    node['preconditions']={'status':'unresolved','expression':None};assert not validate_graph(g,src,docs)

def test_step_claim_workflow_stable_on_reordering(sample):
    store,docs,src,g,tmp=sample
    # Document-only line shift: exact quote relocation, no semantic operation needed.
    p=tmp/'synthetic_manual.md';original=(docs.source_root(src['id'])/'synthetic_manual.md').read_bytes();p.write_bytes(b'\n\n'+original)
    new=docs.import_local(p,'demo-2','Schema Demo','Controlled synthetic')
    preview=preview_update(store,docs,g['graph_id'],new['id'],{'operations':[]})
    assert preview['graph']['nodes']==g['nodes'];assert preview['graph']['lineage_id']==g['lineage_id']
    assert all(e['line_start']==old['line_start']+2 for e,old in zip(preview['graph']['evidence'],g['evidence']))

def test_indirect_output_impact_chain(sample):
    _,_,src,g,_=sample
    # Limit the changed-source witness to the producer feature; output consumer is indirect.
    graph=deepcopy(g);producer=next(n for n in graph['nodes'] if n['id']=='feat_obtain')
    for n in graph['nodes']:
        if n['id']!='feat_obtain':
            for x in __import__('app.graphs',fromlist=['walk']).walk(n):
                if 'evidence_ids' in x:x['evidence_ids']=['unchanged_evidence']
    for r in graph['relations']:r['support']['evidence_ids']=['unchanged_evidence']
    impact=affected_entities(graph,{'files':[{'kind':'modified','old':'synthetic_manual.md'}]})
    assert 'feat_obtain' in impact['direct'];assert 'feat_submit' in impact['indirect'];assert impact['reasons']

def test_add_modify_delete_validated_without_rebuild(sample):
    store,docs,src,g,_=sample
    feature=deepcopy(next(n for n in g['nodes'] if n['id']=='feat_submit'));feature['id']='new_feature';feature['name']['text']='Controlled new goal';feature['workflows']={'status':'not_documented','items':[]}
    # Claims are identity-bearing, not shared between otherwise different conditions.
    for x in __import__('app.graphs',fromlist=['walk']).walk(feature):
        if x.get('kind')=='atom':x['id']='new_'+x['id']
    edge=deepcopy(next(e for e in g['relations'] if e['relation_type']=='CONTAINS' and e['target_id']=='feat_submit'));edge.update(id='new_edge',target_id='new_feature')
    ops=[{'collection':'nodes','op':'add','id':feature['id'],'after':feature,'reason':'controlled explicit addition'}, {'collection':'relations','op':'add','id':edge['id'],'after':edge,'reason':'controlled containment'}]
    p=preview_update(store,docs,g['graph_id'],src['id'],{'operations':ops},manual=True)
    new_id=store.save_graph(p['graph'],src['id'],base_id=g['graph_id'],changes=p['operations'])
    feature_after=deepcopy(feature);feature_after['description']=deepcopy(feature_after['name'])
    p2=preview_update(store,docs,new_id,src['id'],{'operations':[{'collection':'nodes','op':'replace','id':feature['id'],'before':feature,'after':feature_after,'reason':'controlled modification'}]},manual=True)
    assert len(p2['graph']['nodes'])==len(g['nodes'])+1
    id2=store.save_graph(p2['graph'],src['id'],base_id=new_id,changes=p2['operations'])
    p3=preview_update(store,docs,id2,src['id'],{'operations':[{'collection':'relations','op':'remove','id':edge['id'],'before':edge,'reason':'controlled delete edge'},{'collection':'nodes','op':'remove','id':feature['id'],'before':feature_after,'reason':'controlled delete node'}]},manual=True)
    assert p3['graph']['nodes']==g['nodes'];assert store.get('graph',g['graph_id'])==g

def test_no_unadjudicated_fake_precision(sample):
    _,_,_,g,_=sample;r=compare_graphs(g,g,[{'left':g['nodes'][0]['id'],'right':g['nodes'][0]['id'],'accepted':True}],True)
    assert r['node_precision'] is None and r['relation_recall'] is None
    pairs=[{'left':e['id'],'right':e['id'],'accepted':True} for e in g['relations']]
    r=compare_graphs(g,g,reference_is_reviewed=True,reviewed_relation_pairs=pairs,relation_adjudication_complete=True)
    assert r['relation_precision']==r['relation_recall']==1
