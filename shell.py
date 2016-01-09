#!/usr/bin/python

import math
import numpy
from zwave import ujouleZWaveThermostat

class ClimateControllerShell(object):

	def __init__(self, controller):
		self.controller = controller

	def shellCmd(self, cmd, args):
		print "cmd: %s, args=%s" % (cmd, str(args))

		if cmd == "status":
			readings = []
			for sensor in self.controller.sensors:
				temp = self.controller.sensors[sensor].getTemperature()
				if not math.isnan(temp):
					readings.append(temp)
				print "Sensor (%s):\t%0.2f F" % (sensor, temp)

			#print "Readings:\t\t", readings
			print "Sensor Mean:\t\t%0.2f F" % numpy.mean(readings)
			print "Sensor StdDev:\t\t%0.2f F" % numpy.std(readings)

			print "Outside Sensor:\t\t%0.2f F" % self.controller.outsideSensor.getTemperature()

			for name in self.controller.awayDetectors:
				detector = self.controller.awayDetectors[name]
				print "Away Detector (%s):\t%s (%0.2f mi)" % (name, "Away" if detector.isAway() else "Home", detector.distance())

			try:
				print "Setpoint:\t\t%0.2f F" % self.controller.getSetpoint()
				print "Fan Mode:\t\t%s" % self.controller.thermostat.constToString(self.controller.thermostat.getFanMode())
				print "Fan State:\t\t%s" % self.controller.thermostat.constToString(self.controller.thermostat.getFanState())
				print "System State:\t\t%s" % self.controller.thermostat.constToString(self.controller.thermostat.getSystemMode())
			except Exception as e:
				print "Exception printing", e

		elif cmd == "fan":
			if len(args) >= 1 and args[0] == "on":
				self.controller.thermostat.setFanMode(ujouleZWaveThermostat.FAN_MODE_ON)
			elif len(args) >= 1 and args[0] == "auto":
				self.controller.thermostat.setFanMode(ujouleZWaveThermostat.FAN_MODE_AUTO)
			else:
				print "invalid command for \"fan\""

		elif cmd == "setpoint":
			if len(args) >= 1:
				temp = float(args[0])
				self.controller.setSetpoint(temp)

			else:
				print "invalid command for \"setpoint\""

		elif cmd == "mode":
			if len(args) >= 1 and args[0] == "heat":
				self.controller.thermostat.setSystemMode(ujouleZWaveThermostat.SYS_MODE_HEAT)
			elif len(args) >= 1 and args[0] == "off":
				self.controller.thermostat.setSystemMode(ujouleZWaveThermostat.SYS_MODE_OFF)
			else:
				print "invalid command for \"mode\""

		elif cmd == "exit":
			self.controller.stop()
			print "Goodbye!"
			return False

		else:
			print "No command given..."
		
		return True

	def shell(self):
		print "uJoule Climate Controller Shell"
		keepGoing = True
		prevCmd = None
		prevArgs = None

		while keepGoing:
			try:
				cmdLine = raw_input("> ")
				if len(cmdLine) == 0 and prevCmd:
					keepGoing = self.shellCmd(prevCmd, prevArgs)
					continue

				fields = cmdLine.split(" ")
				cmd = fields[0]
				args = []
				if len(fields) >= 2:
					for i in xrange(1, len(fields)):
						args.append(fields[i])

				keepGoing = self.shellCmd(cmd, args)
				prevCmd = cmd
				prevArgs = args

			except Exception as e:
				print "Exception", e