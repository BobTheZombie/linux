#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Boot an x86 kernel against a disposable ext4 image, without host mounts.

Requires a statically linked BusyBox, QEMU, mkfs.ext4, and e2fsck. This checks
clean filesystem operations only; it is not a crash or power-failure test.
"""
import argparse
import gzip
from pathlib import Path
import shlex
import subprocess
import tempfile

INIT = r'''#!/bin/busybox sh
set -eu
export PATH=/bin
/bin/busybox --install -s /bin
trap 'echo LPM_EXT4_SMOKE_FAIL; poweroff -f' EXIT
mkdir -p /proc /sys /dev /mnt /tmp
mount -t proc proc /proc
mount -t sysfs sysfs /sys
mount -t devtmpfs devtmpfs /dev
mount -t ext4 /dev/vda /mnt
# Exercise large allocation plus many small allocations and frees.
dd if=/dev/urandom of=/mnt/payload bs=1048576 count=16
sha256sum /mnt/payload > /tmp/checksum
cp /mnt/payload /mnt/copy
cmp /mnt/payload /mnt/copy
mv /mnt/copy /mnt/renamed
truncate -s 8193 /mnt/renamed
[ "$(stat -c %s /mnt/renamed)" = 8193 ]
head -c 8193 /mnt/payload > /tmp/prefix
cmp /tmp/prefix /mnt/renamed
truncate -s 33554432 /mnt/sparse
[ "$(stat -c %s /mnt/sparse)" = 33554432 ]
mkdir /mnt/small
for n in $(seq 1 256); do
    printf 'allocation-%s\n' "$n" > /mnt/small/"$n"
done
for n in $(seq 1 2 255); do rm /mnt/small/"$n"; done
sync
umount /mnt
mount -t ext4 /dev/vda /mnt
sha256sum -c /tmp/checksum
cmp /tmp/prefix /mnt/renamed
for n in $(seq 2 2 256); do
    [ "$(cat /mnt/small/"$n")" = "allocation-$n" ]
done
rm -rf /mnt/small /mnt/sparse /mnt/renamed
sync
umount /mnt
trap - EXIT
echo LPM_EXT4_SMOKE_PASS
poweroff -f
'''


def archive_entry(name, data, mode, inode):
    encoded = name.encode() + b'\0'
    fields = [inode, mode, 0, 0, 1, 0, len(data), 0, 0, 0, 0, len(encoded), 0]
    header = b'070701' + ''.join(f'{value:08x}' for value in fields).encode()
    record = header + encoded
    record += b'\0' * (-len(record) % 4)
    record += data
    record += b'\0' * (-len(data) % 4)
    return record


def initramfs(busybox):
    result = b''
    entries = [('bin', b'', 0o040755), ('dev', b'', 0o040755),
               ('proc', b'', 0o040755), ('sys', b'', 0o040755),
               ('mnt', b'', 0o040755), ('tmp', b'', 0o040755),
               ('bin/busybox', busybox.read_bytes(), 0o100755),
               ('init', INIT.encode(), 0o100755), ('TRAILER!!!', b'', 0)]
    for inode, (name, data, mode) in enumerate(entries, 1):
        result += archive_entry(name, data, mode, inode)
    return gzip.compress(result, mtime=0)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kernel', type=Path, required=True)
    parser.add_argument('--busybox', type=Path, required=True)
    parser.add_argument('--qemu', default='qemu-system-x86_64')
    parser.add_argument('--qemu-args', default='', help='Additional trusted QEMU options')
    parser.add_argument('--timeout', type=int, default=120)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='lpm-ext4-smoke-') as temp:
        directory = Path(temp)
        disk = directory / 'ext4.img'
        archive = directory / 'initramfs.cpio.gz'
        # Only this newly created regular file is ever passed to mkfs/QEMU.
        with disk.open('xb') as image:
            image.truncate(128 * 1024 * 1024)
        archive.write_bytes(initramfs(args.busybox))
        subprocess.run(['mkfs.ext4', '-F', '-q', str(disk)], check=True)
        command = [args.qemu, '-nodefaults', '-m', '512', '-cpu', 'qemu64',
                   '-kernel', str(args.kernel.resolve()), '-initrd', str(archive),
                   '-append', 'console=ttyS0 rdinit=/init panic=-1',
                   '-drive', f'file={disk},if=virtio,format=raw',
                   '-no-reboot', '-nographic', '-serial', 'stdio']
        command += shlex.split(args.qemu_args)
        boot = subprocess.run(command, capture_output=True, text=True,
                              errors='replace', timeout=args.timeout)
        print(boot.stdout, end='')
        if boot.stderr:
            print(boot.stderr, end='')
        if (boot.returncode != 0 or 'LPM_EXT4_SMOKE_PASS' not in boot.stdout or
                'LPM_EXT4_SMOKE_FAIL' in boot.stdout):
            raise RuntimeError('guest filesystem smoke test failed')
        subprocess.run(['e2fsck', '-f', '-n', str(disk)], check=True)
        print('PASS: guest ext4 operations, remount checksums, and host read-only fsck')


if __name__ == '__main__':
    main()
