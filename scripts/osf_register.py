"""
Create the CARMA preregistration on OSF from docs/OSF_REGISTRATION_FORM.md.

    python scripts/osf_register.py check     # validate the form against the OSF template (offline-safe)
    python scripts/osf_register.py draft     # private project + attached protocol + filled draft
    python scripts/osf_register.py submit --embargo-until 2027-10-26   # or --public

`draft` and `submit` need OSF_TOKEN (osf.io/settings/tokens, scope
osf.full_write) in carma-backend/.env.  What was created is kept in
artifacts/preregistration/osf.json, so each step runs once.  A submitted
registration cannot be deleted, only withdrawn: review the draft on OSF first.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FORM = ROOT / 'docs' / 'OSF_REGISTRATION_FORM.md'
ATTACHMENTS = [ROOT / 'docs' / 'OSF_PREREGISTRATION.md', FORM,
               ROOT / 'artifacts' / 'preregistration' / 'seen_cases.json']
STATE = ROOT / 'artifacts' / 'preregistration' / 'osf.json'
ENV = ROOT / 'carma-backend' / '.env'
API = 'https://api.osf.io/v2'
FILES = 'https://files.osf.io/v1'
TEMPLATE = 'OSF Preregistration'
SECTION = re.compile(r'^## (\d+-\d+) · ', re.M)


def request(method: str, url: str, body=None, token: str = '', raw: bytes | None = None):
    headers = {'User-Agent': 'carma-research/1.0', 'Accept': 'application/vnd.api+json'}
    data = raw
    if body is not None:
        data = json.dumps(body).encode('utf-8')
        headers['Content-Type'] = 'application/vnd.api+json'
    if token:
        headers['Authorization'] = f'Bearer {token}'
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=data, headers=headers,
                                                           method=method), timeout=60) as response:
            text = response.read().decode('utf-8')
    except urllib.error.HTTPError as exc:
        sys.exit(f'{method} {url} failed ({exc.code}): {exc.read().decode("utf-8", "replace")[:600]}')
    return json.loads(text) if text else {}


def token() -> str:
    for line in ENV.read_text(encoding='utf-8').splitlines():
        if line.startswith('OSF_TOKEN='):
            value = line.split('=', 1)[1].strip()
            if value:
                return value
    sys.exit(f'Set OSF_TOKEN in {ENV} (osf.io/settings/tokens, scope osf.full_write).')


def parse_form() -> tuple[str, str, dict]:
    text = FORM.read_text(encoding='utf-8')
    title = re.search(r'^\*\*Title\.\*\* (.+)$', text, re.M).group(1).strip()
    description = re.search(r'^\*\*Description\.\*\* (.+)$', text, re.M).group(1).strip()
    marks = list(SECTION.finditer(text))
    answers = {}
    for index, mark in enumerate(marks):
        end = marks[index + 1].start() if index + 1 < len(marks) else len(text)
        section = text[mark.end():end]
        answers[mark.group(1)] = section.split('\n', 1)[1].strip() if '\n' in section else ''
    return title, description, answers


def template() -> tuple[str, dict]:
    """The template's id and its questions: key -> (input type, required, options)."""
    schemas = request('GET', f'{API}/schemas/registrations/?filter[active]=true&page[size]=100')
    schema_id = next(item['id'] for item in schemas['data']
                     if item['attributes']['name'] == TEMPLATE)
    blocks = request('GET', f'{API}/schemas/registrations/{schema_id}/schema_blocks/?page[size]=200')
    questions, current = {}, None
    for block in blocks['data']:
        attributes = block['attributes']
        if attributes.get('registration_response_key'):
            current = attributes['registration_response_key']
            questions[current] = (attributes['block_type'], bool(attributes.get('required')), [])
        elif attributes['block_type'] == 'select-input-option' and current:
            questions[current][2].append(attributes['display_text'].strip())
        else:
            current = None
    return schema_id, questions


def responses() -> tuple[str, str, str, dict]:
    title, description, answers = parse_form()
    schema_id, questions = template()
    problems, filled = [], {}
    for key, (kind, required, options) in questions.items():
        answer = answers.get(key, '')
        if kind == 'file-input':
            continue
        if not answer:
            if required:
                problems.append(f'{key}: required, no answer')
            continue
        if kind in ('single-select-input', 'multi-select-input'):
            if answer not in options:
                problems.append(f'{key}: "{answer[:60]}…" is not one of the template options')
                continue
            filled[key] = answer if kind == 'single-select-input' else [answer]
        else:
            filled[key] = answer
    problems += [f'{key}: not a question of the template' for key in answers if key not in questions]
    if problems:
        sys.exit('The form does not match the template:\n  ' + '\n  '.join(problems))
    return schema_id, title, description, filled


def load_state() -> dict:
    return json.loads(STATE.read_text(encoding='utf-8')) if STATE.exists() else {}


def save_state(state: dict):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state, indent=2), encoding='utf-8')


def draft():
    state = load_state()
    if state.get('draft_id'):
        print(f"Draft exists: https://osf.io/registries/drafts/{state['draft_id']}/review")
        return
    schema_id, title, description, filled = responses()
    secret = token()
    if not state.get('node_id'):
        node = request('POST', f'{API}/nodes/', token=secret, body={'data': {
            'type': 'nodes', 'attributes': {'title': title, 'category': 'project',
                                            'description': description, 'public': False}}})
        state['node_id'] = node['data']['id']
        save_state(state)
    for path in ATTACHMENTS:
        name = urllib.parse.quote(path.name)
        request('PUT', f"{FILES}/resources/{state['node_id']}/providers/osfstorage/"
                       f'?kind=file&name={name}', token=secret, raw=path.read_bytes())
    created = request('POST', f'{API}/draft_registrations/', token=secret, body={'data': {
        'type': 'draft_registrations',
        'relationships': {
            'branched_from': {'data': {'type': 'nodes', 'id': state['node_id']}},
            'registration_schema': {'data': {'type': 'registration-schemas', 'id': schema_id}},
        }}})
    state['draft_id'] = created['data']['id']
    save_state(state)
    request('PATCH', f"{API}/draft_registrations/{state['draft_id']}/", token=secret, body={'data': {
        'type': 'draft_registrations', 'id': state['draft_id'],
        'attributes': {'title': title, 'description': description,
                       'registration_responses': filled}}})
    print(f"Project: https://osf.io/{state['node_id']}/")
    print(f"Draft:   https://osf.io/registries/drafts/{state['draft_id']}/review")


def submit(embargo_until: str | None):
    state = load_state()
    if state.get('registration_id'):
        print(f"Already registered: https://osf.io/{state['registration_id']}/")
        return
    if not state.get('draft_id'):
        sys.exit('No draft yet: run "draft" first.')
    attributes = {'draft_registration': state['draft_id'],
                  'registration_choice': 'embargo' if embargo_until else 'immediate'}
    if embargo_until:
        attributes['lift_embargo'] = f'{embargo_until}T00:00:00'
    created = request('POST', f"{API}/nodes/{state['node_id']}/registrations/", token=token(),
                      body={'data': {'type': 'registrations', 'attributes': attributes}})
    state['registration_id'] = created['data']['id']
    save_state(state)
    print(f"Registered: https://osf.io/{state['registration_id']}/")
    print('Set PREREGISTRATION_URL to this URL in carma-backend/.env.')


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('step', choices=['check', 'draft', 'submit'])
    when = parser.add_mutually_exclusive_group()
    when.add_argument('--embargo-until', metavar='YYYY-MM-DD')
    when.add_argument('--public', action='store_true')
    options = parser.parse_args()
    if options.step == 'check':
        _, title, _, filled = responses()
        print(f'OK: "{title}" answers {len(filled)} questions of the "{TEMPLATE}" template.')
    elif options.step == 'draft':
        draft()
    else:
        if not (options.embargo_until or options.public):
            sys.exit('Choose --embargo-until YYYY-MM-DD or --public.')
        submit(options.embargo_until)


if __name__ == '__main__':
    main()
