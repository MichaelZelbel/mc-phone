"""Setup helpers, run as root by install.sh or by `mc-phone setup ...`. None of them dials.

  agent    create the "Godspeed phone" agent in your ElevenLabs workspace, or bring an existing one
           up to the prompt and settings this version ships; prints its id
  numbers  list the phone numbers imported into ElevenLabs (ids and the last digits)
  check    read-only proof that the key works and what the account holds
"""
import json
import os
import urllib.parse

import call as phone

CONFIG_FILE = '/etc/mc-phone/config.env'


def list_agents():
    agents, cursor, seen = [], None, set()
    for _ in range(100):
        path = 'agents?page_size=100'
        if cursor:
            path += '&cursor=' + urllib.parse.quote(cursor, safe='')
        data = phone.api(path)
        agents.extend(data['agents'])
        if not data.get('has_more'):
            return agents
        cursor = data.get('next_cursor')
        if not cursor or cursor in seen:
            raise RuntimeError('The agent list came back incomplete; no agent was created.')
        seen.add(cursor)
    raise RuntimeError('The agent list is too long to read; no agent was created.')


def find_agent():
    matches = [a for a in list_agents() if a.get('name') == phone.AGENT_NAME]
    if len(matches) > 1:
        raise RuntimeError('More than one agent is called "%s". Rename or delete the extra ones in ElevenLabs first.' % phone.AGENT_NAME)
    return matches[0]['agent_id'] if matches else None


def verify_agent(agent_id):
    wanted = phone.agent_config()['conversation_config']
    current = phone.api('agents/' + agent_id)['conversation_config']
    if (current['agent']['prompt']['prompt'] != wanted['agent']['prompt']['prompt']
            or current['agent']['first_message'] != '' or current['agent'].get('language') != 'en'
            or current['turn']['initial_wait_time'] != -1 or current['turn']['turn_timeout'] != -1):
        raise RuntimeError('The agent did not come back with the settings that were sent.')


def setup_agent():
    config = phone.agent_config()
    agent_id = phone.setting('AGENT_ID') or find_agent()
    if agent_id:
        phone.api('agents/' + agent_id, 'PATCH', config)
        status = 'updated'
    else:
        created = phone.api('agents/create', 'POST', dict(config, name=phone.AGENT_NAME, tags=['mc-phone']))
        agent_id = created.get('agent_id')
        if not isinstance(agent_id, str) or not agent_id:
            raise RuntimeError('ElevenLabs did not confirm the new agent. Look at the agent list before trying again.')
        status = 'created'
    verify_agent(agent_id)
    return {'status': status, 'agent_id': agent_id, 'name': phone.AGENT_NAME}


def list_numbers():
    numbers = phone.api('phone-numbers')
    if not isinstance(numbers, list):
        raise RuntimeError('Unexpected answer to the phone number list.')
    out = []
    for n in numbers:
        digits = str(n.get('phone_number') or '')
        out.append({'phone_number_id': n.get('phone_number_id'), 'label': n.get('label'),
                    'ends_with': digits[-4:], 'provider': n.get('provider')})
    return {'numbers': out}


def check():
    agents = list_agents()
    numbers = list_numbers()['numbers']
    return {'status': 'ok', 'agents': len(agents),
            'mc_phone_agent': phone.setting('AGENT_ID') or find_agent(),
            'numbers': len(numbers), 'configured_number': phone.setting('NUMBER_ID')}


def write_setting(name, value, path=CONFIG_FILE):
    """Replace or add one GODSPEED_PHONE_ line in the config file. The file is root's, mode 0600."""
    key = 'GODSPEED_PHONE_' + name
    lines = []
    if os.path.exists(path):
        with open(path, encoding='utf-8') as f:
            lines = [l for l in f.read().splitlines() if not l.startswith(key + '=')]
    lines.append('%s="%s"' % (key, value))  # quoted: systemd strips the quotes, and so does a shell
    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    os.chmod(path, 0o600)


def main(argv):
    what = argv[0] if argv else 'check'
    try:
        if what == 'agent':
            out = setup_agent()
            if '--write' in argv:
                write_setting('AGENT_ID', out['agent_id'])
        elif what == 'numbers':
            out = list_numbers()
        elif what == 'check':
            out = check()
        else:
            raise ValueError('setup takes one of: agent, numbers, check')
        print(json.dumps(out, ensure_ascii=True, indent=2))
        return 0
    except (RuntimeError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({'error': str(exc) if isinstance(exc, (RuntimeError, ValueError)) else 'Unexpected answer shape.'}))
        return 1
