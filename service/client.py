"""mc-phone: the one command the assistant uses. It talks to the service over its socket.

  mc-phone health                     is the service up, configured, and how many calls today
  mc-phone prepare <order.json>       validate an order without calling
  mc-phone submit  <order.json> --authorization "<the person's words>" --source "<assistant, chat>"
  mc-phone wait    <job_id>           poll until finished (55 seconds at most per run)
  mc-phone result  <job_id>           the outcome and the transcript
  mc-phone list                       the last twenty jobs
  mc-phone setup   agent|numbers|check   root only; see setup.py

This runs on the server only. There is no laptop mode: whichever assistant places an order
(Hermes through Telegram, or the desktop app connected to the server's gateway) runs here.
"""
import argparse
import json
import os
from pathlib import Path
import socket
import sys
import time

SOCKET_PATH = Path('/run/mc-phone-rpc.sock')
CONFIG_DIR = Path('/etc/mc-phone')


class PhoneTransportError(RuntimeError):
    """The service was not reached. The message says what was tried and why it failed."""


def unix_socket(request):
    parts = []
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
        s.settimeout(25)
        s.connect(str(SOCKET_PATH))
        s.sendall(json.dumps(request).encode('utf-8'))
        s.shutdown(socket.SHUT_WR)  # the service reads to EOF; without this both sides wait for ever
        while True:
            chunk = s.recv(65536)
            if not chunk:
                break
            parts.append(chunk)
    return b''.join(parts).decode('utf-8')


def rpc(request):
    if not SOCKET_PATH.exists():
        raise PhoneTransportError(
            'The order was NOT submitted: %s does not exist on this machine. mc-phone runs on the '
            'server only; if this is the server, the socket unit is down: systemctl status mc-phone-rpc.socket'
            % SOCKET_PATH)
    try:
        raw = unix_socket(request)
    except PermissionError:
        raise PhoneTransportError(
            'The order was NOT submitted: this account may not open %s. Only members of the mc-phone '
            'group may; add one with: usermod -aG mc-phone <account>, then restart the service that '
            'runs the assistant so it picks up the group.' % SOCKET_PATH) from None
    except OSError as exc:
        raise PhoneTransportError('The order was NOT submitted: the socket answered "%s". Check: systemctl '
                                  'status mc-phone-rpc.socket mc-phone' % exc) from None
    try:
        out = json.loads(raw)
    except ValueError:
        raise PhoneTransportError('The order was NOT submitted: the service answered with something that is '
                                  'not JSON: %.200r' % raw) from None
    if out.get('error'):
        raise RuntimeError(out['error'])  # the service refused; that is the answer
    return out


def load_env(path):
    if not path.exists():
        return
    for line in path.read_text(encoding='utf-8').splitlines():
        if '=' in line and not line.startswith('#'):
            k, v = line.split('=', 1)
            v = v.strip()
            if len(v) >= 2 and v[0] == v[-1] and v[0] in '"\'':
                v = v[1:-1]
            os.environ.setdefault(k.strip(), v)


def is_root():
    return getattr(os, 'geteuid', lambda: -1)() == 0


def run_setup(args):
    if not is_root():
        print(json.dumps({'error': 'mc-phone setup runs as root; it needs the key in /etc/mc-phone.'}))
        return 1
    load_env(CONFIG_DIR / 'config.env')
    load_env(CONFIG_DIR / 'credentials.env')
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import setup
    return setup.main(args)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('command', choices=['health', 'prepare', 'submit', 'result', 'wait', 'list', 'setup'])
    p.add_argument('target', nargs='?')
    p.add_argument('--authorization', default='')
    p.add_argument('--source', default='godspeed')
    p.add_argument('--seconds', type=int, default=45)
    p.add_argument('--write', action='store_true', help='setup agent: also record the agent id in config.env')
    a = p.parse_args()
    if a.command == 'setup':
        return run_setup([x for x in (a.target, '--write' if a.write else None) if x])
    try:
        if a.command in ('prepare', 'submit'):
            if not a.target:
                raise ValueError('Give the order file: mc-phone %s <order.json>' % a.command)
            job = json.loads(Path(a.target).read_text(encoding='utf-8'))
            # The fingerprint is computed here, from the file as it is, and the service recomputes
            # it from what arrived. They match only if nothing changed on the way.
            sys.path.insert(0, str(Path(__file__).resolve().parent))
            from call import fingerprint
            body = {'job': job, 'approved_fingerprint': fingerprint(job), 'authorization': a.authorization,
                    'source': a.source}
            out = rpc({'action': a.command, 'body': body})
        elif a.command in ('result', 'wait'):
            if not a.target:
                raise ValueError('Give the job id: mc-phone %s <job_id>' % a.command)
            end = time.monotonic() + min(55, max(0, a.seconds)) if a.command == 'wait' else 0
            while True:
                out = rpc({'action': 'result', 'job_id': a.target})
                if out['status'] == 'finished' or time.monotonic() >= end:
                    break
                time.sleep(3)
        else:
            out = rpc({'action': a.command})
        print(json.dumps(out, ensure_ascii=True, indent=2))
    except (ValueError, RuntimeError, TypeError, OSError) as exc:
        print(json.dumps({'error': str(exc)}))
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
