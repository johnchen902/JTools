#!/usr/bin/env python3
import argparse, subprocess, io, os, threading

__all__ = ['parse_args', 'popen', 'stdio']

def create_echo_stream(raw):
    fdr, fdw = os.pipe()
    def run():
        with raw, os.fdopen(fdw, 'wb', buffering=0) as w:
            while True:
                data = raw.read(8192)
                if not data:
                    break
                print(data)
                w.write(data)
    t = threading.Thread(target=run, daemon=False)
    t.start()
    return os.fdopen(fdr, 'rb', buffering=0)

def parse_args(description=None):
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument('--echo', action='store_true')
    parser.add_argument('--buffer', action='store_true')
    parser.add_argument('command')
    parser.add_argument('arguments', nargs=argparse.REMAINDER)
    return parser.parse_args()

def popen(args):
    return subprocess.Popen([args.command] + args.arguments,
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, bufsize = 0)

def stdio(args, proc):
    pin = proc.stdout
    pout = proc.stdin
    if args.echo:
        pin = create_echo_stream(pin)
    if args.buffer:
        pin = io.BufferedReader(pin)
    return (pin, pout)
