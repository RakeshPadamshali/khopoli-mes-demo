"""Shared helpers for the Khopoli demo data generator. Everything is deterministic (seeded)."""
import random
from datetime import datetime, timedelta

R = random.Random(2609)
BASE = datetime(2026, 9, 1, 0, 0)          # plan window start (Tue 1 Sep 2026)
ASOF = datetime(2026, 9, 15, 10, 30)       # "now" for the demo (Tue 15 Sep 2026, shift A)
END = datetime(2026, 9, 30, 23, 59)


def iso(d):
    return d.strftime('%Y-%m-%dT%H:%M:%S') if d else None


def day(d):
    return d.strftime('%Y-%m-%d')


def h(x):
    return timedelta(hours=x)


def m(x):
    return timedelta(minutes=x)


def r1(x):
    return round(x + 1e-9, 1)


def r2(x):
    return round(x + 1e-9, 2)


def pick(seq):
    return R.choice(seq)


def between(a, b):
    return a + (b - a) * R.random()


def shift_of(d):
    hr = d.hour
    return 'A' if 6 <= hr < 14 else 'B' if 14 <= hr < 22 else 'C'


def status_vs_asof(start, end):
    if end <= ASOF:
        return 'DONE'
    if start <= ASOF:
        return 'IN_PROGRESS'
    return 'PLANNED'


class Seq:
    """Running counters for ids."""
    def __init__(self):
        self.c = {}

    def next(self, key):
        self.c[key] = self.c.get(key, 0) + 1
        return self.c[key]


SEQ = Seq()
