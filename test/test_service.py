import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

import _env
import call
import service


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.patcher = patch.object(service, 'BASE', self.base)
        self.patcher.start()
        self.job = _env.example_order()
        self.body = {'job': self.job, 'approved_fingerprint': call.fingerprint(self.job),
                     'authorization': 'Please make a test call to me.', 'source': 'test'}

    def tearDown(self):
        self.patcher.stop()
        self.tmp.cleanup()

    def submit(self):
        return service.rpc({'action': 'submit', 'body': self.body})

    def test_health_reports_configuration_and_count(self):
        out = service.rpc({'action': 'health'})
        self.assertTrue(out['configured'])
        self.assertEqual(out['calls_today'], 0)
        self.assertEqual(out['daily_limit'], 5)
        self.assertFalse(out['worker_recent'])

    def test_prepare_validates_without_queueing_and_without_the_words(self):
        # Found by Hermes on 2026-09-16: prepare must not demand what only submit needs.
        self.body['authorization'] = ''
        self.body['source'] = ''
        out = service.rpc({'action': 'prepare', 'body': self.body})
        self.assertFalse(out['call_started'])
        self.assertEqual(service.rpc({'action': 'list'})['jobs'], [])

    def test_prepare_still_refuses_a_bad_order(self):
        self.body['job']['to_number'] = '+49112'
        self.body['approved_fingerprint'] = call.fingerprint(self.body['job'])
        with self.assertRaisesRegex(ValueError, 'emergency'):
            service.rpc({'action': 'prepare', 'body': self.body})

    def test_authorization_is_required(self):
        self.body['authorization'] = ''
        with self.assertRaises(ValueError):
            self.submit()

    def test_source_is_required(self):
        self.body['source'] = ''
        with self.assertRaises(ValueError):
            self.submit()

    def test_general_live_call_needs_no_reservation_fields(self):
        self.job.update(mode='live', to_number='+4930123456', contact='Bike workshop',
                        goal='Ask whether the bike is ready to collect.')
        for field in ('date', 'time', 'party_size'):
            self.job.pop(field, None)
        self.body['approved_fingerprint'] = call.fingerprint(self.job)
        with patch.object(service.phone, 'call', return_value={'conversation_id': 'conv_test'}) as dial:
            self.assertEqual(self.submit()['status'], 'queued')
            service.tick()
            self.assertEqual(dial.call_args.args[0]['goal'], self.job['goal'])

    def test_duplicate_submit_is_idempotent(self):
        self.submit()
        self.assertTrue(self.submit()['duplicate_avoided'])
        self.assertEqual(len(service.rpc({'action': 'list'})['jobs']), 1)

    def test_reused_id_for_a_different_order_is_refused(self):
        self.submit()
        self.job['time'] = '18:00'
        self.body['approved_fingerprint'] = call.fingerprint(self.job)
        with self.assertRaisesRegex(ValueError, 'different order'):
            self.submit()

    def test_mutated_approved_job_is_rejected(self):
        self.body['job']['time'] = '18:00'
        with self.assertRaises(ValueError):
            self.submit()

    def test_uncertain_send_never_redials(self):
        self.submit()
        with patch.object(service.phone, 'call', side_effect=RuntimeError('uncertain')) as dial:
            service.tick()
            service.tick()
            self.assertEqual(dial.call_count, 1)
        self.assertEqual(service.rpc({'action': 'result', 'job_id': self.job['job_id']})['result']['outcome'], 'uncertain')

    def test_crash_recovery_does_not_redial(self):
        self.submit()
        with service.database() as db:
            db.execute("UPDATE jobs SET status='sending'")
        with patch.object(service.phone, 'call') as dial:
            service.tick()
            dial.assert_not_called()

    def test_completion_needs_semantic_review_and_carries_the_transcript(self):
        self.submit()
        with patch.object(service.phone, 'call', return_value={'conversation_id': 'conv_test'}):
            service.tick()
        with patch.object(service.phone, 'result', return_value={'status': 'done', 'transcript': [{'role': 'user', 'message': 'Sorry, fully booked.'}]}):
            service.tick()
        result = service.rpc({'action': 'result', 'job_id': self.job['job_id']})['result']
        self.assertEqual(result['outcome'], 'needs_review')
        self.assertIn('fully booked', result['transcript'][0]['message'])
        self.assertIn('not a confirmation', result['review_instruction'])
        self.assertNotIn('transcript_url', result)

    def test_one_call_at_a_time(self):
        self.submit()
        second = dict(self.job, job_id='second-order')
        self.body = dict(self.body, job=second, approved_fingerprint=call.fingerprint(second))
        self.submit()
        with patch.object(service.phone, 'call', return_value={'conversation_id': 'conv_a'}) as dial, \
             patch.object(service.phone, 'result', return_value={'status': 'in-progress', 'transcript': []}):
            service.tick()
            service.tick()
            self.assertEqual(dial.call_count, 1)

    def test_daily_limit_refuses_the_next_order(self):
        with patch.dict(os.environ, {'GODSPEED_PHONE_DAILY_LIMIT': '1'}):
            self.submit()
            with patch.object(service.phone, 'call', return_value={'conversation_id': 'conv_a'}):
                service.tick()
            second = dict(self.job, job_id='second-order')
            self.body = dict(self.body, job=second, approved_fingerprint=call.fingerprint(second))
            with self.assertRaisesRegex(ValueError, 'daily limit'):
                self.submit()
            self.assertEqual(service.rpc({'action': 'health'})['calls_today'], 1)

    def test_unknown_action_and_unknown_job(self):
        with self.assertRaises(ValueError):
            service.rpc({'action': 'dial'})
        with self.assertRaises(ValueError):
            service.rpc({'action': 'result', 'job_id': 'nope'})


if __name__ == '__main__':
    unittest.main()
