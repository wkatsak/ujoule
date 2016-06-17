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

class SubsumptionArchBasicPolicy(SubsumptionArchPolicy):
	def __init__(self, controller):
		super(SubsumptionArchBasicPolicy, self).__init__(controller)
		self.minOffInterval = 4
		self.minOnInterval = 4
		self.minFanTime = 4
		self.allowedMaxDelta = 3

	def getReferenceTemp(self):
		return self.controller.tempMean()

	def execute(self):
		self.logger.info("using referenceTemp=%0.1f" % self.getReferenceTemp())
		return super(SubsumptionArchBasicPolicy, self).execute()

	def systemOffInterval(self, currentState, nextState):
		if (nextState.systemMode == ujouleZWaveThermostat.SYS_MODE_HEAT or nextState.systemMode == ujouleZWaveThermostat.SYS_MODE_COOL) \
				and currentState.systemMode == ujouleZWaveThermostat.SYS_MODE_OFF:
			if currentState.systemSetTime and datetime.now() - currentState.systemSetTime < timedelta(minutes=self.minOffInterval):
				self.logger.info("systemOffInterval tripped")
				nextState.systemMode = ujouleZWaveThermostat.SYS_MODE_OFF

	def systemOnInterval(self, currentState, nextState):
		if nextState.systemMode == ujouleZWaveThermostat.SYS_MODE_OFF \
				and (currentState.systemMode == ujouleZWaveThermostat.SYS_MODE_HEAT or currentState.systemMode == ujouleZWaveThermostat.SYS_MODE_COOL):
			if currentState.systemSetTime and datetime.now() - currentState.systemSetTime < timedelta(minutes=self.minOnInterval):
				self.logger.info("systemOnInterval tripped")
				nextState.systemMode = currentState.systemMode

	def fanAfterSystem(self, currentState, nextState):
		if nextState.systemMode == ujouleZWaveThermostat.SYS_MODE_OFF \
				and (currentState.systemMode == ujouleZWaveThermostat.SYS_MODE_HEAT or currentState.systemMode == ujouleZWaveThermostat.SYS_MODE_COOL):
			self.logger.info("fanAfterSystem tripped")
			nextState.fanMode = ujouleZWaveThermostat.FAN_MODE_ON

	def fanCirculate(self, currentState, nextState):
		if nextState.systemMode == ujouleZWaveThermostat.SYS_MODE_OFF and nextState.fanMode == ujouleZWaveThermostat.FAN_MODE_AUTO:
			if self.controller.tempMaxDelta() > self.allowedMaxDelta:
				self.logger.info("fanCirculate tripped")
				nextState.fanMode = ujouleZWaveThermostat.FAN_MODE_ON

	def fanOff(self, currentState, nextState):
		if nextState.systemMode == ujouleZWaveThermostat.SYS_MODE_OFF and nextState.fanMode == ujouleZWaveThermostat.FAN_MODE_ON:
			if self.controller.tempMaxDelta() <= self.allowedMaxDelta and currentState.fanSetTime and datetime.now() - currentState.fanSetTime >= timedelta(minutes=self.minFanTime):
				self.logger.info("fanOff tripped")
				nextState.fanMode = ujouleZWaveThermostat.FAN_MODE_AUTO

	def away(self, currentState, nextState):
		if self.controller.away() and self.controller.tempMin() > 60.0 and self.controller.tempMax() < 78.0:
			self.logger.info("away tripped")
			nextState.systemMode = ujouleZWaveThermostat.SYS_MODE_OFF
			nextState.fanMode = ujouleZWaveThermostat.FAN_MODE_AUTO

class CoolingPolicy(SubsumptionArchBasicPolicy):

	def __init__(self, controller):
		super(CoolingPolicy, self).__init__(controller)

		self.policies =	[
			self.coolOn,
			self.coolOff,
			self.systemOffInterval,
			self.systemOnInterval,
			self.fanAfterSystem,
			#self.fanCirculate,
			self.fanOff,
			self.away
		]

	def coolOn(self, currentState, nextState):
		if self.getReferenceTemp() >= self.controller.getSetpoint() + 1.0 and currentState.systemMode == ujouleZWaveThermostat.SYS_MODE_OFF:
			self.logger.info("coolOn tripped")
			nextState.systemMode = ujouleZWaveThermostat.SYS_MODE_COOL
			nextState.fanMode = ujouleZWaveThermostat.FAN_MODE_AUTO
			nextState.coolSetpoint = 68.0

	def coolOff(self, currentState, nextState):
		if self.getReferenceTemp() <= self.controller.getSetpoint() and currentState.systemMode == ujouleZWaveThermostat.SYS_MODE_COOL:
			self.logger.info("coolOff tripped")
			nextState.systemMode = ujouleZWaveThermostat.SYS_MODE_OFF


class HeatingPolicy(SubsumptionArchBasicPolicy):

	def __init__(self, controller):
		super(HeatingPolicy, self).__init__(controller)

		self.policies =	[
			self.heatOn,
			self.heatOff,
			self.systemOffInterval,
			self.systemOnInterval,
			self.fanAfterSystem,
			#self.fanCirculate,
			self.fanOff,
			self.away
		]

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

class CoolingDaytimePolicy(CoolingPolicy):
	def __init__(self, controller):
		super(CoolingDaytimePolicy, self).__init__(controller)

	def getReferenceTemp(self):
		return self.controller.tempMean(locations=["livingroom"])

class CoolingBedtimePolicy(CoolingPolicy):
	def __init__(self, controller):
		super(CoolingBedtimePolicy, self).__init__(controller)

	def getReferenceTemp(self):
		return self.controller.tempMean(locations=["bedroom"])

class HeatingDaytimePolicy(HeatingPolicy):
	def __init__(self, controller):
		super(HeatingDaytimePolicy, self).__init__(controller)

	def getReferenceTemp(self):
		return self.controller.tempMean(locations=["livingroom"])

class HeatingBedtimePolicy(HeatingPolicy):
	def __init__(self, controller):
		super(HeatingBedtimePolicy, self).__init__(controller)

	def getReferenceTemp(self):
		return self.controller.tempMean(locations=["bedroom"])
