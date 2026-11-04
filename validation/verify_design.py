#!/usr/bin/env python3
"""Offline checks for this design package, not product implementation tests.

The example validator implements only the JSON Schema keywords used here. It is
not a general JSON Schema implementation and MUST NOT be reused as production
validation/security code. Runtime implementations should use a maintained,
standards-conforming validator plus tool-specific schemas and policy guards.
"""
from pathlib import Path
import json,re,sys,collections,xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[1]
checks=[]
def passed(name,detail):checks.append({'check':name,'result':'PASS','detail':detail})
def require(cond,message):
 if not cond:raise AssertionError(message)
def read(p):return json.loads(p.read_text())
def resolve(ref,source):
 name,_,fragment=ref.partition('#')
 target=(source.parent/name).resolve() if name else source
 require(target.is_relative_to(ROOT),'Reference escapes package: '+ref)
 data=read(target)
 if fragment:
  require(fragment.startswith('/'),'Only JSON Pointer refs are supported')
  for segment in fragment[1:].split('/'):
   key=segment.replace('~1','/').replace('~0','~');data=data[int(key)] if isinstance(data,list) else data[key]
 return data,target

def check_value(value,schema,source,path='$'):
 if '$ref' in schema:
  target,p=resolve(schema['$ref'],source);check_value(value,target,p,path)
 if 'anyOf' in schema:
  errors=[]
  for s in schema['anyOf']:
   try:check_value(value,s,source,path);break
   except AssertionError as e:errors.append(str(e))
  else:raise AssertionError(path+' did not match anyOf')
 if 'const' in schema:require(value==schema['const'],path+' wrong const')
 if 'enum' in schema:require(value in schema['enum'],path+' wrong enum')
 types=schema.get('type',[]);types=[types] if isinstance(types,str) else types
 match={'null':value is None,'boolean':isinstance(value,bool),'integer':isinstance(value,int) and not isinstance(value,bool),'number':isinstance(value,(int,float)) and not isinstance(value,bool),'string':isinstance(value,str),'object':isinstance(value,dict),'array':isinstance(value,list)}
 if types:require(any(match[t] for t in types),path+' wrong type')
 if isinstance(value,dict):
  require(len(value)<=schema.get('maxProperties',10**9),path+' too many properties')
  for k in schema.get('required',[]):require(k in value,path+' missing '+k)
  props=schema.get('properties',{})
  if schema.get('additionalProperties') is False:require(not(set(value)-set(props)),path+' unexpected properties '+str(set(value)-set(props)))
  for k,s in props.items():
   if k in value:check_value(value[k],s,source,path+'.'+k)
 if isinstance(value,list):
  require(len(value)>=schema.get('minItems',0),path+' too few items');require(len(value)<=schema.get('maxItems',10**9),path+' too many items')
  for i,v in enumerate(value):
   if 'items'in schema:check_value(v,schema['items'],source,f'{path}[{i}]')
 if isinstance(value,str):
  require(len(value)>=schema.get('minLength',0),path+' too short');require(len(value)<=schema.get('maxLength',10**9),path+' too long')
  if 'pattern'in schema:require(re.search(schema['pattern'],value) is not None,path+' pattern mismatch')
 if isinstance(value,(int,float)) and not isinstance(value,bool):
  if 'minimum'in schema:require(value>=schema['minimum'],path+' below minimum')
  if 'maximum'in schema:require(value<=schema['maximum'],path+' above maximum')

def walk(v,fn):
 if isinstance(v,dict):
  fn(v)
  for x in v.values():walk(x,fn)
 elif isinstance(v,list):
  for x in v:walk(x,fn)

def run():
 json_files=list(ROOT.rglob('*.json'))+[ROOT/'contracts/openapi.yaml']
 for p in json_files:read(p)
 passed('JSON syntax',f'{len(json_files)} files parsed')
 for p in (ROOT/'contracts').glob('*.schema.json'):
  def schema_node(node):
   if '$ref'in node:resolve(node['$ref'],p)
   if 'required'in node:
    require(isinstance(node['required'],list),str(p)+' invalid required')
    require(set(node['required'])<=set(node.get('properties',{})),str(p)+' missing property definition')
  walk(read(p),schema_node)
 passed('Schema references and required fields','All local refs resolve and required properties are declared')
 api=read(ROOT/'contracts/openapi.yaml')
 require(api['openapi']=='3.1.0','Unexpected OpenAPI version')
 require(api['security']==[{'LocalBearer':[]}],'Missing API authentication')
 ids=[]
 for path,item in api['paths'].items():
  declared={p['name'] for p in item.get('parameters',[])}
  for method,op in item.items():
   if method not in ['get','post','put','patch','delete']:continue
   ids.append(op['operationId'])
   pd=declared|{p['name'] for p in op.get('parameters',[])}
   require(set(re.findall(r'\{([^}]+)\}',path))<=pd,'Missing path param: '+path)
   require('responses'in op,'Missing responses')
 walk(api,lambda node:resolve(node['$ref'],ROOT/'contracts/openapi.yaml') if '$ref'in node else None)
 require(len(ids)==len(set(ids)),'Duplicate operationId')
 passed('OpenAPI structure',f'{len(ids)} operations, refs and path parameters checked; not full OpenAPI meta-schema validation')
 positives=negatives=0
 for p in (ROOT/'contracts/examples').glob('*.json'):
  name=p.name.split('.')[0];s=ROOT/'contracts'/(name+'.schema.json');v=read(p)
  if '.invalid-'in p.name:
   try:check_value(v,read(s),s)
   except AssertionError:negatives+=1
   else:raise AssertionError('Invalid example accepted: '+p.name)
  else:check_value(v,read(s),s);positives+=1
 passed('Contract examples',f'{positives} positive and {negatives} negative fixtures checked against the documented keyword subset')
 sm=read(ROOT/'contracts/state-machine.json');common=read(ROOT/'contracts/common.schema.json')['$defs']
 for domain,enum in [('task','TaskState'),('operation','OperationState'),('approval','ApprovalState')]:
  transitions=sm[domain]['transitions'];states=set(common[enum]['enum'])
  require(set(transitions)==states,domain+' state definitions differ')
  require(all(x in states for ys in transitions.values() for x in ys),domain+' has unknown target')
 require(sm['approval']['transitions']['CONSUMED']==[],'Consumed grant can revive')
 require('UNKNOWN'in sm['operation']['transitions'],'Missing unknown state')
 passed('State definitions','Enums and transition targets agree; CONSUMED is terminal; textual guards still require implementation')
 tasks=read(ROOT/'tasks/backlog.json');by={t['id']:t for t in tasks}
 require(len(tasks)==96 and len(by)==96,'Expected 96 unique tasks')
 rank={x:i for i,x in enumerate(['M0','M1','M2','M3','M4','P2'])}
 requirements=set();indeg={k:0 for k in by};children=collections.defaultdict(list)
 for t in tasks:
  require(t['status'] in {'TODO','READY','IN_PROGRESS','REVIEW','VERIFIED','DONE','BLOCKED'},'Unknown engineering task status')
  if t['status'] in {'VERIFIED','DONE','BLOCKED'}:
   execution=t.get('execution',{})
   require(execution.get('evidence'),'Task state needs evidence: '+t['id'])
   for path in execution['evidence']:require((ROOT/path).is_file(),'Missing task evidence: '+path)
   if t['status']=='BLOCKED':require(execution.get('blockers'),'Blocked task needs minimum condition: '+t['id'])
   if t['status']=='DONE':require(not execution.get('blockers'),'Done task has unresolved blockers: '+t['id'])
  require(2<=len(t['implementation_steps'])<=4,'Unexpected task granularity '+t['id'])
  for field in ['acceptance','negative_acceptance','validation','evidence_required','outputs','risk','req_ids','docs_refs']:require(t.get(field),t['id']+' missing '+field)
  requirements.update(t['req_ids'])
  for ref in t['docs_refs']:require((ROOT/ref).exists(),'Missing task doc: '+ref)
  for dep in t['depends_on']:
   require(dep in by,'Unknown task dependency '+dep);require(rank[by[dep]['milestone']]<=rank[t['milestone']],'Dependency points to future milestone: '+t['id'])
   indeg[t['id']]+=1;children[dep].append(t['id'])
 ready=collections.deque(k for k,v in indeg.items() if v==0);ordered=[]
 while ready:
  k=ready.popleft();ordered.append(k)
  for c in children[k]:
   indeg[c]-=1
   if indeg[c]==0:ready.append(c)
 require(len(ordered)==len(tasks),'Dependency cycle')
 require(requirements=={f'RQ{i:02d}'for i in range(1,13)},'Missing requirements coverage')
 passed('Task graph',f'96 stable task IDs with evidence-backed states, DAG valid, no future-stage dependencies, 12 requirement groups covered')
 diagrams=list((ROOT/'diagrams').glob('*.svg'))
 require(len(diagrams)==7,'Missing diagrams')
 for p in diagrams:ET.parse(p)
 require(len(list((ROOT/'diagrams').glob('*.png')))==7,'Missing PNG diagrams')
 require(len(list((ROOT/'diagrams').glob('*.mmd')))==7,'Missing Mermaid source')
 passed('Diagram assets','7 SVG XML documents parsed; matching PNG and Mermaid files present; visual review is separate')
 for p in (ROOT/'docs').glob('*.md'):
  for link in re.findall(r'!?\[[^]]*\]\(([^)]+)\)',p.read_text()):
   if not link.startswith(('http://','https://','#')):require((p.parent/link.split('#')[0]).exists(),'Missing linked file '+link)
 passed('Document asset links','All document-local diagram links resolve')
 result={'status':'PASS','scope':'Design integrity only; no real providers, Feishu, OS isolation, signing, or product runtime tested','checks':checks,'task_topological_order':ordered,'not_validated':['Full JSON Schema/OpenAPI meta-schema conformance','RFC8785 digest correctness of synthetic examples','MCP real-server compatibility','Real sandbox egress and file boundaries','Actual OpenBot application behavior','Native installation and upgrades']}
 print(json.dumps(result,ensure_ascii=False,indent=2))
 return result
if __name__=='__main__':
 try:run()
 except Exception as e:print('FAIL:',e,file=sys.stderr);raise
