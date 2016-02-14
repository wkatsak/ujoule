#!/usr/bin/python

from datetime import datetime
from Queue import Queue
from threading import Lock

def unix_ts(dt):
	epoch = datetime(month=1, day=1, year=1970)
	return int((dt - epoch).total_seconds())
