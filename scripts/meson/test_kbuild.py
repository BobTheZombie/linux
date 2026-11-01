#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Exercise the bridge without requiring a kernel toolchain or root."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).with_name('kbuild.py')


class BridgeTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='kernel bridge ')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'source'
        self.source.mkdir()
        self.out = self.root / 'out'
        self.log = self.root / 'calls'
        self.make = self.root / 'fake make'
        self.make.write_text('''#!/usr/bin/env python3
import json, os, pathlib, sys
with open(os.environ['TEST_LOG'], 'a') as f:
    f.write(json.dumps(sys.argv[1:]) + '\\n')
output = next(x[2:] for x in sys.argv if x.startswith('O='))
if sys.argv[-1] == 'defconfig':
    pathlib.Path(output, '.config').write_text('CONFIG_MODULES=y\\n')
sys.exit(int(os.environ.get('TEST_FAIL', '0')))
''')
        self.make.chmod(0o755)
        self.command = [sys.executable, str(SCRIPT), '--source', str(self.source),
                        '--output', str(self.out), '--arch', 'x86', '--make',
                        str(self.make), '--conf', str(self.root / 'conf'), '--jobs', '2']
        self.env = os.environ.copy()
        self.env['TEST_LOG'] = str(self.log)
        for key in ('INSTALL_PATH', 'INSTALL_MOD_PATH', 'INSTALL_HDR_PATH'):
            self.env.pop(key, None)

    def call(self, target, *options):
        return subprocess.run(self.command + list(options) + [target], env=self.env,
                              capture_output=True, text=True)

    def test_initialization_and_rebuild(self):
        self.assertEqual(self.call('build').returncode, 0)
        config = self.out / '.config'
        config.write_text('my existing configuration\n')
        self.assertEqual(self.call('modules').returncode, 0)
        self.assertEqual(config.read_text(), 'my existing configuration\n')
        import json
        calls = [json.loads(x) for x in self.log.read_text().splitlines()]
        self.assertEqual([x[-1] for x in calls],
                         ['defconfig', 'olddefconfig', 'all', 'modules'])
        self.assertIn('O=' + str(self.out), calls[0])

    def test_failed_build_has_no_stamp(self):
        self.out.mkdir()
        (self.out / '.config').write_text('CONFIG_MODULES=y\n')
        self.env['TEST_FAIL'] = '23'
        stamp = self.root / 'stamp'
        self.assertNotEqual(self.call('build', '--stamp', str(stamp)).returncode, 0)
        self.assertFalse(stamp.exists())

    def test_failed_initial_configuration_is_retryable(self):
        self.env['TEST_FAIL'] = '23'
        self.assertNotEqual(self.call('build').returncode, 0)
        self.assertFalse((self.out / '.config').exists())
        self.env.pop('TEST_FAIL')
        self.assertEqual(self.call('build').returncode, 0)

    def test_install_requires_staging(self):
        for target in ('install', 'modules_install', 'headers_install'):
            self.assertNotEqual(self.call(target).returncode, 0)
        self.assertFalse(self.log.exists())

    def test_staging_path_is_forwarded_as_make_argument(self):
        import json
        for target, variable in (('install', 'INSTALL_PATH'),
                                 ('modules_install', 'INSTALL_MOD_PATH'),
                                 ('headers_install', 'INSTALL_HDR_PATH')):
            self.env[variable] = str(self.root / 'stage')
            self.assertEqual(self.call(target).returncode, 0)
            last_call = json.loads(self.log.read_text().splitlines()[-1])
            self.assertIn(variable + '=' + str(self.root / 'stage'), last_call)

    def test_seed_configuration_is_preserved(self):
        seed = self.root / 'seed'
        seed.write_text('CONFIG_EXT4_FS=y\n')
        self.assertEqual(self.call('prepare', '--config', str(seed)).returncode, 0)
        self.assertEqual((self.out / '.config').read_text(), seed.read_text())
        self.assertNotIn('\"defconfig\"', self.log.read_text())

    def test_reject_non_x86_profile(self):
        self.assertNotEqual(self.call('build', '--arch', 'arm64', '--ryzen', 'zen2').returncode, 0)
        self.assertFalse(self.log.exists())


if __name__ == '__main__':
    unittest.main()
