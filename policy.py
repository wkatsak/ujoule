#!/usr/bin/python

from datetime import datetime
from datetime import timedelta
from louie import dispatcher
from common import ujouleLouieSignals, Policy
from zwave import ujouleZWaveThermostat

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