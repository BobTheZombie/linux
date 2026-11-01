# SPDX-License-Identifier: GPL-2.0-only
project('linux', 'c', version: '7.3.0', meson_version: '>=0.63.0',
        default_options: ['c_std=gnu11', 'buildtype=release', 'warning_level=1'])

python = import('python').find_installation('python3')
make = find_program('make')
subdir('scripts/kconfig')

# Kbuild remains the kernel dependency engine during the migration. Its output
# lives below the Meson build directory, never in the source tree.
bridge = files('scripts/meson/kbuild.py')
bridge_args = [
  '--source', meson.project_source_root(),
  '--output', meson.project_build_root() / 'kernel',
  '--make', make.full_path(),
  '--arch', get_option('kernel_arch'),
  '--cross-compile', get_option('cross_compile'),
  '--llvm', get_option('llvm'),
  '--jobs', get_option('jobs').to_string(),
  '--config', get_option('config'),
  '--defconfig', get_option('defconfig'),
  '--ryzen', get_option('ryzen'),
  '--conf', kconfig_conf.full_path(),
]
bridge_deps = [kconfig_conf]
if kconfig_mconf.found()
  bridge_args += ['--mconf', kconfig_mconf.full_path()]
  bridge_deps += [kconfig_mconf]
endif
custom_target('kernel', output: 'kernel-build.stamp',
  command: [python, bridge, bridge_args, '--stamp', '@OUTPUT@', 'build'],
  depends: bridge_deps, build_by_default: true, build_always_stale: true,
  console: true)
foreach target : ['modules', 'olddefconfig', 'menuconfig', 'nconfig', 'xconfig',
                  'gconfig', 'savedefconfig', 'prepare', 'modules_prepare',
                  'headers_install', 'modules_install', 'install', 'clean']
  target_name = target
  if target in ['install', 'clean']
    target_name = 'kernel-' + target
  endif
  run_target(target_name, command: [python, bridge, bridge_args, target],
             depends: bridge_deps)
endforeach
run_target('kbuild', command: [python, bridge, bridge_args, 'environment'],
           depends: bridge_deps)
test('kbuild-bridge', python, args: files('scripts/meson/test_kbuild.py'))
summary({'kernel output': meson.project_build_root() / 'kernel',
         'kernel backend': 'Kbuild (GNU Make); native Ninja migration incomplete',
         'native Ninja tools': 'conf / optional mconf',
         'Ryzen profile': get_option('ryzen')}, section: 'Build status')
