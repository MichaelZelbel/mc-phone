"""Shared test scaffolding: the service folder on the path and a reader's config in the environment."""
import json
import os
from pathlib import Path
import sys

SERVICE = Path(__file__).resolve().parent.parent / 'service'
sys.path.insert(0, str(SERVICE))

CONFIG = {
    'GODSPEED_PHONE_CALLER_NAME': 'Sam Example',
    'GODSPEED_PHONE_OWN_NUMBER': '+4917212345678',
    'GODSPEED_PHONE_TIMEZONE': 'Europe/Berlin',
    'GODSPEED_PHONE_AGENT_ID': 'agent_test',
    'GODSPEED_PHONE_NUMBER_ID': 'phnum_test',
    'GODSPEED_PHONE_DAILY_LIMIT': '5',
}
os.environ.update(CONFIG)
os.environ.pop('ELEVENLABS_API_KEY', None)


def example_order():
    return json.loads((Path(__file__).with_name('example-order.json')).read_text(encoding='utf-8'))
