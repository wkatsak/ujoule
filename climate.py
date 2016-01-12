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
from common import ujouleLouieSignals, Policy, getLogger
from zwave import ujouleZWaveThermostat
from webapis import WeatherUndergroundTemperature, iCloudAwayDetector
from datacollector import ClimateDataCollector
from shell import ClimateControllerShell

class ClimateControllerConfig(object):
	def __init__(self, policy, setpoint):
		self.policy = policy
		self.setpoint = setpoint

	def __str__(self):
		return "ClimateControllerConfig(policy=%s, setpoint=%0.1f)" % (self.policy.__name__, self.setpoint)

	def __repr__(self):
		return self.__str__()

# class to maintain state
class ClimateControllerState(object):
	def __init__(self, orig=None):
		if orig == None:
			self.systemMode = ujouleZWaveThermostat.SYS_MODE_OFF
			self.systemSetTime = None
			self.fanMode = ujouleZWaveThermostat.FAN_MODE_AUTO
			self.fanSetTime = None
			self.vars = {}
		else:
			self.systemMode = orig.systemMode
			self.systemSetTime = orig.systemSetTime
			self.fanMode = orig.fanMode
			self.fanSetTime = orig.fanSetTime
			self.vars = dict(orig.vars)

	def getCustomState(self, varName):
		if varName not in self.vars:
			self.vars[varName] = None

		return self.vars[varName]

	def setCustomState(self, varName, varValue):
		self.vars[varName] = varValue

	def __str__(self):
		return "ClimateControllerState(systemMode=%s, fanMode=%s)" % (self.systemMode, self.fanMode)

	def __repr__(self):
		return self.__str__()

class ClimateController(object):
	# sensors is a dictionary by location
	def __init__(self, thermostat, sensors, outsideSensor, defaultConfig):
		self.thermostat = thermostat
		self.sensors = sensors
		self.outsideSensor = outsideSensor

		self.policyInstances = {}
		self.defaultConfig = defaultConfig
		self.scheduledConfigs = []
		self.scheduledConfigTimes = {}

		self.awayDetectors = {}

		self.policy = defaultConfig.policy
		self.setpoint = defaultConfig.setpoint

		self.currentState = ClimateControllerState()

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

	def getTemps(self, locations):
		temps = []
		for sensor in locations:
			temp = self.getSensorTemp(sensor)
			if not math.isnan(temp):
				temps.append(temp)

		return temps

	def getAllTemps(self):
		return self.getTemps(self.getSensors())

	def tempMean(self, locations=None):
		if not locations:
			temps = self.getAllTemps()
		else:
			temps = self.getTemps(locations)

		mean = numpy.mean(temps)
		return mean

	def tempStdDev(self, locations=None):
		if not locations:
			temps = self.getAllTemps()
		else:
			temps = self.getTemps(locations)

		stdDev = numpy.std(temps)
		return stdDev

	def tempMaxDelta(self, locations=None):
		if not locations:
			temps = self.getAllTemps()
		else:
			temps = self.getTemps(locations)

		maxDelta = numpy.max(temps) - numpy.min(temps)
		return maxDelta

	def tempMin(self, locations=None):
		if not locations:
			temps = self.getAllTemps()
		else:
			temps = self.getTemps(locations)

		minTemp = numpy.min(temps)
		return minTemp

	def tempMax(self, locations=None):
		if not locations:
			temps = self.getAllTemps()
		else:
			temps = self.getTemps(locations)

		maxTemp = numpy.max(temps)
		return maxTemp

	def getPolicyInstance(self, policy):
		if policy not in self.policyInstances:
			self.policyInstances[policy] = policy(self)

		return self.policyInstances[policy]

	def getCurrentState(self):
		return self.currentState

	def setDefaultConfig(self, config):
		self.defaultConfig = config
		self.instantiatePolicy(policy)

	def addScheduledConfig(self, config, startTime, endTime):
		for conf in self.scheduledConfigTimes:
			start, end = self.scheduledConfigTimes[conf]
			tmp = datetime(year=1970, month=1, day=1, hour=end.hour, minute=end.minute, second=end.second) - timedelta(milliseconds=1)
			end = tmp.time()

			if self.timeBetween(start, startTime, endTime) or self.timeBetween(end, startTime, endTime):
				raise Exception("Cannot add config, conflicts with existing schedule...")

		self.scheduledConfigs.append(config)
		self.scheduledConfigTimes[config] = (startTime, endTime)

		self.scheduledConfigs.sort(key=lambda x : self.scheduledConfigTimes[x])

	def getScheduledConfigs(self):
		return list(self.scheduledConfigs)

	def addAwayDetector(self, name, detector):
		self.awayDetectors[name] = detector

	def setPolicy(self, policy):
		if policy != self.policy:
			dispatcher.send(signal=ujouleLouieSignals.SIGNAL_POLICY_CHANGED, sender=self.setPolicy, value=policy)
			self.policy = policy

	def setSetpoint(self, setpoint):
		if setpoint != self.setpoint:
			dispatcher.send(signal=ujouleLouieSignals.SIGNAL_SETPOINT_CHANGED, sender=self.setSetpoint, value=setpoint)
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

	def timeBetween(self, targetTime, startTime, endTime):
		if endTime >= startTime:
			if targetTime >= startTime and targetTime < endTime:
				return True
		else:
			if targetTime >= startTime or targetTime < endTime:
				return True

		return False

	# find the currently valid config
	def getConfigByTime(self, targetTime):
		targetConfig = self.defaultConfig

		for config in self.scheduledConfigs:
			start, end = self.scheduledConfigTimes[config]

			if self.timeBetween(targetTime, start, end):
				targetConfig = config
				break

		return targetConfig

	def applyConfig(self, config):
		self.setPolicy(config.policy)
		self.setSetpoint(config.setpoint)

	def testSchedule(self):
		# see what time it is and apply the correct configuration
		for i in xrange(0, 23):
			for j in xrange(0, 59, 15):
				t = dt_time(hour=i, minute=j)

				config = self.getConfigByTime(t)
				print "At time %s, config is %s" % (t, config)

	def executePolicy(self, sender=None):
		# try to obtain the lock, if we cannot, someone else is already executing
		# the policy, so no sense in doing it again
		if not self.policyLock.acquire(False):
			return

		# if we are inside, try to cancel the timer, if possible
		if self.policyTimer:
			self.policyTimer.cancel()

		self.logger.info("entered executePolicy, caused by %s" % str(sender))

		# see what time it is and apply the correct configuration
		nowTime = datetime.now().time()
		config = self.getConfigByTime(nowTime)
		self.logger.info("applying config: %s" % config)
		self.applyConfig(config)

		# execute the configured policy
		policyInstance = self.getPolicyInstance(self.policy)
		nextState = policyInstance.execute()

		# use whatever is set in the nextState to configure the system
		if nextState.fanMode != self.currentState.fanMode:
			nextState.fanSetTime = datetime.now()
			self.logger.info("Setting fan mode to %s" % self.thermostat.constToString(nextState.fanMode))
			self.thermostat.setFanMode(nextState.fanMode)

		if nextState.systemMode != self.currentState.systemMode:
			nextState.systemSetTime = datetime.now()
			self.logger.info("Setting system mode to %s" % self.thermostat.constToString(nextState.systemMode))
			self.thermostat.setSystemMode(nextState.systemMode)

		self.currentState = nextState

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


if __name__ == "__main__":
	pass
	#from policy import BasicSubsumptionArchPolicy, SubsumptionArchBedtimePolicy
	#defaultConfig = ClimateControllerConfig(policy=BasicSubsumptionArchPolicy, setpoint=74.0)
	#climateController = ClimateController(None, None, None, defaultConfig=defaultConfig)
	#climateController.addScheduledConfig(ClimateControllerConfig(policy=SubsumptionArchBedtimePolicy, setpoint=71.0), startTime=dt_time(hour=19, minute=45), endTime=dt_time(hour=7))
	#climateController.testSchedule()
	#print climateController.getScheduledConfigs()
	#climateController.addScheduledConfig(ClimateControllerConfig(policy=SubsumptionArchBedtimePolicy, setpoint=80.0), startTime=dt_time(hour=7), endTime=dt_time(hour=10))
	#climateController.testSchedule()
	#print climateController.getScheduledConfigs()
