#!/usr/bin/python

import logging
import sys
from common import ujouleLouieSignals, getLogger
from helpers import unix_ts
from datetime import datetime
from louie import dispatcher

class ClimateDataCollector(object):

	def __init__(self, controller, dataPath="data"):
		self.controller = controller
		self.dataPath = dataPath
		self.logger = getLogger(self)

	def start(self):
		dispatcher.connect(self.logValue, ujouleLouieSignals.SIGNAL_TEMPERATURE_UPDATED)
		dispatcher.connect(self.logValue, ujouleLouieSignals.SIGNAL_OUTSIDE_TEMPERATURE_UPDATED)
		dispatcher.connect(self.logValue, ujouleLouieSignals.SIGNAL_SETPOINT_UPDATED)

	def writeFile(self, filename, timestamp, value):
		with open(filename, "a") as f:
			f.write("%s %0.1f\n" % (timestamp, value))

	def logValue(self, signal, sender, value):
		self.logger.debug("logging value: signal=%d, sender=%s, value=%0.2f" % (signal, sender, value))
		unixTimeNow = unix_ts(datetime.now())

		if signal == ujouleLouieSignals.SIGNAL_TEMPERATURE_UPDATED:
			foundSensor = None
			for sensor in self.controller.sensors:
				if self.controller.sensors[sensor] == sender:
					foundSensor = sensor
					break
			if foundSensor:
				logFile = "%s/sensor-%s.dat" % (self.dataPath, foundSensor)		
				self.writeFile(logFile, unixTimeNow, value)

		elif signal == ujouleLouieSignals.SIGNAL_OUTSIDE_TEMPERATURE_UPDATED:
			logFile = "%s/sensor-outside.dat" % (self.dataPath)
			self.writeFile(logFile, unixTimeNow, value)

		elif signal == ujouleLouieSignals.SIGNAL_SETPOINT_UPDATED:
			logFile = "%s/setpoint.dat" % (self.dataPath)
			self.writeFile(logFile, unixTimeNow, value)

		elif signal == ujouleLouieSignals.SIGNAL_AWAY_STATE_UPDATED:
			logFile = "%s/away.dat" % (self.dataPath)
			self.writeFile(logFile, unixTimeNow, 1 if value else 0)
