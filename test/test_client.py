import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import _env
import client


class TransportTests(unittest.TestCase):
    def test_missing_socket_says_the_order_was_not_submitted(self):
        with patch.object(client, 'SOCKET_PATH', Path('/nonexistent/mc-phone.sock')):
            with self.assertRaisesRegex(client.PhoneTransportError, 'NOT submitted.*does not exist') as caught:
                client.rpc({'action': 'health'})
        self.assertIn('server only', str(caught.exception))

    def test_permission_refusal_names_the_group(self):
        with patch.object(client.SOCKET_PATH.__class__, 'exists', return_value=True), \
             patch.object(client, 'unix_socket', side_effect=PermissionError(13, 'denied')):
            with self.assertRaisesRegex(client.PhoneTransportError, 'mc-phone group'):
                client.rpc({'action': 'health'})

    def test_service_refusal_is_final_and_verbatim(self):
        with patch.object(client.SOCKET_PATH.__class__, 'exists', return_value=True), \
             patch.object(client, 'unix_socket', return_value=json.dumps({'error': 'That date has already passed.'})):
            with self.assertRaisesRegex(RuntimeError, '^That date has already passed.$'):
                client.rpc({'action': 'submit', 'body': {}})

    def test_non_json_answer_is_reported(self):
        with patch.object(client.SOCKET_PATH.__class__, 'exists', return_value=True), \
             patch.object(client, 'unix_socket', return_value='Traceback ...'):
            with self.assertRaisesRegex(client.PhoneTransportError, 'not JSON'):
                client.rpc({'action': 'health'})


class CommandTests(unittest.TestCase):
    def run_main(self, *argv):
        out = []
        with patch.object(sys, 'argv', ['mc-phone', *argv]), patch('builtins.print', side_effect=lambda s, **k: out.append(s)):
            code = client.main()
        return code, json.loads(out[-1])

    def test_submit_sends_the_order_its_fingerprint_and_the_words(self):
        job = _env.example_order()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'order.json'
            path.write_text(json.dumps(job))
            with patch.object(client, 'rpc', return_value={'job_id': job['job_id'], 'status': 'queued'}) as rpc:
                code, out = self.run_main('submit', str(path), '--authorization', 'Call them and book it.', '--source', 'hermes telegram')
        self.assertEqual(code, 0)
        self.assertEqual(out['status'], 'queued')
        request = rpc.call_args.args[0]
        self.assertEqual(request['action'], 'submit')
        self.assertEqual(request['body']['authorization'], 'Call them and book it.')
        self.assertEqual(request['body']['source'], 'hermes telegram')
        self.assertEqual(len(request['body']['approved_fingerprint']), 16)

    def test_prepare_without_a_file_is_a_clear_error(self):
        code, out = self.run_main('prepare')
        self.assertEqual(code, 1)
        self.assertIn('order file', out['error'])

    def test_wait_stops_when_finished(self):
        answers = [{'status': 'queued'}, {'status': 'finished', 'result': {}}]
        with patch.object(client, 'rpc', side_effect=answers), patch.object(client.time, 'sleep'):
            code, out = self.run_main('wait', 'job-1')
        self.assertEqual(out['status'], 'finished')

    def test_setup_refuses_non_root(self):
        with patch.object(client, 'is_root', return_value=False):
            code, out = self.run_main('setup', 'check')
        self.assertEqual(code, 1)
        self.assertIn('root', out['error'])


if __name__ == '__main__':
    unittest.main()
