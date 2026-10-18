"""The installer's choices of mission control folder, assistant's account and code, read without
installing anything (MC_PHONE_INSTALLER_FUNCTIONS_ONLY=1 stops it right after it has chosen).

The machine's real accounts must not decide these tests, so `id` and `getent` answer from a small
passwd file of the test's own, and `stat` can be told who owns a folder. Linux only, as the add-on is.
"""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

import _env  # noqa: F401  (the shared scaffolding, as in every test here)

ROOT = Path(__file__).resolve().parent.parent
INSTALLER = ROOT / 'install.sh'
LINUX = sys.platform.startswith('linux') and shutil.which('bash') is not None

# Each stand-in answers from the test's own world when told to, and is the real tool otherwise.
STAND_INS = {
    'id': '''#!/bin/sh
if [ -n "$FAKE_PASSWD" ] && [ $# -eq 1 ] && [ "${1#-}" = "$1" ]; then
  grep -q "^$1:" "$FAKE_PASSWD"; exit $?
fi
exec %(id)s "$@"
''',
    'getent': '''#!/bin/sh
if [ -n "$FAKE_PASSWD" ] && [ "$1" = passwd ] && [ $# -eq 2 ]; then
  grep "^$2:" "$FAKE_PASSWD" || exit 2; exit 0
fi
exec %(getent)s "$@"
''',
    'stat': '''#!/bin/sh
if [ -n "$FAKE_OWNER" ] && [ "$1" = -c ] && [ "$2" = %%U ]; then printf '%%s\\n' "$FAKE_OWNER"; exit 0; fi
exec %(stat)s "$@"
''',
}


def physical(path):
    return os.path.realpath(str(path))


@unittest.skipUnless(LINUX, 'mc-phone installs on Linux only')
class InstallerChoiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='mc-phone-install-'))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.bin = self.tmp / 'bin'
        self.bin.mkdir()
        real = {name: shutil.which(name) for name in STAND_INS}
        for name, text in STAND_INS.items():
            path = self.bin / name
            path.write_text(text % real, encoding='utf-8')
            path.chmod(0o755)
        self.passwd = self.tmp / 'passwd'
        self.passwd.write_text('', encoding='utf-8')

    def account(self, name, home):
        with self.passwd.open('a', encoding='utf-8') as f:
            f.write('%s:x:1000:1000::%s:/bin/bash\n' % (name, home))

    def mission_control(self, folder):
        folder.mkdir(parents=True, exist_ok=True)
        (folder / 'AGENTS.md').write_text('# mine\n', encoding='utf-8')
        return folder

    def copy_at(self, folder):
        """This add-on's installer and service, put where a test wants a copy of it."""
        (folder / 'service').mkdir(parents=True, exist_ok=True)
        shutil.copyfile(INSTALLER, folder / 'install.sh')
        shutil.copyfile(ROOT / 'service' / 'service.py', folder / 'service' / 'service.py')
        return folder / 'install.sh'

    def bundled_copy(self, mission_control):
        here = mission_control / '.godspeed' / 'integrated-runtime' / 'versions' / '0123456789abcdef' / 'third-party' / 'addons' / 'mc-phone'
        return self.copy_at(here), here

    def choose(self, script, owner=None, fake_accounts=True, **given):
        env = {k: v for k, v in os.environ.items()
               if k not in ('GODSPEED', 'AI_USER', 'HP_SRC', 'SUDO_USER', 'MC_PHONE_INSTALLER_FUNCTIONS_ONLY')}
        env['PATH'] = '%s:%s' % (self.bin, env.get('PATH', '/usr/bin:/bin'))
        if fake_accounts:
            env['FAKE_PASSWD'] = str(self.passwd)
        if owner:
            env['FAKE_OWNER'] = owner
        env.update(given)
        run = subprocess.run(
            ['bash', '-c', 'MC_PHONE_INSTALLER_FUNCTIONS_ONLY=1; . "$0"; printf "%s\\n%s\\n%s\\n" "$GODSPEED" "$AI_USER" "$HP_SRC"', str(script)],
            env=env, capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        godspeed, user, source = run.stdout.split('\n')[:3]
        return godspeed, user, source

    def test_the_copy_that_comes_with_the_linux_installer_finds_its_mission_control_its_owner_and_its_own_code(self):
        root = self.mission_control(self.tmp / 'home' / 'godspeed v2')
        script, here = self.bundled_copy(root)
        godspeed, user, source = self.choose(script, owner='sam')
        self.assertEqual(physical(godspeed), physical(root))
        self.assertEqual(user, 'sam', 'the account that owns the folder')
        self.assertEqual(physical(source), physical(here), 'the code beside it, not a download')

    def test_the_owner_is_read_from_the_folder_itself(self):
        root = self.mission_control(self.tmp / 'home' / 'godspeed-v2')
        script, _ = self.bundled_copy(root)
        _, user, _ = self.choose(script, fake_accounts=False)
        self.assertEqual(user, subprocess.run(['id', '-un'], capture_output=True, text=True).stdout.strip())

    def test_where_the_linux_installer_ran_as_root_root_is_the_assistants_account(self):
        # A server rented with only a root login: the Linux installer, its notebook and its
        # assistant all run as root. Root wins over the previous edition's account ai.
        self.account('ai', self.tmp / 'home-ai')
        root = self.mission_control(self.tmp / 'root' / 'godspeed-v2')
        script, _ = self.bundled_copy(root)
        _, user, _ = self.choose(script, owner='root')
        self.assertEqual(user, 'root')

    def test_a_folder_root_owns_that_this_copy_did_not_come_with_is_not_the_assistants(self):
        other = self.mission_control(self.tmp / 'srv' / 'godspeed')
        script = self.copy_at(self.tmp / 'clone')
        self.account('ai', self.tmp / 'home-ai')
        _, user, _ = self.choose(script, owner='root', GODSPEED=str(other))
        self.assertEqual(user, 'ai', 'the previous edition\'s server: the assistant is ai')
        self.passwd.write_text('', encoding='utf-8')
        _, user, _ = self.choose(script, owner='root', GODSPEED=str(other), SUDO_USER='sam')
        self.assertEqual(user, 'sam', 'else the account that started sudo')
        _, user, _ = self.choose(script, owner='root', GODSPEED=str(other), SUDO_USER='root')
        self.assertEqual(user, '', 'never root by way of sudo')

    def test_what_godspeed_and_ai_user_say_wins(self):
        root = self.mission_control(self.tmp / 'home' / 'godspeed-v2')
        script, _ = self.bundled_copy(root)
        godspeed, user, _ = self.choose(script, owner='sam', GODSPEED='/srv/other', AI_USER='someone')
        self.assertEqual((godspeed, user), ('/srv/other', 'someone'))

    def test_the_previous_editions_server_finds_the_ai_accounts_folder(self):
        home = self.tmp / 'home-ai'
        self.account('ai', home)
        self.mission_control(home / 'godspeed')
        script = self.copy_at(self.tmp / 'clone')
        godspeed, user, _ = self.choose(script)
        self.assertEqual((godspeed, user), (str(home / 'godspeed'), 'ai'))

    def test_a_folder_the_kit_recorded_wins_then_this_editions_then_the_previous_ones(self):
        home = self.tmp / 'home-sam'
        self.account('sam', home)
        self.mission_control(home / 'godspeed')
        script = self.copy_at(self.tmp / 'clone')
        self.mission_control(home / 'godspeed-v2')
        godspeed, _, _ = self.choose(script, SUDO_USER='sam')
        self.assertEqual(godspeed, str(home / 'godspeed-v2'))
        recorded = self.mission_control(self.tmp / 'elsewhere' / 'mine')
        (home / '.godspeed').mkdir()
        (home / '.godspeed' / 'device.env').write_text('GODSPEED_DIR="%s"\n' % recorded, encoding='utf-8')
        godspeed, user, _ = self.choose(script, SUDO_USER='sam')
        self.assertEqual((godspeed, user), (str(recorded), 'sam'))

    def test_a_copy_outside_any_mission_control_with_nobody_to_ask_settles_on_nothing(self):
        script = self.copy_at(self.tmp / 'loose')
        godspeed, user, source = self.choose(script)
        self.assertEqual((godspeed, user), ('', ''), 'so the installer stops before installing anything')
        self.assertEqual(physical(source), physical(self.tmp / 'loose'))


class InstallerTextTests(unittest.TestCase):
    """What the installer does once it has chosen, read from its text, on any machine."""

    @classmethod
    def setUpClass(cls):
        cls.script = INSTALLER.read_text(encoding='utf-8')

    def test_it_stops_before_installing_anything_when_it_found_no_folder(self):
        first = self.script.index('install -d -m 755 /opt/mc-phone')
        stop = self.script.index('Found no mission control folder')
        self.assertLess(stop, first)
        self.assertLess(self.script.index('the one-line server'), first, 'the container is named before anything is installed')
        self.assertLess(self.script.index('Could not tell which account your assistant runs as'), first)

    def test_it_says_plainly_where_it_cannot_run(self):
        self.assertIn('mc-phone needs Linux with systemd: a Linux computer or server. It cannot run on this machine, nor on a Mac or Windows.', self.script)

    def test_the_assistants_account_owns_the_order_socket_so_it_needs_no_restart(self):
        self.assertIn("printf '[Socket]\\nSocketUser=%s\\n' \"$AI_USER\" > /etc/systemd/system/mc-phone-rpc.socket.d/assistant.conf", self.script)
        self.assertIn('systemctl restart mc-phone-rpc.socket', self.script, 'restarted, so a changed owner takes effect')
        self.assertNotIn('AI_USER="${AI_USER:-ai}"', self.script, 'no longer assumes the account ai')

    def test_the_selftest_switch_comes_before_anything_is_downloaded(self):
        self.assertLess(self.script.index('MC_PHONE_INSTALLER_FUNCTIONS_ONLY'), self.script.index('curl -fsSL "$LIB_URL"'))


class RecipeTests(unittest.TestCase):
    """The recipe asks the machine first and prepares the call where none can go out."""

    @classmethod
    def setUpClass(cls):
        cls.text = (ROOT / 'skill' / 'phone-errands' / 'SKILL.md').read_text(encoding='utf-8').replace('\r', '')

    def test_it_checks_before_it_builds_an_order(self):
        self.assertLess(self.text.index('Run `mc-phone health` before anything else'), self.text.index('## Build the order'))

    def test_where_no_call_can_go_out_it_says_so_and_prepares_the_call(self):
        self.assertIn('not on Windows, not on a Mac, and not on the one-line server', self.text)
        self.assertIn('## Prepare the call instead', self.text)
        self.assertIn('Do not look for another way to dial.', self.text)
        self.assertIn('Never say or suggest that a call took place.', self.text)
        self.assertNotIn("server's mc-phone service", self.text, 'it no longer assumes a server')


if __name__ == '__main__':
    unittest.main()
