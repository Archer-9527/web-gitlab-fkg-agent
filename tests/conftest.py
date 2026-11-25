import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.store import Store
from app.documents import Documents
from app.common import ROOT,load
from app.graphs import scaffold,validate_graph

@pytest.fixture
def env(tmp_path):
    store=Store(tmp_path/'data');docs=Documents(store,[tmp_path,ROOT])
    return store,docs,tmp_path

@pytest.fixture
def sample(env):
    store,docs,tmp=env
    source=docs.import_local(ROOT/'fixtures/synthetic/synthetic_manual.md','demo-1.0','Schema Demo','Controlled synthetic')
    g=load(ROOT/'fixtures/synthetic/fkg.example.json');old=g['documents'][0]['id'];g=scaffold(source,g)
    g['documents'][0]['processing_status']='processed'
    for e in g['evidence']:e['document_id']=source['documents'][0]['id']
    assert not validate_graph(g,source,docs)
    store.save_graph(g,source['id'])
    return store,docs,source,g,tmp
