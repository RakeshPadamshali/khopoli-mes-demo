"""Shared helpers for the Khopoli demo data generator. Everything is deterministic (seeded).
All dates are RELATIVE to the as-of date, which defaults to TODAY (override: --asof YYYY-MM-DD or env KHP_ASOF),
so re-running the generator before a demo makes the whole dataset current without changing any id or story."""
import os, sys, random
from datetime import datetime, timedelta


def _asof():
    v = None
    for i, a in enumerate(sys.argv):
        if a == "--asof" and i + 1 < len(sys.argv): v = sys.argv[i + 1]
        elif a.startswith("--asof="): v = a.split("=", 1)[1]
    v = v or os.environ.get("KHP_ASOF")
    d = datetime.strptime(v, "%Y-%m-%d") if v else datetime.now()
    return d.replace(hour=10, minute=30, second=0, microsecond=0)      # "now" for the demo = as-of day, 10:30, shift A


R = random.Random(2609)
ASOF = _asof()
DAY0 = ASOF.replace(hour=0, minute=0, second=0, microsecond=0)
BASE = DAY0 - timedelta(days=14)                                   # plan window start (2 weeks of history)
END = DAY0 + timedelta(days=15, hours=23, minutes=59)
YM = ASOF.strftime("%y%m")                                          # year/month batch token, e.g. 2609
YM_PREV = (DAY0.replace(day=1) - timedelta(days=1)).strftime("%y%m")  # previous month (HR coils received earlier)


def at(days, hour=0, minute=0, second=0):
    """datetime at an offset in days from the as-of day (0 = as-of day) with a time of day"""
    return DAY0 + timedelta(days=days, hours=hour, minutes=minute, seconds=second)


def dstr(days):
    return (DAY0 + timedelta(days=days)).strftime("%Y-%m-%d")


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
