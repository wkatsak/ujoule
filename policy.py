#!/usr/bin/python

from datetime import datetime
from datetime import timedelta
from louie import dispatcher
from common import ujouleLouieSignals, Policy
from climate import ClimateControllerState
from zwave import ujouleZWaveThermostat

class SubsumptionArchPolicy(Policy):

	def __init__(self, controller):
		super(SubsumptionArchPolicy, self).__init__(controller)
		self.policies = []

	def execute(self):
		currentState = self.controller.getCurrentState()
		nextState = ClimateControllerState(currentState)

		# go through the policies, least priority first
		for policy in self.policies:
			policy(currentState, nextState)

		# return the nextState object to the caller
		return nextState

class BasicSubsumptionArchPolicy(SubsumptionArchPolicy):

	def __init__(self, controller):
		super(BasicSubsumptionArchPolicy, self).__init__(controller)
		self.policies =	[
			self.heatOn,
			self.heatOff,
			#self.somewhereHighByTwo,
			#self.somewhereLowByThree,
			self.heatOffInterval,
			self.heatOnInterval,
			self.fanAfterHeat,
			self.fanCirculate,
			self.fanOff,
			self.away
		]

	def getReferenceTemp(self):
		return self.controller.tempMean()

	def execute(self):
		self.logger.info("using referenceTemp=%0.1f" % self.getReferenceTemp())
		return super(BasicSubsumptionArchPolicy, self).execute()

	def heatOn(self, currentState, nextState):
		if self.getReferenceTemp() <= self.controller.getSetpoint() - 1.0 and currentState.systemMode == ujouleZWaveThermostat.SYS_MODE_OFF:
			self.logger.info("heatOn tripped")
			nextState.systemMode = ujouleZWaveThermostat.SYS_MODE_HEAT
			nextState.fanMode = ujouleZWaveThermostat.FAN_MODE_AUTO
			nextState.heatSetpoint = 80.0

	def heatOff(self, currentState, nextState):
		if self.getReferenceTemp() >= self.controller.getSetpoint() and currentState.systemMode == ujouleZWaveThermostat.SYS_MODE_HEAT:
			self.logger.info("heatOff tripped")
			nextState.systemMode = ujouleZWaveThermostat.SYS_MODE_OFF

	def somewhereHighByTwo(self, currentState, nextState):
		if self.controller.tempMax() >= self.controller.getSetpoint() + 2.0 and currentState.systemMode == ujouleZWaveThermostat.SYS_MODE_HEAT:
			self.logger.info("somewhereHighByTwo tripped")
			nextState.systemMode = ujouleZWaveThermostat.SYS_MODE_OFF

	def somewhereLowByThree(self, currentState, nextState):
		if self.controller.tempMin() < self.controller.getSetpoint() - 3.0 and currentState.systemMode == ujouleZWaveThermostat.SYS_MODE_OFF:
			self.logger.info("somewhereLowByThree tripped")
			nextState.systemMode = ujouleZWaveThermostat.SYS_MODE_HEAT
			nextState.fanMode = ujouleZWaveThermostat.FAN_MODE_AUTO
			nextState.heatSetpoint = 80.0

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

class SubsumptionArchDaytimePolicy(BasicSubsumptionArchPolicy):
	def __init__(self, controller):
		super(SubsumptionArchDaytimePolicy, self).__init__(controller)

	def getReferenceTemp(self):
		return self.controller.tempMean(locations=["livingroom"])

class SubsumptionArchBedtimePolicy(BasicSubsumptionArchPolicy):
	def __init__(self, controller):
		super(SubsumptionArchBedtimePolicy, self).__init__(controller)

		self.policies =	[
			self.heatOn,
			self.heatOff,
			self.heatOffInterval,
			self.heatOnInterval,
			self.fanAfterHeat,
			self.fanCirculate,
			self.fanOff,
			self.away
		]

	def getReferenceTemp(self):
		return self.controller.tempMean(locations=["bedroom"])
