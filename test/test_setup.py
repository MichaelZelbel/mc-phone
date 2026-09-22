import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import _env
import call as phone
import setup

GOOD = phone.agent_config()
GOOD_BACK = {'conversation_config': GOOD['conversation_config']}


class SetupTests(unittest.TestCase):
    def test_existing_agent_by_name_is_updated_not_duplicated(self):
        with patch.dict(os.environ, {'GODSPEED_PHONE_AGENT_ID': ''}), \
             patch.object(phone, 'api', side_effect=[{'agents': [{'name': 'Godspeed phone', 'agent_id': 'existing'}], 'has_more': False}, {}, GOOD_BACK]) as api:
            out = setup.setup_agent()
        self.assertEqual(out['status'], 'updated')
        self.assertEqual(out['agent_id'], 'existing')
        self.assertEqual(api.call_args_list[1].args[:2], ('agents/existing', 'PATCH'))

    def test_configured_agent_is_updated_without_listing(self):
        with patch.object(phone, 'api', side_effect=[{}, GOOD_BACK]) as api:
            out = setup.setup_agent()
        self.assertEqual(out['status'], 'updated')
        self.assertEqual(api.call_args_list[0].args[:2], ('agents/agent_test', 'PATCH'))

    def test_creation_is_a_single_post_carrying_the_shipped_prompt(self):
        with patch.dict(os.environ, {'GODSPEED_PHONE_AGENT_ID': ''}), \
             patch.object(phone, 'api', side_effect=[{'agents': [], 'has_more': False}, {'agent_id': 'new'}, GOOD_BACK]) as api:
            out = setup.setup_agent()
        self.assertEqual(out['status'], 'created')
        create = api.call_args_list[1]
        self.assertEqual(create.args[:2], ('agents/create', 'POST'))
        self.assertEqual(create.args[2]['name'], 'Godspeed phone')
        self.assertIn('{{godspeed_call_brief}}', create.args[2]['conversation_config']['agent']['prompt']['prompt'])

    def test_two_agents_with_the_name_stop_setup(self):
        with patch.dict(os.environ, {'GODSPEED_PHONE_AGENT_ID': ''}), \
             patch.object(phone, 'api', return_value={'agents': [{'name': 'Godspeed phone', 'agent_id': 'a'}, {'name': 'Godspeed phone', 'agent_id': 'b'}], 'has_more': False}):
            with self.assertRaisesRegex(RuntimeError, 'More than one'):
                setup.setup_agent()

    def test_second_page_is_read_and_broken_pagination_stops(self):
        with patch.dict(os.environ, {'GODSPEED_PHONE_AGENT_ID': ''}), \
             patch.object(phone, 'api', side_effect=[{'agents': [], 'has_more': True, 'next_cursor': 'p2'}, {'agents': [{'name': 'Godspeed phone', 'agent_id': 'x'}], 'has_more': False}]):
            self.assertEqual(setup.find_agent(), 'x')
        with patch.object(phone, 'api', return_value={'agents': [], 'has_more': True}):
            with self.assertRaisesRegex(RuntimeError, 'incomplete'):
                setup.find_agent()

    def test_unconfirmed_settings_are_an_error(self):
        wrong = {'conversation_config': {'agent': {'prompt': {'prompt': 'other'}, 'first_message': ''}, 'turn': {'initial_wait_time': -1, 'turn_timeout': -1}}}
        with patch.object(phone, 'api', side_effect=[{}, wrong]):
            with self.assertRaisesRegex(RuntimeError, 'did not come back'):
                setup.setup_agent()

    def test_numbers_are_listed_by_id_and_last_digits_only(self):
        with patch.object(phone, 'api', return_value=[{'phone_number': '+4917212345678', 'phone_number_id': 'phnum_1', 'label': 'mine', 'provider': 'twilio'}]):
            out = setup.list_numbers()
        self.assertEqual(out['numbers'][0]['phone_number_id'], 'phnum_1')
        self.assertEqual(out['numbers'][0]['ends_with'], '5678')
        self.assertNotIn('+4917212345678', str(out))

    def test_write_setting_replaces_and_keeps_the_rest(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'config.env'
            path.write_text('GODSPEED_PHONE_CALLER_NAME=Sam\nGODSPEED_PHONE_AGENT_ID=old\n')
            setup.write_setting('AGENT_ID', 'new', str(path))
            setup.write_setting('NUMBER_ID', 'phnum_9', str(path))
            text = path.read_text()
        self.assertIn('GODSPEED_PHONE_CALLER_NAME=Sam\n', text)
        self.assertIn('GODSPEED_PHONE_AGENT_ID="new"\n', text)
        self.assertNotIn('old', text)
        self.assertIn('GODSPEED_PHONE_NUMBER_ID="phnum_9"\n', text)


if __name__ == '__main__':
    unittest.main()
