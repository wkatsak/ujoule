#!/usr/bin/python

import logging
import sys
import time
import math
import numpy
from datetime import datetime
from datetime import timedelta
from datetime import time as dt_time
from threading import Thread, Timer, Lock
from louie import dispatcher
from common import ujouleLouieSignals, Policy
from zwave import ujouleZWaveThermostat
from webapis import WeatherUndergroundTemperature, iCloudAwayDetector
from datacollector import ClimateDataCollector
from shell import ClimateControllerShell
from policy import *

class ClimateController(object):
	# sensors is a dictionary by location
	def __init__(self, thermostat, sensors, outsideSensor, setpoint=74.0):
		self.thermostat = thermostat
		self.sensors = sensors
		self.outsideSensor = outsideSensor
		self.policies = {}
		self.defaultPolicy = None
		self.policyInstances = {}
		self.awayDetectors = {}
		self.prevSetpoint = setpoint
		self.setpoint = setpoint

		self.policyLock = Lock()
		self.broadcastLock = Lock()
		self.policyTimer = None
		self.broadcastTimer = None

		self.dataCollector = ClimateDataCollector(self)
		self.shellImpl = ClimateControllerShell(self)

		self.logger = logging.getLogger("ClimateController")

	def getSensors(self):
		return list(self.sensors.keys())

	def getSensorTemp(self, sensor):
		return self.sensors[sensor].getTemperature()

	def getAllTemps(self):
		temps = []
		for sensor in self.getSensors():
			temp = self.getSensorTemp(sensor)
			if not math.isnan(temp):
				temps.append(temp)

		return temps

	def tempMean(self):
		temps = self.getAllTemps()
		mean = numpy.mean(temps)
		return mean

	def tempStdDev(self):
		temps = self.getAllTemps()
		stdDev = numpy.std(temps)
		return stdDev

	def tempMaxDelta(self):
		temps = self.getAllTemps()
		maxDelta = numpy.max(temps) - numpy.min(temps)
		return maxDelta

	def tempMin(self):
		temps = self.getAllTemps()
		minTemp = numpy.min(temps)
		return minTemp

	def tempMax(self):
		temps = self.getAllTemps()
		maxTemp = numpy.max(temps)
		return maxTemp

	def instantiatePolicy(self, policy):
		if policy not in self.policyInstances:
			self.policyInstances[policy] = policy(self)

	def setDefaultPolicy(self, policy):
		self.defaultPolicy = policy
		self.instantiatePolicy(policy)

	def addPolicy(self, policy, times=None):
		self.policies[times] = policy
		self.instantiatePolicy(policy)

	def addAwayDetector(self, name, detector):
		self.awayDetectors[name] = detector

	def setSetpoint(self, setpoint):
		if setpoint != self.prevSetpoint:
			dispatcher.send(signal=ujouleLouieSignals.SIGNAL_SETPOINT_CHANGED, sender=self.setSetpoint, value=setpoint)
			self.prevSetpoint = self.setpoint

		self.setpoint = setpoint
		self.broadcastParams()

	def getSetpoint(self):
		return self.setpoint

	def away(self):
		for name in self.awayDetectors:
			detector = self.awayDetectors[name]
			if not detector.isAway():
				return False

		return True

	def broadcastParams(self):
		if not self.broadcastLock.acquire(False):
			return

		if self.broadcastTimer:
			self.broadcastTimer.cancel()

		dispatcher.send(signal=ujouleLouieSignals.SIGNAL_SETPOINT_UPDATED, sender=self.broadcastParams, value=self.setpoint)
		# set up a timer
		self.broadcastTimer = Timer(60.0, self.broadcastParams)
		self.broadcastTimer.start()

		self.broadcastLock.release()

	def executePolicy(self, sender=None):
		# try to obtain the lock, if we cannot, someone else is already executing
		# the policy, so no sense in doing it again
		if not self.policyLock.acquire(False):
			return

		# if we are inside, try to cancel the timer, if possible
		if self.policyTimer:
			self.policyTimer.cancel()

		self.logger.info("entered executePolicy, caused by %s" % str(sender))

		# see what time it is
		nowTime = datetime.now().time()

		# find the currently valid policy
		policy = self.defaultPolicy
		for start, end in self.policies:
			if end >= start:
				if nowTime >= start and nowTime < end:
					policy = self.policies[start, end]
					break
			else:
				if nowTime >= start or nowTime < end:
					policy = self.policies[start, end]
					break

		if policy:
			self.logger.info("using policy: %s" % str(policy))
			# execute policy
			self.policyInstances[policy].execute()
		else:
			self.logger.info("no policy configured")

		# set up a timer to guarantee we rerun in 240s
		self.policyTimer = Timer(240.0, self.executePolicy, [Timer])
		self.policyTimer.start()

		self.logger.info("finished executePolicy")

		# drop the lock
		self.policyLock.release()

	def start(self):
		self.thermostat.setSystemMode(ujouleZWaveThermostat.SYS_MODE_OFF)
		self.thermostat.setFanMode(ujouleZWaveThermostat.FAN_MODE_AUTO)

		dispatcher.connect(self.executePolicy, ujouleLouieSignals.SIGNAL_TEMPERATURE_CHANGED)
		dispatcher.connect(self.executePolicy, ujouleLouieSignals.SIGNAL_SETPOINT_CHANGED)
		dispatcher.connect(self.executePolicy, ujouleLouieSignals.SIGNAL_AWAY_STATE_CHANGED)

		self.dataCollector.start()
		self.broadcastParams()
		self.executePolicy()

	def stop(self):
		if self.policyTimer:
			self.policyTimer.cancel()
		if self.broadcastTimer:
			self.broadcastTimer.cancel()

		self.thermostat.setSystemMode(ujouleZWaveThermostat.SYS_MODE_OFF)
		self.thermostat.setFanMode(ujouleZWaveThermostat.FAN_MODE_AUTO)

	def shell(self):
		self.shellImpl.shell()