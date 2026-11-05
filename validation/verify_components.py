#!/usr/bin/env python3
"""Offline design-catalog checks. This is not component/runtime qualification.

The imported example checker supports only a documented subset of JSON Schema.
Production admission and complete Draft 2020-12 validation belong to OB-089/090.
"""
from pathlib import Path
import collections
import datetime
import hashlib
import json
import re
import sys
from urllib.parse import urlparse
sys.dont_write_bytecode = True
from verify_design import check_value

ROOT = Path(__file__).resolve().parents[1]
def read(path): return json.loads((ROOT/path).read_text(encoding='utf-8'))
def require(condition, message):
    if not condition: raise AssertionError(message)

def run():
    catalog=read('components/catalog.json')
    check_value(catalog,read('components/catalog.schema.json'),ROOT/'components/catalog.schema.json')
    datetime.date.fromisoformat(catalog['review_date'])
    items=catalog['components']; ids=[x['component_id'] for x in items]
    require(len(ids)==52 and len(set(ids))==52,'Expected 52 unique component groups')
    tasks=read('tasks/backlog.json'); by_task={x['id']:x for x in tasks}
    require(set(by_task)=={f'OB-{i:03d}' for i in range(1,97)},'Task IDs must preserve 001-088 and add 089-096')
    qs=read('components/qualification-plan.json')['scenarios']; qids={x['qualification_id'] for x in qs}
    require(qids=={f'Q{i:02d}' for i in range(1,17)},'Expected Q01-Q16')
    for q in qs:
        require(q['status']=='NOT_RUN','Design scenario falsely claims runtime validation')
        require((ROOT/q['specification']).is_file(),'Missing qualification spec')
    for c in items:
        require(set(c['task_ids'])<=set(by_task),'Unknown task reference: '+c['component_id'])
        require(set(c['qualification_ids'])<=qids,'Unknown qualification reference')
        require(len(c['task_ids'])==len(set(c['task_ids'])),'Repeated task reference')
        require(c['pinned_release'] is None and c['artifact_sha256'] is None,'Design catalog must not invent release pins')
        require(c['qualification_state']=='NOT_RUN' and c['runtime_enabled'] is False,'Design catalog is not runtime authorization')
        for u in c['upstream_urls']:
            require(urlparse(u).scheme=='https' and bool(urlparse(u).hostname),'Invalid upstream URL format')
    modes={'control_owned','dependency_adapter','source_review','native_primitive','qualification','deferred'}
    for t in tasks:
        require('component_refs' in t and isinstance(t['component_refs'],list),'Missing component refs '+t['id'])
        require(set(t['component_refs'])<=set(ids),'Unknown component in '+t['id'])
        require(t['reuse_type'] in modes,'Unknown reuse type '+t['id'])
        require(isinstance(t['reuse_notes'],list) and t['reuse_notes'],'Missing task reuse notes '+t['id'])
    baseline=read('validation/baseline_compatibility.json')
    for name,expected in baseline['preserved_files'].items():
        digest=hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
        require(digest==expected['v1_1_sha256']==expected['v1_2_sha256'],'Unexpected protocol/DDL change: '+name)
    for tid,phase in baseline['legacy_task_milestones'].items():
        require(by_task[tid]['milestone']==phase,'Legacy task stage changed: '+tid)
    counts=dict(collections.Counter(t['milestone'] for t in tasks))
    require(counts=={'M0':13,'M1':37,'M2':11,'M3':25,'M4':4,'P2':6},'Unexpected phase distribution')
    sources=read('evidence/reuse_sources.json')['sources']; source_ids={x['source_id'] for x in sources}
    require(source_ids=={f'R{i:02d}' for i in range(1,25)},'Expected R01-R24')
    evidence_doc=(ROOT/'docs/11_decisions_evidence.md').read_text(encoding='utf-8')
    for s in sources:
        require(f"[{s['source_id']}]" in evidence_doc,'Missing human source index')
        for u in s['urls']: require(u in evidence_doc,'Source URL not synchronized: '+u)
    for p in (ROOT/'docs').glob('*.md'):
        for rid in re.findall(r'\[(R\d{2})\]',p.read_text(encoding='utf-8')):
            require(rid in source_ids,'Unknown source reference: '+rid)
    require(len(re.findall(r'\| ADR\d{2} \|',evidence_doc))==22,'Expected 22 ADRs')
    require(read('components/source-reuse-ledger.json')['entries']==[],'Design package should not claim vendored source')
    require(read('components/dependency-lock.template.json')['resolutions']==[],'Template must not claim actual dependency locks')
    for name in ['templates/component-qualification.md','templates/source-reuse-record.json','templates/UPSTREAM_PATCHES.md','tasks/revision_delta.json','tasks/REVISION_v1_2.md','prompts/06_component_admission.md']:
        require((ROOT/name).is_file(),'Missing handoff artifact: '+name)
    result={
      'status':'PASS','scope':'Offline design integrity, not runtime component qualification',
      'component_groups':len(items),'qualification_scenarios':len(qids),'source_groups':len(source_ids),
      'tasks':len(tasks),'legacy_task_ids_and_phases_preserved':88,'new_task_ids':list(range(89,97)),
      'milestones':counts,'decisions':dict(collections.Counter(c['decision'] for c in items)),
      'preserved_protocol_files':list(baseline['preserved_files']),
      'all_component_runtime_statuses':'NOT_RUN',
      'not_validated':['Exact dependency locks and license compliance of a release','Actual SDK behavior or network/OS isolation','Full JSON Schema meta-schema validation','Real providers, Feishu, browser or MCP servers','Native installation, signing and upgrades']
    }
    print(json.dumps(result,ensure_ascii=False,indent=2));return result

if __name__=='__main__':
    try: run()
    except Exception as exc:
        print('FAIL:',exc,file=sys.stderr)
        raise
