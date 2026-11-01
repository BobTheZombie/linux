.. SPDX-License-Identifier: GPL-2.0-only

Meson/Ninja frontend and Ryzen tuning
====================================

Implementation status
---------------------

This is an incremental migration, not a native replacement for Kbuild.
Meson/Ninja builds the host ``conf`` and optional ``mconf`` executables directly,
including Flex/Bison generation. Kernel images, modules, other configuration
UIs, generated headers, modpost, objtool, signing, and installation still use
Kbuild through GNU Make. GNU Make remains a required dependency. No claim is
made that the kernel compilation graph has been converted to Ninja.

The bridge always enters Kbuild on each Ninja invocation. Kbuild then makes
its own incremental decisions, including tracking changed compiler flags and
new source files. A success stamp is never used to skip this dependency check.
Operations on a shared kernel output directory are serialized with flock.

Build
-----

Install the normal kernel build dependencies, Meson >= 0.63, Ninja, Python 3,
Flex, Bison, and optionally ncurses development headers. For a Zen 2 machine::

  meson setup build -Dryzen=zen2
  ninja -C build
  ninja -C build menuconfig
  ninja -C build modules

The kernel output is ``build/kernel``; the x86 boot image is
``build/kernel/arch/x86/boot/bzImage``. Normal ``make`` builds continue to work.
Meson ``buildtype`` and its CFLAGS affect the host tools only; kernel flags
are owned by Kbuild. Use normal Kbuild variables such as ``KCFLAGS`` for kernel
experiments. The Ryzen selection is explicit and does not inspect the host CPU.

Available generation names: ``zen``, ``zen2``, ``zen3``, ``zen4``, ``zen5``.
``none`` (default) keeps the architecture defconfig. A profile is a starting
point, not a replacement for checking required hardware drivers. For an existing
LPM configuration::

  meson setup build -Dconfig=/absolute/path/to/kernel.config -Dryzen=zen2

The seed configuration and profile are applied only when ``build/kernel/.config``
does not exist. Existing configurations are preserved. To change profiles, use
a new build directory or edit the configuration with menuconfig. When selecting
Zen tuning manually, clear ``CONFIG_X86_NATIVE_CPU`` first.

``-Dkernel_arch``, ``-Dcross_compile``, and ``-Dllvm`` map to Kbuild's ``ARCH``,
``CROSS_COMPILE``, and ``LLVM``. ``-Djobs=0`` uses the process CPU affinity count;
set an explicit smaller count on memory-constrained builders. The host Kconfig
tools always use a native host compiler, including with a Meson cross file.

Additional targets include olddefconfig, nconfig, xconfig, gconfig,
savedefconfig, prepare, modules_prepare, headers_install, modules_install,
kernel-install, and kernel-clean. The ``kbuild`` target prints an equivalent Make command for
other targets, such as building an external module with ``M=/path/to/module``.

Installation requires an explicit staging path. For example::

  INSTALL_MOD_PATH="$PWD/stage" ninja -C build modules_install
  INSTALL_HDR_PATH="$PWD/stage/usr" ninja -C build headers_install
  INSTALL_PATH="$PWD/stage/boot" ninja -C build kernel-install

These targets do not generate or install an initramfs or update a bootloader.
The normal Kbuild install hooks still run. Review staged output before packaging.

Ryzen changes
-------------

The x86-64 compiler tuning choice selects ``-mtune=znver1`` through
``-mtune=znver5`` when supported by the selected C compiler. The ISA baseline
remains ``-march=x86-64``; Rust retains the generic target and tuning. The
kernel's no-FPU, no-SIMD, no-red-zone, mitigation, and runtime alternatives rules
are unchanged. No globally enabled AVX/AVX2 instructions are introduced.

The optional profile enables SMP/SMT scheduling, dynamic preemption, 1000 Hz
ticks, amd-pstate active mode, ACPI CPU-frequency fallback, AMD IOMMU,
microcode support, NVMe/AHCI, and ext4. These choices have latency, throughput,
and power tradeoffs; they are not a measured speedup across all workloads.
Firmware support is still required for amd-pstate. Compiler scheduling tuning
alone does not establish a performance improvement.

ext4 changes
------------

The allocator's set/clear range helpers retain their existing word path for
ranges below 256 bits. Longer ranges retain per-bit updates at partial-byte
edges and use the architecture's existing memset implementation for whole bytes.
This removes the explicit 32-bit loop for large ranges and reuses the existing
x86 assembly and CPU alternatives rather than adding a filesystem-specific
SIMD implementation. The change affects both rotational and nonrotational
storage; it is not a new SSD disk format or a change in allocation policy.

Journal semantics, checksums, barriers, flush/FUA handling, metadata format,
allocation locks, and feature compatibility checks are unchanged. Ext4's
existing nonrotational allocation heuristics remain in place. This does not
prove freedom from data loss. Treat the branch as experimental until testing
below is completed on disposable filesystems.

Validation and remaining work
-----------------------------

``meson test -C build --print-errorlogs`` exercises bridge initialization,
configuration preservation, command argument handling, failure propagation,
and staging requirements. The ext4 mballoc KUnit suite includes a range test
that checks every bit and guard byte for partial ranges and unaligned buddy
bitmap addresses. ``scripts/meson/check_bitmap.py`` builds the actual extracted
range helpers with sanitizers, compares them against a bitwise oracle, and
benchmarks them against the base revision's implementation.

Required before deployment: boot tests on the supported Ryzen generations;
whole-kernel GCC and Clang builds; built-in and modular ext4; ext4 KUnit and
xfstests (including bigalloc, 1K/4K blocks, quota, encryption, verity, mmap,
direct I/O, fallocate, truncate, discard, and ENOSPC); crash/recovery and
fault-injection tests; cross-kernel mount/fsck compatibility; and end-to-end
fio/fs_mark workloads on actual SSD/NVMe hardware. Helper microbenchmarks do
not establish filesystem throughput or crash consistency.

A complete native Ninja kernel backend still needs configuration-aware
translation of all Kbuild rules, generated headers, architecture boot stages,
composite objects, modversions, BTF, objtool, LTO, Rust, signing, external
modules, installation, and parity testing. This frontend deliberately retains
those existing rules until each replacement is verified.
