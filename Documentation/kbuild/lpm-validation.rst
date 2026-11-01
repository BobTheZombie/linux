.. SPDX-License-Identifier: GPL-2.0-only

LPM kernel validation record
============================

Scope
-----

Date: 2026-11-01. Base source: Linux 7.3.0 at
``cbbddb6b08cc9900a87cccaa9b22bbe06aa4f50a`` in BobTheZombie/linux.
Implementation and tests were AI-assisted by OpenAI Codex at the repository
owner's request. No human DCO certification is asserted.

Local builder: x86-64 Intel Xeon virtual host, GCC 13.3.0, GNU Binutils 2.42,
Meson 1.3.2, Ninja 1.11.1, Python 3.12, QEMU 8.2.2, e2fsprogs 1.47.0.
The builder is not a Ryzen machine. Results below apply to the tested source
and configurations; they are not a guarantee of data preservation.

Observed results
----------------

* Full x86_64_defconfig plus the optional Zen 2 profile: PASS. Built vmlinux,
  bzImage, Module.symvers, and 12 modules through Ninja. The build log had no
  compiler warnings or errors. Ext4 was built in for this configuration.
* Object command inspection: PASS. Ext4 compiled with ``-march=x86-64`` and
  ``-mtune=znver2``, retaining the kernel's no-SIMD flags. Disassembly confirms
  that the bulk range path calls the kernel's existing memset implementation.
* Incremental Ninja invocation: PASS. Re-entered Kbuild and completed without
  rebuilding the kernel objects.
* Native Meson conf and optional mconf compilation: PASS. All 34 upstream
  Kconfig tests passed using the Meson-built conf executable.
* Build bridge regression tests: PASS, seven tests. Includes existing config
  preservation, initial setup rollback, failure propagation, paths containing
  spaces, explicit staging requirements, and forwarding staging variables as
  Make command-line assignments.
* Regular Make x86_64_defconfig: PASS, with generic compiler tuning selected.
* Unsupported Zen 5 profile with GCC 13: correctly rejected. No partial
  ``.config`` remained to silently turn a retry into a generic build.
* Modules staged with depmod indexes: PASS. All 12 modules installed in a
  temporary staging directory. No host kernel modules were replaced.
* Userspace headers staged: PASS. Verified linux/types.h in the requested
  staging directory. INSTALL_HDR_PATH is forwarded as a Make argument because
  the top-level Makefile overrides its environment value.
* Actual-source bitmap oracle checks: PASS, 1,589,008 comparisons, with address
  and undefined-behavior sanitizers and fatal sanitizer recovery disabled.
  LeakSanitizer was disabled because the execution environment blocks its
  process-inspection mechanism. Range checking includes guard bytes, offsets,
  empty and partial ranges, all-zero/all-one/mixed data, and randomized ranges
  up to a 64K-bit bitmap.
* Ext4 KUnit under x86-64 QEMU with Zen 2 compiler tuning: PASS, 75 tests.
  The new range case runs with the suite's 1K/4K/64K block-size layout fixtures.
  An initial fixture initialization failure was corrected by parameterizing
  the new case to match the existing suite's required layout parameter.
* UML KUnit: compiled, but runtime unavailable. The host blocks ptrace before
  UML can boot; this attempt executed zero tests. QEMU supplied the successful
  runtime coverage above.
* Generic qemu64 CPU boot smoke: reached root mounting. The separate image
  without an initramfs intentionally had no root device and stopped there;
  this is not counted as a complete userspace boot.
* Full kernel plus static BusyBox initramfs and a disposable 128 MiB ext4 disk
  under QEMU: PASS. Created and verified a 16 MiB file, copied and renamed it,
  checked truncated contents and sparse-file size, allocated/deleted hundreds
  of small files, cleanly unmounted/remounted, rechecked checksums and contents,
  and powered off. Host read-only ``e2fsck -fn`` completed with exit status 0.
  The host never mounted the image.

Performance and deployment limits
--------------------------------

The userspace helper microbenchmark was run, but its libc memset, virtual CPU,
and scheduling noise make its timings unsuitable for claiming filesystem or
Ryzen performance gains. Large ranges benefit in that diagnostic benchmark;
short-range overhead remains a concern to measure inside the kernel. The
256-bit threshold is a prototype policy, not an established optimum.

No physical Ryzen, NVMe, SSD endurance, throughput, latency, power, or thermal
measurements were performed. No crash/power-cut recovery, fault injection,
xfstests, full feature matrix, Clang build, modular ext4 build, Rust build,
external module build, or other-architecture boot was validated locally.
Normal unmount/remount and fsck do not substitute for those tests.

The added GitHub workflow provides GCC/Clang builds, module/header staging,
bitmap sanitizers, guest filesystem smoke tests, and x86 QEMU ext4 KUnit.
Those CI jobs are configured; their results must be checked separately.

The native Ninja kernel build graph is not implemented. Kernel images and
modules continue to use GNU Make/Kbuild underneath the frontend; only conf
and mconf host compilation is native Meson/Ninja. Broader ext4 SSD allocation
and Ryzen runtime optimization remain future work. This experimental branch
must not be described as a completed build-system replacement, a proven
heavy performance optimization, or a guarantee against data loss.
