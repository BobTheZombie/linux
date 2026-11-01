#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Test actual ext4 range helper bodies against a bitwise oracle in userspace.

This is not a kernel, filesystem, persistence, or crash-consistency test.
"""
import argparse
from pathlib import Path
import shlex
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
BASE = 'cbbddb6b08cc9900a87cccaa9b22bbe06aa4f50a'


def functions(source, prefix):
    result = []
    for name in ('mb_clear_bits', 'mb_set_bits'):
        start = source.index('void ' + name + '(')
        end = source.index('\n}', start) + 2
        result.append('__attribute__((noinline)) ' + source[start:end].replace(name, prefix + name))
    return '\n'.join(result)


HARNESS = r'''
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
typedef uint32_t __u32;
static void mb_clear_bit(int bit, void *bm)
{
    ((unsigned char *)bm)[bit >> 3] &= ~(1U << (bit & 7));
}
static void mb_set_bit(int bit, void *bm)
{
    ((unsigned char *)bm)[bit >> 3] |= 1U << (bit & 7);
}
/* HELPERS */
static uint32_t state = 0xc0ffee;
static uint32_t random_word(void)
{
    state ^= state << 13;
    state ^= state >> 17;
    state ^= state << 5;
    return state;
}
static void check(int offset, int start, int len, int fill, int set)
{
    unsigned char actual[8256], expected[8256];
    int bit;
    memset(actual, fill, sizeof(actual));
    memcpy(expected, actual, sizeof(actual));
    for (bit = start; bit < start + len; bit++) {
        unsigned char *byte = expected + 16 + offset + (bit >> 3);
        if (set)
            *byte |= 1U << (bit & 7);
        else
            *byte &= ~(1U << (bit & 7));
    }
    if (set)
        new_mb_set_bits(actual + 16 + offset, start, len);
    else
        new_mb_clear_bits(actual + 16 + offset, start, len);
    if (memcmp(actual, expected, sizeof(actual))) {
        fprintf(stderr, "mismatch offset=%d start=%d len=%d fill=%d set=%d\n",
                offset, start, len, fill, set);
        exit(1);
    }
}
static void correctness(void)
{
    unsigned long cases = 0;
    int set, offset, start, len, fill, i;
    for (set = 0; set <= 1; set++)
        for (offset = 0; offset < 8; offset++)
            for (start = 0; start < 128; start++)
                for (len = 0; len <= 256; len++) {
                    for (fill = 0; fill < 3; fill++) {
                        check(offset, start, len,
                              fill == 0 ? 0 : fill == 1 ? 255 : 165, set);
                        cases++;
                    }
                }
    for (i = 0; i < 10000; i++) {
        start = random_word() % 65536;
        len = random_word() % (65537 - start);
        check(random_word() % 8, start, len, random_word() & 255, random_word() & 1);
        cases++;
    }
    printf("PASS: %lu oracle comparisons, including guard bytes\n", cases);
}
static double measure(void (*fn)(void *, int, int), int start, int len)
{
    struct timespec before, after;
    unsigned char bitmap[8192];
    int i;
    memset(bitmap, 0xa5, sizeof(bitmap));
    clock_gettime(CLOCK_MONOTONIC, &before);
    for (i = 0; i < 300000; i++) {
        fn(bitmap, start, len);
        __asm__ __volatile__("" : : "r"(bitmap) : "memory");
    }
    clock_gettime(CLOCK_MONOTONIC, &after);
    return ((after.tv_sec - before.tv_sec) * 1e9 + after.tv_nsec - before.tv_nsec) / 300000;
}
int main(int argc, char **argv)
{
    const int lengths[] = {1, 8, 31, 32, 64, 128, 512, 4096, 32768};
    unsigned int i;
    int set, start, trial;
    if (argc == 1) {
        correctness();
        return 0;
    }
    puts("operation,start,bits,trial,old_ns,new_ns");
    for (set = 0; set <= 1; set++)
        for (start = 0; start <= 3; start += 3)
            for (i = 0; i < sizeof(lengths) / sizeof(lengths[0]); i++)
                for (trial = 0; trial < 5; trial++) {
                    double old = measure(set ? old_mb_set_bits : old_mb_clear_bits,
                                         start, lengths[i]);
                    double new = measure(set ? new_mb_set_bits : new_mb_clear_bits,
                                         start, lengths[i]);
                    printf("%s,%d,%d,%d,%.3f,%.3f\n", set ? "set" : "clear",
                           start, lengths[i], trial, old, new);
                }
    return 0;
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', default=BASE)
    parser.add_argument('--cc', default='cc')
    parser.add_argument('--benchmark', action='store_true')
    args = parser.parse_args()
    old = subprocess.check_output(['git', 'show', args.base + ':fs/ext4/mballoc.c'],
                                  cwd=ROOT, text=True)
    new = (ROOT / 'fs/ext4/mballoc.c').read_text()
    body = HARNESS.replace('/* HELPERS */', functions(old, 'old_') + functions(new, 'new_'))
    with tempfile.TemporaryDirectory(prefix='ext4-bitmap-') as temp:
        source = Path(temp) / 'check.c'
        binary = Path(temp) / 'check'
        source.write_text(body)
        command = shlex.split(args.cc) + ['-O2', '-Wall', '-Werror', str(source), '-o', str(binary)]
        if not args.benchmark:
            command += ['-fsanitize=address,undefined', '-fno-sanitize-recover=all',
                        '-fno-omit-frame-pointer']
        # The benchmark links userspace libc, not the kernel's memset.
        # Its timings are diagnostic and cannot predict kernel throughput.
        subprocess.run(command, check=True)
        subprocess.run([str(binary)] + (['benchmark'] if args.benchmark else []), check=True)


if __name__ == '__main__':
    main()
