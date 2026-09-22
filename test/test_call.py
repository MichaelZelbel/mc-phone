import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import _env
import call as phone

AGENT_OK = {'conversation_config': {'agent': {'first_message': '', 'prompt': {'prompt': 'x {{godspeed_call_brief}} y'}}}}


class ValidationTests(unittest.TestCase):
    def setUp(self):
        self.job = _env.example_order()

    def test_example_order_is_valid(self):
        self.assertEqual(phone.validate_job(self.job)['job_id'], self.job['job_id'])

    def test_missing_field_is_named(self):
        del self.job['goal']
        with self.assertRaisesRegex(ValueError, 'goal'):
            phone.validate_job(self.job)

    def test_rehearsal_may_only_call_own_number(self):
        self.job['to_number'] = '+4930123456'
        with self.assertRaisesRegex(ValueError, 'own number'):
            phone.validate_job(self.job)

    def test_live_may_call_any_ordinary_number(self):
        self.job.update(mode='live', to_number='+4930123456')
        phone.validate_job(self.job)

    def test_emergency_numbers_are_refused(self):
        for number in ('+49112', '+1911', '+44999', '+49110'):
            self.job.update(mode='live', to_number=number)
            with self.assertRaisesRegex(ValueError, 'emergency'):
                phone.validate_job(self.job)

    def test_past_date_is_refused(self):
        self.job['date'] = '2000-01-01'
        with self.assertRaisesRegex(ValueError, 'passed'):
            phone.validate_job(self.job)

    def test_bad_time_is_refused(self):
        self.job['time'] = '7pm'
        with self.assertRaises(ValueError):
            phone.validate_job(self.job)

    def test_unknown_timezone_falls_back_to_utc(self):
        with patch.dict(os.environ, {'GODSPEED_PHONE_TIMEZONE': 'Mars/Olympus'}):
            self.assertEqual(str(phone.timezone()), 'UTC')


class BriefTests(unittest.TestCase):
    def setUp(self):
        self.job = _env.example_order()

    def test_brief_carries_the_errand_but_not_the_dialled_number(self):
        data = json.loads(phone.brief(self.job))
        self.assertEqual(data['opening'], self.job['opening'])
        self.assertEqual(data['party_size'], 4)
        self.assertNotIn('to_number', data)
        self.assertEqual(data['timezone'], 'Europe/Berlin')

    def test_callback_defaults_to_own_number_unless_chosen(self):
        self.assertEqual(json.loads(phone.brief(self.job))['callback_number'], '+4917212345678')
        self.job['callback_number'] = None
        self.assertIsNone(json.loads(phone.brief(self.job))['callback_number'])
        self.job['callback_number'] = '+49301111'
        self.assertEqual(json.loads(phone.brief(self.job))['callback_number'], '+49301111')


class DialTests(unittest.TestCase):
    def setUp(self):
        self.job = _env.example_order()
        self.tmp = tempfile.TemporaryDirectory()
        self.state = patch.object(phone, 'STATE', Path(self.tmp.name))
        self.state.start()

    def tearDown(self):
        self.state.stop()
        self.tmp.cleanup()

    def test_wrong_approval_cannot_dial(self):
        with patch.object(phone, 'api') as api:
            with self.assertRaises(ValueError):
                phone.call(self.job, 'wrong')
            api.assert_not_called()

    def test_changed_job_invalidates_approval(self):
        approval = phone.fingerprint(self.job)
        self.job['time'] = '18:00'
        with patch.object(phone, 'api') as api:
            with self.assertRaises(ValueError):
                phone.call(self.job, approval)
            api.assert_not_called()

    def test_unconfigured_service_cannot_dial(self):
        with patch.dict(os.environ, {'GODSPEED_PHONE_AGENT_ID': ''}), patch.object(phone, 'api') as api:
            with self.assertRaisesRegex(ValueError, 'setup'):
                phone.call(self.job, phone.fingerprint(self.job))
            api.assert_not_called()

    def test_foreign_agent_cannot_dial(self):
        other = {'conversation_config': {'agent': {'first_message': 'Hi!', 'prompt': {'prompt': 'no brief'}}}}
        with patch.object(phone, 'api', return_value=other) as api:
            with self.assertRaisesRegex(ValueError, 'setup agent'):
                phone.call(self.job, phone.fingerprint(self.job))
            self.assertEqual(api.call_count, 1)

    def test_uncertain_send_cannot_be_repeated(self):
        with patch.object(phone, 'api', side_effect=[AGENT_OK, RuntimeError('uncertain'), AGENT_OK]) as api:
            with self.assertRaises(RuntimeError):
                phone.call(self.job, phone.fingerprint(self.job))
            with self.assertRaises(FileExistsError):
                phone.call(self.job, phone.fingerprint(self.job))
            self.assertEqual(sum(c.args[0] == 'twilio/outbound-call' for c in api.call_args_list), 1)

    def test_send_uses_config_and_no_recording(self):
        with patch.object(phone, 'api', side_effect=[AGENT_OK, {'success': True, 'conversation_id': 'conv_1'}]) as api:
            phone.call(self.job, phone.fingerprint(self.job))
        payload = api.call_args.args[2]
        self.assertFalse(payload['call_recording_enabled'])
        self.assertEqual(payload['agent_id'], 'agent_test')
        self.assertEqual(payload['agent_phone_number_id'], 'phnum_test')
        self.assertEqual(payload['to_number'], '+4917212345678')
        variables = payload['conversation_initiation_client_data']['dynamic_variables']
        self.assertEqual(variables['caller_name'], 'Sam Example')
        self.assertEqual(json.loads(variables['godspeed_call_brief'])['time'], '19:00')

    def test_provider_success_is_not_reservation_success(self):
        with patch.object(phone, 'api', return_value={'status': 'done', 'analysis': {'call_successful': 'success'}, 'transcript': []}):
            self.assertEqual(phone.result('conv_123')['outcome'], 'needs_review')

    def test_bad_conversation_id_never_reaches_the_provider(self):
        with patch.object(phone, 'api') as api:
            with self.assertRaises(ValueError):
                phone.result('../agents')
            api.assert_not_called()


class ApiTests(unittest.TestCase):
    def test_missing_key_never_uses_network(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(phone.urllib.request, 'build_opener') as opener:
            with self.assertRaisesRegex(RuntimeError, 'ELEVENLABS_API_KEY'):
                phone.api('agents')
            opener.assert_not_called()

    def test_http_error_does_not_expose_body_or_key(self):
        error = phone.urllib.error.HTTPError('https://api.elevenlabs.io/', 401, 'secret-content', {}, None)
        opener = unittest.mock.MagicMock()
        opener.open.side_effect = error
        with patch.dict(os.environ, {'ELEVENLABS_API_KEY': 'private-key'}), patch.object(phone.urllib.request, 'build_opener', return_value=opener):
            with self.assertRaisesRegex(RuntimeError, 'HTTP 401') as caught:
                phone.api('agents')
        self.assertNotIn('secret-content', str(caught.exception))
        self.assertNotIn('private-key', str(caught.exception))

    def test_redirect_is_not_followed_with_credentials(self):
        self.assertIsNone(phone.NoRedirect().redirect_request(None, None, 302, '', {}, 'https://example.com'))

    def test_agent_config_is_english_and_carries_the_placeholders(self):
        config = phone.agent_config()['conversation_config']
        self.assertEqual(config['agent']['language'], 'en')
        self.assertEqual(config['agent']['first_message'], '')
        self.assertIn('{{godspeed_call_brief}}', config['agent']['prompt']['prompt'])
        self.assertIn('{{caller_name}}', config['agent']['prompt']['prompt'])
        self.assertIn('AI assistant', config['agent']['prompt']['prompt'])
        self.assertEqual(config['conversation']['max_duration_seconds'], 180)
        # ElevenLabs refuses an English agent on the v2.5 voice model (checked live 2026-09-16).
        self.assertEqual(config['tts']['model_id'], 'eleven_flash_v2')


if __name__ == '__main__':
    unittest.main()
