#!/usr/bin/python

import logging
import sys
import time
import math
import numpy
import urllib2
import json
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

class SimplePolicy(Policy):
	awayThreshold = 60.0

	def __init__(self, controller):
		super(SimplePolicy, self).__init__(controller)

		self.wasHeating = False
		self.wasFanOn = False
		self.extraFanCycles = 0

	def getReferenceTemp(self):
		temps = []
		for sensor in self.controller.sensors:
			temp = self.controller.sensors[sensor].getTemperature()
			if not math.isnan(temp):
				temps.append(temp)

		mean = numpy.mean(temps)
		return mean

	def execute(self):
		referenceTemp = self.getReferenceTemp()
		self.logger.info("policy: reference temp is %0.2f" % referenceTemp)

		if not self.controller.away():
			threshold = self.controller.setpoint - 1.0
		else:
			self.logger.info("policy: everyone away, set threshold to %0.2f F" % self.awayThreshold)
			threshold = awayThreshold

		if referenceTemp <= threshold and not self.wasHeating:
			self.logger.info("policy: need heat")
			self.controller.thermostat.setSystemMode(ujouleZWaveThermostat.SYS_MODE_HEAT)
			self.controller.thermostat.setFanMode(ujouleZWaveThermostat.FAN_MODE_ON)
			self.wasHeating = True
			self.wasFanOn = True

		elif referenceTemp > threshold and self.wasHeating:
			self.logger.info("policy: hit target, heat off")
			self.controller.thermostat.setSystemMode(ujouleZWaveThermostat.SYS_MODE_OFF)
			self.wasHeating = False
			self.extraFanCycles = 3

		elif referenceTemp > threshold and self.wasFanOn:
			self.extraFanCycles -= 1
			self.logger.info("policy: extra fan minus one (extraFanCycles=%d)" % self.extraFanCycles)
			if self.extraFanCycles == 0:
				self.logger.info("policy: extra fan off")
				self.controller.thermostat.setFanMode(ujouleZWaveThermostat.FAN_MODE_AUTO)
				self.wasFanOn = False
		else:
			self.logger.info("policy: noop")

class SimpleBedtimePolicy(SimplePolicy):
	def execute(self):
		super(BedtimePolicy, self).execute()

	def getReferenceTemp(self):
		return self.controller.sensors["bedroom"].getTemperature()

class SubsumptionArchPolicy(Policy):

	class State(object):
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

	def __init__(self, controller):
		super(SubsumptionArchPolicy, self).__init__(controller)
		self.policies = []
		self.currentState = SubsumptionArchPolicy.State()

	def execute(self):
		# most basic state, system off
		nextState = SubsumptionArchPolicy.State(self.currentState)

		# go through the policies, least priority first
		for policy in self.policies:
			policy(self.currentState, nextState)

		# use whatever is left in the nextState to configure the system
		if nextState.systemMode != self.currentState.systemMode:
			nextState.systemSetTime = datetime.now()
			self.logger.info("Setting system mode to %s" % self.controller.thermostat.constToString(nextState.systemMode))
			self.controller.thermostat.setSystemMode(nextState.systemMode)

		if nextState.fanMode != self.currentState.fanMode:
			nextState.fanSetTime = datetime.now()
			self.logger.info("Setting fan mode to %s" % self.controller.thermostat.constToString(nextState.fanMode))
			self.controller.thermostat.setFanMode(nextState.fanMode)

		self.currentState = nextState

class BasicSubsumptionArchPolicy(SubsumptionArchPolicy):

	def __init__(self, controller):
		super(BasicSubsumptionArchPolicy, self).__init__(controller)
		self.policies =	[
				self.tempLow,
				self.tempHigh,
				self.somewhereHighByTwo,
				self.somewhereLowByThree,
				self.heatOffInterval,
				self.heatOnInterval,
				self.fanAfterHeat,
				self.fanCirculate,
				self.fanOff,
				self.away
		]

	def tempLow(self, currentState, nextState):
		if self.controller.tempMean() < self.controller.getSetpoint() - 0.5:
			self.logger.info("tempLow tripped")
			nextState.systemMode = ujouleZWaveThermostat.SYS_MODE_HEAT
			nextState.fanMode = ujouleZWaveThermostat.FAN_MODE_AUTO

	def tempHigh(self, currentState, nextState):
		if self.controller.tempMean() >= self.controller.getSetpoint():
			self.logger.info("tempHigh tripped")
			nextState.systemMode = ujouleZWaveThermostat.SYS_MODE_OFF

	def somewhereHighByTwo(self, currentState, nextState):
		if self.controller.tempMax() >= self.controller.getSetpoint() + 2.0:
			self.logger.info("somewhereHighByTwo tripped")
			nextState.systemMode = ujouleZWaveThermostat.SYS_MODE_OFF

	def somewhereLowByThree(self, currentState, nextState):
		if self.controller.tempMin() < self.controller.getSetpoint() - 3.0:
			self.logger.info("somewhereLowByThree tripped")
			nextState.systemMode = ujouleZWaveThermostat.SYS_MODE_HEAT
			nextState.fanMode = ujouleZWaveThermostat.FAN_MODE_AUTO

	def heatOffInterval(self, currentState, nextState):
		if nextState.systemMode == ujouleZWaveThermostat.SYS_MODE_HEAT and currentState.systemMode == ujouleZWaveThermostat.SYS_MODE_OFF:
			if currentState.systemSetTime and datetime.now() - currentState.systemSetTime < timedelta(minutes=4):
				self.logger.info("heatOffInterval tripped")
				nextState.systemMode = ujouleZWaveThermostat.SYS_MODE_OFF

	def heatOnInterval(self, currentState, nextState):
		if nextState.systemMode == ujouleZWaveThermostat.SYS_MODE_OFF and currentState.systemMode == ujouleZWaveThermostat.SYS_MODE_HEAT:
			if currentState.systemSetTime and datetime.now() - currentState.systemSetTime < timedelta(minutes=4):
				self.logger.info("heatOnInterval tripped")
				nextState.systemMode = ujouleZWaveThermostat.SYS_MODE_HEAT

	def fanAfterHeat(self, currentState, nextState):
		if nextState.systemMode == ujouleZWaveThermostat.SYS_MODE_OFF and currentState.systemMode == ujouleZWaveThermostat.SYS_MODE_HEAT:
			self.logger.info("fanAfterHeat tripped")
			nextState.fanMode = ujouleZWaveThermostat.FAN_MODE_ON

	def fanCirculate(self, currentState, nextState):
		if nextState.systemMode == ujouleZWaveThermostat.SYS_MODE_OFF and nextState.fanMode == ujouleZWaveThermostat.FAN_MODE_AUTO:
			if self.controller.tempStdDev() > 2.0:
				self.logger.info("fanCirculate tripped")
				nextState.fanMode = ujouleZWaveThermostat.FAN_MODE_ON

	def fanOff(self, currentState, nextState):
		if nextState.systemMode == ujouleZWaveThermostat.SYS_MODE_OFF and nextState.fanMode == ujouleZWaveThermostat.FAN_MODE_ON:
			if self.controller.tempStdDev() <= 2.0 and currentState.fanSetTime and datetime.now() - currentState.fanSetTime >= timedelta(minutes=4):
				self.logger.info("fanOff tripped")
				nextState.fanMode = ujouleZWaveThermostat.FAN_MODE_AUTO

	def away(self, currentState, nextState):
		if self.controller.away() and self.controller.tempMin() > 60.0:
			self.logger.info("away tripped")
			nextState.systemMode = ujouleZWaveThermostat.SYS_MODE_OFF
			nextState.fanMode = ujouleZWaveThermostat.FAN_MODE_AUTO

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