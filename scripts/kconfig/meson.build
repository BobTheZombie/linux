# SPDX-License-Identifier: GPL-2.0-only
bison = find_program('bison', native: true)
flex = find_program('flex', native: true)
parser = custom_target('kconfig-parser', input: 'parser.y',
  output: ['parser.tab.c', 'parser.tab.h'],
  command: [bison, '-o', '@OUTPUT0@', '--defines=@OUTPUT1@', '-t', '-l', '@INPUT@'])
lexer = custom_target('kconfig-lexer', input: 'lexer.l', output: 'lexer.lex.c',
  command: [flex, '-o@OUTPUT@', '-L', '@INPUT@'])
kconfig_inc = include_directories('.', '../include')
kconfig_common = static_library('kconfig-common',
  ['confdata.c', 'expr.c', 'menu.c', 'preprocess.c', 'symbol.c', 'util.c', parser, lexer],
  native: true, include_directories: kconfig_inc)
kconfig_conf = executable('conf', 'conf.c', native: true,
  include_directories: kconfig_inc, link_with: kconfig_common)
ncurses = dependency('ncursesw', native: true, required: get_option('kconfig_ui'))
kconfig_mconf = disabler()
if ncurses.found()
  kconfig_mconf = executable('mconf',
    ['mconf.c', 'mnconf-common.c', 'lxdialog/checklist.c', 'lxdialog/inputbox.c',
     'lxdialog/menubox.c', 'lxdialog/textbox.c', 'lxdialog/util.c', 'lxdialog/yesno.c'],
    native: true, include_directories: kconfig_inc, dependencies: ncurses,
    link_with: kconfig_common)
endif
