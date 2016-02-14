#!/usr/bin/python
import sys
from datetime import datetime
from datetime import timedelta
from helpers import unix_ts

if __name__ == "__main__":
	filename = sys.argv[1]
	hours = int(sys.argv[2])

	current_ts = unix_ts(datetime.now())
	earliest_ts = current_ts - hours*60.0*60.0
	good_data = []

	with open(filename, "r") as f:
		lines = f.readlines()
		for line in lines:
			line = line.strip()
			timestamp, reading = line.split()
			timestamp = int(timestamp)
			reading = float(reading)
			if timestamp >= earliest_ts:
				good_data.append((timestamp, reading))

	with open(filename.replace(".dat", "-last.dat"), "w") as f:
		for data in good_data:
			f.write("%d %f\n" % (data[0], data[1]))
