#!/usr/bin/python

import cmd
import math
import numpy
import climate
import zwave
from datetime import time

class ClimateControllerShell(cmd.Cmd):

	def __init__(self, controller):
		cmd.Cmd.__init__(self)
		self.controller = controller
		self.intro = "uJoule Climate Control System Shell\n"
		self.intro += "Copyright (C) 2015, 2016 William Katsak\n"
		self.prompt = "ujoule> "

	def tokens(self, args):
		return args.strip().split()

	def error(self, msg):
		print "error: %s" % msg
		return False

	def do_status(self, args):
		try:
			readings = []
			for sensor in self.controller.sensors:
				temp = self.controller.sensors[sensor].getTemperature()

				if not math.isnan(temp):
					readings.append(temp)
				print "Sensor Temp   (%s):\t%0.2f F" % (sensor, temp)

				if isinstance(self.controller.sensors[sensor], zwave.ujouleZWaveMultisensor):
					relativeHumidity = self.controller.sensors[sensor].getRelativeHumidity()
					print "Sensor RelHum (%s):\t%0.2f %%" % (sensor, relativeHumidity)

			print "Sensor Temp Mean:\t\t%0.2f F" % numpy.mean(readings)
			print "Sensor Temp StdDev:\t\t%0.2f F" % numpy.std(readings)

			print "Outside Sensor Temp:\t\t%0.2f F" % self.controller.outsideSensor.getTemperature()
			print "Outside Sensor RelHum:\t\t%0.2f %%" % self.controller.outsideSensor.getRelativeHumidity()

			for name in self.controller.awayDetectors:
				detector = self.controller.awayDetectors[name]
				print "Away Detector (%s):\t%s (%0.2f mi)" % (name, "Away" if detector.isAway() else "Home", detector.distance())

			print "Setpoint:\t\t%0.2f F" % self.controller.getSetpoint()
			print "Fan Mode:\t\t%s" % self.controller.thermostat.constToString(self.controller.thermostat.getFanMode())
			print "Fan State:\t\t%s" % self.controller.thermostat.constToString(self.controller.thermostat.getFanState())
			print "System State:\t\t%s" % self.controller.thermostat.constToString(self.controller.thermostat.getSystemMode())
			print "Override:\t\t%s" % ("On" if self.controller.override else "Off")
			print "System Mode:\t\t%s" % self.controller.getMode()

		except Exception as e:
			#print "Exception printing", e
			print "Exception getting status:", e

		return False

	def do_exit(self, args):
		self.controller.stop()
		print "Goodbye!"
		return True

	def do_override(self, args):
		tokens = self.tokens(args)
		if len(tokens) == 0:
			print "override status: %s" % ("on" if self.controller.override else "off")
			return False

		if tokens[0] == "on":
			self.controller.overrideEnable()
			print "override enable"
			return False
		elif tokens[0] == "off":
			self.controller.overrideDisable()
			print "override disabled"
			return False

		if not self.controller.override:
			return self.error("override not enabled, only \"override on\" supported.")

		currentState = self.controller.getCurrentState()
		nextState = climate.ClimateControllerState(currentState)

		if tokens[0] == "fan":
			if len(tokens) >= 2 and tokens[1] == "on":
				nextState.fanMode = zwave.ujouleZWaveThermostat.FAN_MODE_ON

			elif len(tokens) >= 2 and tokens[1] == "auto":
				nextState.fanMode = zwave.ujouleZWaveThermostat.FAN_MODE_AUTO
			else:
				return self.error("invalid command for \"fan\"")

		elif tokens[0] == "setpoint":
			if len(tokens) >= 2:
				temp = float(tokens[1])
				self.controller.setSetpoint(temp)
				nextState.heatSetpoint = temp
			else:
				return self.error("invalid command for \"setpoint\"")

		elif tokens[0] == "mode":
			if len(tokens) >= 2 and tokens[1] == "heat":
				nextState.systemMode = zwave.ujouleZWaveThermostat.SYS_MODE_HEAT
			elif len(tokens) >= 2 and tokens[1] == "cool":
				nextState.systemMode = zwave.ujouleZWaveThermostat.SYS_MODE_COOL
			elif len(args) >= 2 and tokens[1] == "off":
				nextState.systemMode = zwave.ujouleZWaveThermostat.SYS_MODE_OFF
			else:
				return self.error("invalid command for \"mode\"")

		self.controller.updateState(nextState)

	def do_schedule(self, args):
		tokens = self.tokens(args)

		if len(tokens) == 0:
			return self.error("argument required")

		if tokens[0] == "list":
			for mode in [climate.ClimateController.MODE_HEAT, climate.ClimateController.MODE_COOL]:
				configs = self.controller.getScheduledConfigs(mode)
				configTimes = self.controller.getScheduledConfigTimes(mode)
				#print configs
			#	print configTimes
				print "\nMode: %s" % mode
				print "Index\tPolicy\t\t\tSetpoint\tStart\t\tEnd"
				print "--------------------------------------------------------------------------------------"
				print "default\t%s\t%0.2f\t\t---\t\t---" % (self.controller.defaultConfigs[mode].policy.__name__, self.controller.defaultConfigs[mode].setpoint)
				for i in xrange(0, len(configs)):
					config = configs[i]
					startTime, endTime = configTimes[config]
					print "%d\t%s\t%0.2f\t\t%s\t\t%s" % (i, config.policy.__name__, config.setpoint, startTime.strftime("%H:%M"), endTime.strftime("%H:%M"))

		elif tokens[0] == "add":
			if len(tokens) >= 5:
				policyClassName = tokens[1]
				setpointString = tokens[2]
				startTimeString = tokens[3]
				endTimeString = tokens[4]

				__import__("policy", fromlist=[policyClassName])

				policy = eval(policyClassName)
				setpoint = int(setpointString)
				startTime = time.strptime(startTimeString, "%H:%M")
				endTime = time.strptime(endTimeString, "%H:%M")

		elif tokens[0] == "remove":
			if len(tokens) >= 2:
				index = int(tokens[1])
				self.controller.removeScheduledConfig(index)
			else:
				return self.error("usage: remove [index]")

		elif tokens[0] == "setpoint":
			if len(tokens) >= 4:
				modeStr = tokens[1]
				index = tokens[2]
				try:
					temp = float(tokens[3])
				except:
					self.error("invalid temperature")
			else:
				return self.error("usage: setpoint [mode] [index] [temperature]")

			if modeStr == "cool":
				mode = climate.ClimateController.MODE_COOL
			elif modeStr == "heat":
				mode = climate.ClimateController.MODE_HEAT
			else:
				return self.error("mode must be one of cool, heat")

			if index == "default":
				self.controller.defaultConfigs[mode].setpoint = temp
				self.controller.executePolicy()
			else:
				try:
					index = int(index)
					if index >= len(self.controller.getScheduledConfigs(mode)):
						raise Exception()
				except:
					return self.error("invalid index")

				self.controller.scheduledConfigs[mode][index].setpoint = temp
				self.controller.executePolicy()

		return False

	def do_defaultpolicy(self, args):
		pass

	def do_mode(self, args):
		tokens = self.tokens(args)

		if tokens[0] == "cool":
			self.controller.setMode(climate.ClimateController.MODE_COOL)
			print "Mode set to cool"
		elif tokens[0] == "heat":
			self.controller.setMode(climate.ClimateController.MODE_HEAT)
			print "Mode set to heat"
		elif tokens[0] == "auto":
			self.controller.setMode(climate.ClimateController.MODE_AUTO)
			print "Mode set to auto"
		else:
			return self.error("invalid mode, options are cool, heat, auto")

	def do_ipython(self, args):
		from IPython import embed
		embed()
