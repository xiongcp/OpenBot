#!/usr/bin/env python3
"""Read-only validation of this planning package; never runs OpenBot or Git."""
from pathlib import Path
import collections
import json
import re
import sys


def main():
    root = Path(__file__).resolve().parents[1]
    errors = []
    parsed = {}
    for path in sorted(root.rglob('*.json')):
        try:
            parsed[path.relative_to(root).as_posix()] = json.loads(path.read_text(encoding='utf-8'))
        except Exception as exc:
            errors.append(f'{path.relative_to(root)}: {exc}')
    payload = parsed.get('cases/test_cases.json', {})
    cases = payload.get('cases', [])
    ids = [c.get('id') for c in cases]
    if len(cases) != 100 or len(set(ids)) != 100:
        errors.append('Expected exactly 100 unique planned case IDs')
    required = {'id','title','gate','priority','environment','preconditions','steps','expected',
                'evidence','failure_diagnosis','fix_direction','regression','related_tasks',
                'requires_real_environment','status'}
    known_tasks = {f'OB-{n:03d}' for n in range(1,97)}
    for case in cases:
        ident = case.get('id','<missing>')
        if set(case) != required:
            errors.append(f'{ident}: field mismatch')
        if case.get('status') != 'NOT_RUN':
            errors.append(f'{ident}: master plan must remain NOT_RUN; use separate run records')
        if case.get('priority') not in {'P0','P1','P2'}:
            errors.append(f'{ident}: invalid priority')
        if not isinstance(case.get('requires_real_environment'),bool):
            errors.append(f'{ident}: requires_real_environment must be bool')
        for key in ['preconditions','steps','expected','evidence','failure_diagnosis','fix_direction','regression','related_tasks']:
            values = case.get(key)
            if not isinstance(values,list) or not values or any(not isinstance(v,str) or not v.strip() for v in values):
                errors.append(f'{ident}: {key} must be non-empty strings')
        for task in case.get('related_tasks',[]):
            if task not in known_tasks:
                errors.append(f'{ident}: unknown development task {task}')
    counts = dict(collections.Counter(i.split('-')[1] for i in ids if i))
    if counts != {'QA':8,'CORE':44,'MAC':22,'INT':16,'GIT':6,'EVAL':4}:
        errors.append('Case group counts differ from frozen package scope')
    cards = (root/'cases/TEST_CASES.md').read_text(encoding='utf-8')
    for case in cases:
        if cards.count('### '+case['id']+'：') != 1:
            errors.append(f"{case['id']}: missing or duplicate readable case card")
    findings = parsed.get('cases/initial_findings.json',[])
    if len(findings) != 16 or len({f.get('issue_id') for f in findings}) != 16:
        errors.append('Expected 16 initial findings')
    for finding in findings:
        if finding.get('status') != 'OPEN' or finding.get('local_reproduction_status') != 'NOT_RUN':
            errors.append(f"{finding.get('issue_id')}: initial finding state changed")
        if finding.get('introduced_by_sha') is not None or finding.get('verified_on_sha') is not None:
            errors.append(f"{finding.get('issue_id')}: unobserved fix SHA in initial record")
        if finding.get('push_status') != 'NOT_ATTEMPTED':
            errors.append(f"{finding.get('issue_id')}: unobserved push result")
    templates = [p for p in parsed if p.startswith('templates/workflow/') and p.endswith('.template.json')]
    if len(templates) != 7:
        errors.append('Expected seven execution templates')
    for name in templates:
        if parsed[name].get('status') != 'NOT_RUN':
            errors.append(f'{name}: initial template status is not NOT_RUN')
    link_count = 0
    markdown_count = 0
    for path in sorted(root.rglob('*.md')):
        markdown_count += 1
        text = path.read_text(encoding='utf-8')
        in_code = False
        for line in text.splitlines():
            if line.strip().startswith(('```','~~~')):
                in_code = not in_code
            if in_code:
                continue
            for target in re.findall(r'\[[^\]]+\]\(([^)]+)\)',line):
                if re.match(r'^[a-z]+:',target) or target.startswith('#'):
                    continue
                target = target.split('#')[0]
                link_count += 1
                if not (path.parent/target).exists():
                    errors.append(f'{path.relative_to(root)}: broken link {target}')
        if in_code:
            errors.append(f'{path.relative_to(root)}: unmatched code fence')
    result = {'validation_scope':'DELIVERABLE_STRUCTURE_ONLY_NOT_PRODUCT_TESTING',
        'result':'PASS' if not errors else 'FAIL','case_count':len(cases),'case_groups':counts,
        'all_cases_initial_not_run':all(c.get('status')=='NOT_RUN' for c in cases),
        'findings_count':len(findings),'execution_templates':len(templates),
        'parsed_json_files':len(parsed),'markdown_files':markdown_count,
        'relative_links_checked':link_count,'errors':errors,
        'macOS_product_execution':'NOT_RUN','repository_commit_push':'NOT_ATTEMPTED'}
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0 if not errors else 1


if __name__ == '__main__':
    sys.exit(main())
