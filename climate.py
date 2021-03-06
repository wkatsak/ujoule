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
from common import ujouleLouieSignals, Policy, getLogger, getObjectName
from zwave import ujouleZWaveThermostat
from webapis import WeatherUndergroundService, iCloudAwayDetector
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
			self.heatSetpoint = None
			self.coolSetpoint = None
			self.vars = {}
		else:
			self.systemMode = orig.systemMode
			self.systemSetTime = orig.systemSetTime
			self.fanMode = orig.fanMode
			self.fanSetTime = orig.fanSetTime
			self.heatSetpoint = orig.heatSetpoint
			self.coolSetpoint = orig.coolSetpoint
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
	MODE_AUTO = "MODE_AUTO"
	MODE_HEAT = "MODE_HEAT"
	MODE_COOL = "MODE_COOL"

	# sensors is a dictionary by location
	def __init__(self, thermostat, sensors, outsideSensor, mode=None, autoCoolThreshold=None):
		self.logger = getLogger(self)

		self.thermostat = thermostat
		self.sensors = sensors
		self.outsideSensor = outsideSensor

		self.policyInstances = {}

		self.defaultConfigs = {}
		self.defaultConfigs[ClimateController.MODE_HEAT] = None
		self.defaultConfigs[ClimateController.MODE_COOL] = None

		self.scheduledConfigs = {}
		self.scheduledConfigs[ClimateController.MODE_HEAT] = []
		self.scheduledConfigs[ClimateController.MODE_COOL] = []

		self.scheduledConfigTimes = {}
		self.scheduledConfigTimes[ClimateController.MODE_HEAT] = {}
		self.scheduledConfigTimes[ClimateController.MODE_COOL] = {}

		if not mode:
			mode = ClimateController.MODE_AUTO

		if mode == ClimateController.MODE_AUTO:
			if not autoCoolThreshold:
				raise Exception("autoCoolThreshold must be set with mode=MODE_AUTO...")
			self.coolThreshold = autoCoolThreshold

		self.mode = mode

		self.override = False

		self.awayDetectors = {}

		#mode = self.getMode()
		self.policy = None
		self.setpoint = 0.0

		self.currentState = ClimateControllerState()

		self.policyLock = Lock()
		self.broadcastLock = Lock()
		self.policyTimer = None
		self.broadcastTimer = None

		self.dataCollector = ClimateDataCollector(self)
		self.shellImpl = ClimateControllerShell(self)

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

	def tempOutside(self):
		return self.outsideSensor.getTemperature()

	def getPolicyInstance(self, policy):
		if policy not in self.policyInstances:
			self.policyInstances[policy] = policy(self)

		return self.policyInstances[policy]

	def getCurrentState(self):
		return self.currentState

	def setAutoCoolTreshold(self, threshold):
		self.coolThreshold = threshold

	def setDefaultConfig(self, mode, config):
		self.defaultConfigs[mode] = config

	def addScheduledConfig(self, mode, config, startTime, endTime):
		for conf in self.scheduledConfigTimes[mode]:
			start, end = self.scheduledConfigTimes[mode][conf]
			tmp = datetime(year=1970, month=1, day=1, hour=end.hour, minute=end.minute, second=end.second) - timedelta(milliseconds=1)
			end = tmp.time()

			if self.timeBetween(start, startTime, endTime) or self.timeBetween(end, startTime, endTime):
				raise Exception("Cannot add config, conflicts with existing schedule...")

		self.scheduledConfigs[mode].append(config)
		self.scheduledConfigTimes[mode][config] = (startTime, endTime)

		self.scheduledConfigs[mode].sort(key=lambda x : self.scheduledConfigTimes[mode][x])

	def removeScheduledConfig(self, mode, index):
		self.scheduledConfigs[mode].pop(index)

	def getScheduledConfigs(self, mode):
		return list(self.scheduledConfigs[mode])

	def getScheduledConfigTimes(self, mode):
		return dict(self.scheduledConfigTimes[mode])

	'''
	def saveConfig(self):
		self.configDict["defaultConfig"] = self.defaultConfig
		self.configDict["scheduledConfig"] = self.scheduledConfigs
		self.configDict["scheduledConfigTimes"] = self.scheduledConfigTimes
		self.configDict.commit()

	def loadConfig(self):
		try:
			self.defaultConfig = self.configDict["defaultConfig"]
			self.scheduledConfigs = self.configDict["scheduledConfig"]
			self.scheduledConfigTimes = self.configDict["scheduledConfigTimes"]
		except KeyError:
			self.defaultConfig = None
			self.scheduledConfigs = []
			self.scheduledConfigTimes = {}

		self.applyConfig(self.defaultConfig)
	'''

	def addAwayDetector(self, name, detector):
		self.awayDetectors[name] = detector

	def setPolicy(self, policy):
		# if the policy has changed
		if policy != self.policy:
			# change it
			self.policy = policy

			# Reset the system to avoid an indeterminate state
			self.updateState(ClimateControllerState())

			# send a signal
			dispatcher.send(signal=ujouleLouieSignals.SIGNAL_POLICY_CHANGED, sender=self.setPolicy, value=policy)

	def setSetpoint(self, setpoint):
		if setpoint != self.setpoint:
			dispatcher.send(signal=ujouleLouieSignals.SIGNAL_SETPOINT_CHANGED, sender=self.setSetpoint, value=setpoint)
			self.setpoint = setpoint
			self.broadcastParams()

	def getSetpoint(self):
		return self.setpoint

	def overrideEnable(self):
		self.policyLock.acquire()
		self.override = True
		self.policyLock.release()

	def overrideDisable(self):
		self.policyLock.acquire()
		self.override = False
		self.policyLock.release()

	def away(self):
		if len(self.awayDetectors) == 0:
			return False

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

		dispatcher.send(signal=ujouleLouieSignals.SIGNAL_FAN_ON_UPDATED,
							sender=self.broadcastParams,
							value=True if self.currentState.fanMode == ujouleZWaveThermostat.FAN_MODE_ON else False)

		dispatcher.send(signal=ujouleLouieSignals.SIGNAL_HEAT_ON_UPDATED,
							sender=self.broadcastParams,
							value=True if self.currentState.systemMode == ujouleZWaveThermostat.SYS_MODE_HEAT else False)

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
	def getConfigByTime(self, mode, targetTime):
		targetConfig = self.defaultConfigs[mode]

		for config in self.scheduledConfigs[mode]:
			start, end = self.scheduledConfigTimes[mode][config]

			if self.timeBetween(targetTime, start, end):
				targetConfig = config
				break

		return targetConfig

	def getMode(self):
		# see what mode we are supposed to be in
		if self.mode == ClimateController.MODE_HEAT:
			self.logger.info("In MODE_HEAT, using heat configs...")
			mode = self.mode
		elif self.mode == ClimateController.MODE_COOL:
			self.logger.info("In MODE_COOL, using cool configs...")
			mode = self.mode
		else:
			self.logger.info("In MODE_AUTO, selecting configs based on outside temperature...")
			if self.tempOutside() >= self.coolThreshold:
				self.logger.info("Outside >= %0.2f F, using cool configs..." % self.coolThreshold)
				mode = ClimateController.MODE_COOL
			else:
				self.logger.info("Outside < %0.2f F, using heat configs..." % self.coolThreshold)
				mode = ClimateController.MODE_HEAT

		return mode

	def setMode(self, mode):
		self.mode = mode

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

	def updateState(self, nextState):
		if nextState.fanMode != self.currentState.fanMode:
			nextState.fanSetTime = datetime.now()
			self.logger.info("Setting fan mode to %s" % self.thermostat.constToString(nextState.fanMode))
			self.thermostat.setFanMode(nextState.fanMode)

			dispatcher.send(signal=ujouleLouieSignals.SIGNAL_FAN_ON_CHANGED,
							sender=self.updateState,
							value=True if nextState.fanMode == ujouleZWaveThermostat.FAN_MODE_ON else False)

		if nextState.systemMode != self.currentState.systemMode:
			nextState.systemSetTime = datetime.now()
			self.logger.info("Setting system mode to %s" % self.thermostat.constToString(nextState.systemMode))
			self.thermostat.setSystemMode(nextState.systemMode)

			dispatcher.send(signal=ujouleLouieSignals.SIGNAL_HEAT_ON_CHANGED,
							sender=self.updateState,
							value=True if nextState.systemMode == ujouleZWaveThermostat.SYS_MODE_HEAT else False)

		if nextState.heatSetpoint and nextState.heatSetpoint != self.currentState.heatSetpoint:
			self.logger.info("Setting thermostat heat setpoint to %0.2f" % nextState.heatSetpoint)
			self.thermostat.setHeatTarget(nextState.heatSetpoint)

		if nextState.coolSetpoint and nextState.coolSetpoint != self.currentState.coolSetpoint:
			self.logger.info("Setting thermostat cool setpoint to %0.2f" % nextState.coolSetpoint)
			self.thermostat.setCoolTarget(nextState.coolSetpoint)

		self.currentState = nextState

	def executePolicy(self, sender=None):
		# try to obtain the lock, if we cannot, someone else is already executing
		# the policy, so no sense in doing it again
		if not self.policyLock.acquire(False):
			return

		# if we are inside, try to cancel the timer, if possible
		if self.policyTimer:
			self.policyTimer.cancel()

		self.logger.info("entered executePolicy, caused by %s" % getObjectName(sender))

		if self.override:
			self.logger.info("override enabled, no policy execution will occur, exiting...")
		else:
			# find the current mode and time and apply the correct configuration
			mode = self.getMode()
			nowTime = datetime.now().time()
			config = self.getConfigByTime(mode, nowTime)
			if config:
				self.logger.info("applying config: %s" % config)
				self.applyConfig(config)

				# execute the configured policy
				policyInstance = self.getPolicyInstance(self.policy)
				nextState = policyInstance.execute()

				# use whatever is set in the nextState to configure the system
				self.updateState(nextState)

				# set up a timer to guarantee we rerun in 240s
				self.policyTimer = Timer(240.0, self.executePolicy, [Timer])
				self.policyTimer.start()
			else:
				self.logger.info("no config found, cannot do anything")

		self.logger.info("finished executePolicy")

		# drop the lock
		self.policyLock.release()

	def start(self):
		self.thermostat.setSystemMode(ujouleZWaveThermostat.SYS_MODE_OFF)
		self.thermostat.setFanMode(ujouleZWaveThermostat.FAN_MODE_AUTO)

		dispatcher.connect(self.executePolicy, ujouleLouieSignals.SIGNAL_TEMPERATURE_CHANGED)
		dispatcher.connect(self.executePolicy, ujouleLouieSignals.SIGNAL_SETPOINT_CHANGED)
		dispatcher.connect(self.executePolicy, ujouleLouieSignals.SIGNAL_AWAY_STATE_CHANGED)

		#self.loadConfig()

		self.dataCollector.start()
		self.broadcastParams()
		self.executePolicy(self.start)

	def stop(self):
		if self.policyTimer:
			self.policyTimer.cancel()
		if self.broadcastTimer:
			self.broadcastTimer.cancel()

		#self.saveConfig()

		self.thermostat.setSystemMode(ujouleZWaveThermostat.SYS_MODE_OFF)
		self.thermostat.setFanMode(ujouleZWaveThermostat.FAN_MODE_AUTO)

	def shell(self):
		self.shellImpl.cmdloop()


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
