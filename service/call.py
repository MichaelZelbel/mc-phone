"""The provider layer: validate an errand, describe the agent, dial once, read the result.

Every identity value (agent, number, caller name, own number, timezone) comes from the
environment, which systemd fills from /etc/mc-phone/config.env. Nothing here belongs to
one person. The API key is read only inside api(), which only the dialling worker and the
root-run setup reach; the half of the service a bot can talk to never sees it.
"""
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import urllib.error
import urllib.request
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
STATE = Path('/var/lib/mc-phone/attempts')
AGENT_NAME = 'Godspeed phone'
# Emergency lines in the countries the book's readers live in. No errand may dial one.
BLOCKED = {'112', '110', '911', '999', '000', '111', '117', '118', '119', '15', '17', '18'}
DYNAMIC_PLACEHOLDERS = {
    'godspeed_call_brief': 'No errand was given. Agree to nothing; end the call politely.',
    'caller_name': 'the person who set up this assistant',
}


def setting(name, default=None):
    value = os.environ.get('GODSPEED_PHONE_' + name, '').strip()
    return value or default


def timezone():
    try:
        return ZoneInfo(setting('TIMEZONE', 'UTC'))
    except Exception:
        return ZoneInfo('UTC')


def today():
    return dt.datetime.now(timezone()).date()


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None  # a redirect would carry the key somewhere else


def api(path, method='GET', payload=None, timeout=90):
    key = os.environ.get('ELEVENLABS_API_KEY', '').strip()
    if not key:
        raise RuntimeError('ELEVENLABS_API_KEY is not set. On the server it lives in /etc/mc-phone/credentials.env.')
    req = urllib.request.Request('https://api.elevenlabs.io/v1/convai/' + path,
        data=None if payload is None else json.dumps(payload).encode(),
        headers={'xi-api-key': key, 'Content-Type': 'application/json'}, method=method)
    try:
        with urllib.request.build_opener(NoRedirect).open(req, timeout=timeout) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        # The body is never repeated: it can quote the request, and the request carried the key.
        raise RuntimeError('ElevenLabs answered HTTP %d. Not retried.' % exc.code) from None
    except (OSError, ValueError):
        raise RuntimeError('No clear answer from ElevenLabs. Check the provider before trying again.') from None


def validate_job(job):
    if not isinstance(job, dict):
        raise ValueError('The order must be a JSON object.')
    for key in ('job_id', 'mode', 'contact', 'to_number', 'name', 'goal', 'allowed_changes', 'opening'):
        if not isinstance(job.get(key), str) or not job[key].strip():
            raise ValueError('Missing field: ' + key)
    if not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,79}', job['job_id']):
        raise ValueError('job_id may only hold lowercase letters, digits, - and _ (80 at most).')
    if job['mode'] not in ('rehearsal', 'live'):
        raise ValueError('mode must be rehearsal or live.')
    digits = job['to_number'].lstrip('+')
    if digits in BLOCKED or any(digits.endswith(b) and len(digits) - len(b) <= 3 for b in BLOCKED):
        raise ValueError('That looks like an emergency number. No errand may call one.')
    if not re.fullmatch(r'\+[1-9]\d{6,14}', job['to_number']):
        raise ValueError('to_number must be the full international number, like +4930123456.')
    if job['mode'] == 'rehearsal' and job['to_number'] != setting('OWN_NUMBER'):
        raise ValueError('A rehearsal may only call your own number (GODSPEED_PHONE_OWN_NUMBER).')
    if job.get('date'):
        try:
            date = dt.date.fromisoformat(job['date'])
        except ValueError:
            raise ValueError('date must be YYYY-MM-DD.') from None
        if date < today():
            raise ValueError('That date has already passed.')
    if job.get('time') and not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', job['time']):
        raise ValueError('time must be HH:MM, 24-hour.')
    if job.get('party_size') is not None:
        if not isinstance(job['party_size'], int) or not 1 <= job['party_size'] <= 100:
            raise ValueError('party_size must be a whole number.')
    return job


def load_job(path):
    return validate_job(json.loads(Path(path).read_text(encoding='utf-8')))


def brief(job):
    """What the agent is told about this errand. The number it dials is not part of it."""
    data = dict(job)
    data.pop('to_number', None)
    if 'callback_number' not in data and setting('OWN_NUMBER'):
        data['callback_number'] = setting('OWN_NUMBER')
    data['today'] = today().isoformat()
    data['timezone'] = setting('TIMEZONE', 'UTC')
    return json.dumps(data, ensure_ascii=False)


def fingerprint(job):
    return hashlib.sha256(json.dumps(job, sort_keys=True).encode()).hexdigest()[:16]


def agent_config():
    """The agent exactly as this version ships it. Applied on create and on every update."""
    template = (ROOT / 'prompt.txt').read_text(encoding='utf-8')
    return {'conversation_config': {
        'agent': {'first_message': '', 'language': 'en',
            'max_conversation_duration_message': "I'm sorry, I have to end the call now. Thank you and goodbye.",
            'dynamic_variables': {'dynamic_variable_placeholders': DYNAMIC_PLACEHOLDERS},
            'prompt': {'prompt': template, 'llm': setting('MODEL', 'gemini-2.5-flash'), 'temperature': 0,
                'thinking_budget': 0,
                'built_in_tools': {'end_call': {'name': 'end_call', 'params': {'system_tool_type': 'end_call'}}}}},
        # English agents must use turbo v2 or flash v2 (ElevenLabs refuses v2.5 for 'en' with a 400).
        'tts': {'model_id': 'eleven_flash_v2', 'pronunciation_dictionary_locators': [], 'enable_phoneme_tags': False},
        'turn': {'initial_wait_time': -1, 'turn_timeout': -1, 'turn_eagerness': 'eager',
            'speculative_turn': True, 'silence_end_call_timeout': 30},
        'conversation': {'max_duration_seconds': int(setting('MAX_SECONDS', '180'))}},
        'platform_settings': {'privacy': {'record_voice': False}}}


def call(job, approved):
    """Dial once. A second attempt for the same job_id is refused by the ledger file."""
    if approved != fingerprint(job):
        raise ValueError('The approval belongs to a different order.')
    agent, number = setting('AGENT_ID'), setting('NUMBER_ID')
    if not agent or not number:
        raise ValueError('GODSPEED_PHONE_AGENT_ID or GODSPEED_PHONE_NUMBER_ID is not set. Run: mc-phone setup')
    config = api('agents/' + agent)['conversation_config']
    if config['agent']['first_message'] or '{{godspeed_call_brief}}' not in config['agent']['prompt']['prompt']:
        raise ValueError('The agent is not the mc-phone one. Run: mc-phone setup agent')
    STATE.mkdir(parents=True, exist_ok=True)
    ledger = STATE / (job['job_id'] + '.json')
    with ledger.open('x', encoding='utf-8') as f:  # atomic: an existing file means "started, maybe"
        json.dump({'status': 'sending_or_uncertain', 'fingerprint': fingerprint(job)}, f)
    result = api('twilio/outbound-call', 'POST', {
        'agent_id': agent, 'agent_phone_number_id': number, 'to_number': job['to_number'],
        'call_recording_enabled': False,
        'conversation_initiation_client_data': {'dynamic_variables': {
            'godspeed_call_brief': brief(job), 'caller_name': setting('CALLER_NAME', job['name'])}}})
    ledger.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return result


def result(conversation_id):
    if not re.fullmatch(r'conv_[a-z0-9]+', conversation_id):
        raise ValueError('That is not a conversation id.')
    d = api('conversations/' + conversation_id)
    return {'status': d['status'], 'duration_seconds': d.get('metadata', {}).get('call_duration_secs'),
        'outcome': 'needs_review',  # the provider's "done" says the line closed, nothing more
        'transcript': [{'role': t['role'], 'message': t.get('message')} for t in d.get('transcript', [])]}
