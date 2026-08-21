#!/usr/bin/env python3
"""Stand-in for pulseaudio/snapclient/squeezelite/ledfx.

No audio, no network, no privileges - it only has to be a process that lives,
dies or ignores SIGTERM on demand, so the supervisor's behaviour can be tested.

argv: fake_service.py <name> [mode]
  run     stay alive until terminated (default)
  crash   exit non-zero at once, to exercise the restart backoff
  stubborn ignore SIGTERM, to exercise the SIGKILL path
"""
import os
import signal
import sys
import time

name = sys.argv[1] if len(sys.argv) > 1 else "fake"
mode = sys.argv[2] if len(sys.argv) > 2 else "run"

print("%s started pid=%d args=%s" % (name, os.getpid(), " ".join(sys.argv[1:])), flush=True)
print("%s PULSE_LATENCY_MSEC=%s" % (name, os.environ.get("PULSE_LATENCY_MSEC", "")), flush=True)

if mode == "crash":
    print("%s simulated failure" % name, flush=True)
    sys.exit(3)

if mode == "stubborn":
    signal.signal(signal.SIGTERM, lambda *_: None)
else:
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))

while True:
    time.sleep(0.05)
