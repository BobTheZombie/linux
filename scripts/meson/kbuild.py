#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Meson entry point for Kbuild; does not replace the kernel dependency graph."""

import argparse
import fcntl
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys


def arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('source', 'output', 'make', 'arch', 'conf'):
        parser.add_argument('--' + name, required=True)
    for name in ('cross-compile', 'llvm', 'config', 'mconf'):
        parser.add_argument('--' + name, default='')
    parser.add_argument('--defconfig', default='defconfig')
    parser.add_argument('--jobs', type=int, default=0)
    parser.add_argument('--ryzen', choices=('none', 'zen', 'zen2', 'zen3', 'zen4', 'zen5'),
                        default='none')
    parser.add_argument('--stamp')
    parser.add_argument('target', choices=(
        'build', 'modules', 'olddefconfig', 'menuconfig', 'nconfig', 'xconfig',
        'gconfig', 'savedefconfig', 'prepare', 'modules_prepare', 'headers_install',
        'modules_install', 'install', 'clean', 'environment'))
    args = parser.parse_args()
    if args.jobs < 0:
        parser.error('--jobs must be nonnegative')
    if not args.arch or '/' in args.arch:
        parser.error('--arch must be a Kbuild architecture name')
    if args.defconfig != 'defconfig' and (
            not args.defconfig.endswith('_defconfig') or '/' in args.defconfig):
        parser.error('--defconfig must be defconfig or an architecture *_defconfig')
    if args.ryzen != 'none' and args.arch not in ('x86', 'x86_64'):
        parser.error('Ryzen profiles require x86 or x86_64')
    return args


def make_command(args):
    command = [args.make, '-C', str(Path(args.source).resolve()),
               'O=' + str(Path(args.output).resolve()), 'ARCH=' + args.arch,
               '-j' + str(args.jobs or len(os.sched_getaffinity(0))),
               'KCONFIG_CONF=' + str(Path(args.conf).resolve())]
    if args.mconf:
        command.append('KCONFIG_MCONF=' + str(Path(args.mconf).resolve()))
    if args.cross_compile:
        command.append('CROSS_COMPILE=' + args.cross_compile)
    if args.llvm:
        command.append('LLVM=' + args.llvm)
    return command


def run(command, env):
    print('+ ' + shlex.join(command), flush=True)
    subprocess.run(command, env=env, check=True)


def initialize_config(args, output, command, env):
    config = output / '.config'
    if args.config:
        seed = Path(args.config)
        if not seed.is_absolute():
            seed = Path(args.source) / seed
        shutil.copyfile(seed, config)
    else:
        run(command + [args.defconfig], env)
    if args.ryzen != 'none':
        # Explicit generation selection; never use -march=native on a build host.
        tune = output / '.meson-ryzen.config'
        symbol = 'CONFIG_X86_TUNE_' + args.ryzen.upper()
        tune.write_text('# CONFIG_X86_NATIVE_CPU is not set\n' + symbol + '=y\n')
        run(['sh', str(Path(args.source) / 'scripts/kconfig/merge_config.sh'),
             '-m', '-O', str(output), str(config),
             str(Path(args.source) / 'kernel/configs/lpm-ryzen.config'), str(tune)], env)
    run(command + ['olddefconfig'], env)
    if args.ryzen != 'none':
        expected = 'CONFIG_X86_TUNE_' + args.ryzen.upper() + '=y'
        if expected not in config.read_text().splitlines():
            raise RuntimeError('requested Zen tuning unavailable: check compiler and X86_64')


def initialize(args, output, command, env):
    config = output / '.config'
    if config.exists():
        return
    try:
        initialize_config(args, output, command, env)
    except (OSError, RuntimeError, subprocess.CalledProcessError):
        # A failed initial profile must not become a successful generic build
        # merely because the next invocation sees its partially written config.
        config.unlink(missing_ok=True)
        raise


def main():
    args = arguments()
    args.source = str(Path(args.source).resolve())
    output = Path(args.output).resolve()
    if output == Path(args.source):
        raise RuntimeError('kernel output must differ from the source directory')
    output.mkdir(parents=True, exist_ok=True)
    # One kernel output tree must never have concurrent configuration, clean,
    # build, or installation commands, even from separate Ninja invocations.
    with (output / '.meson-lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        env = os.environ.copy()
        for key in ('MAKEFLAGS', 'MFLAGS', 'MAKELEVEL', 'KBUILD_OUTPUT',
                    'KBUILD_EXTMOD', 'KBUILD_EXTMOD_OUTPUT', 'KCONFIG_CONFIG'):
            env.pop(key, None)
        command = make_command(args)
        if args.target == 'environment':
            print(shlex.join(command))
            return
        if args.target == 'clean':
            if (output / 'Makefile').exists():
                run(command + ['clean'], env)
            return
        # Installation is explicit and must be staged. Never write /boot or
        # /lib/modules on the developer's host through an accidental target.
        required = {'install': 'INSTALL_PATH', 'modules_install': 'INSTALL_MOD_PATH',
                    'headers_install': 'INSTALL_HDR_PATH'}.get(args.target)
        if required and not env.get(required):
            raise RuntimeError('set ' + required + ' to an absolute staging directory')
        if required and (not Path(env[required]).is_absolute() or
                         Path(env[required]).resolve() == Path('/')):
            raise RuntimeError(required + ' must name an absolute staging directory other than /')
        if required:
            # INSTALL_HDR_PATH is assigned by Kbuild, so the environment alone
            # cannot override it. Forward all staging paths as Make arguments.
            command.append(required + '=' + env[required])
        initialize(args, output, command, env)
        targets = ['all'] if args.target == 'build' else [args.target]
        run(command + targets, env)
        if args.stamp:
            Path(args.stamp).write_text('Kbuild completed successfully\n')


if __name__ == '__main__':
    try:
        main()
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        print('kernel build: ' + str(error), file=sys.stderr)
        sys.exit(1)
