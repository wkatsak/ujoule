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
from threading import Thread
from pyicloud import PyiCloudService
from structures import ZWaveThermostat

# based on http://www.pythonforbeginners.com/scraping/scraping-wunderground
class WeatherUndergroundTemperature(object):
	apiKey = "912fc499d4de6771"
	state = "NJ"
	city = "North_Brunswick"
	url = "http://api.wunderground.com/api/%s/conditions/q/%s/%s.json"

	def __init__(self):
		self.temperature = float("nan")
		t = Thread(target=self.checkThread)
		t.daemon = True
		t.start()
		self.logger = logging.getLogger("WeatherUndergroundTemperature")

	def getTemperature(self):
		return self.temperature

	def checkThread(self):
		while True:
			try:
				url = self.url % (self.apiKey, self.state, self.city)
				f = urllib2.urlopen(url)
				json_string = f.read()
				f.close()

				parsed_json = json.loads(json_string)
				temp_f = parsed_json["current_observation"]["temp_f"]
				self.temperature = temp_f

			except Exception as e:
				self.logger.error("Exception getting temperature from weather underground: %s" % str(e))
				self.temperature = float("nan")

			time.sleep(120)

class Policy(object):
	def __init__(self, controller):
		self.controller = controller
		self.logger = logging.getLogger("Policy")

	def execute(self):
		pass

class SubsumptionArchPolicy(Policy):

	class NextState(object):
		def __init__(self):
			self.systemMode = ujouleZWaveThermostat.SYS_MODE_OFF
			self.fanMode = ujouleZWaveThermostat.FAN_MODE_AUTO

	def __init__(self, controller):
		super(SubsumptionArchPolicy, self).__init__(controller)
		self.policies = []

	def execute(self):
		# most basic state, system off
		nextState = SubsumptionArchPolicy.NextState()

		# go through the policies, least priority first
		for policy in reversed(self.policies):
			self.policies[policy](nextState)

		# use whatever is left in the nextState to configure the system
		self.controller.setSystemMode(nextState.systemMode)
		self.controller.setFanMode(nextState.fanMode)

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
			temps.append(self.controller.sensors[sensor].getTemperature())

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

class BedtimePolicy(SimplePolicy):
	def execute(self):
		super(BedtimePolicy, self).execute()

	def getReferenceTemp(self):
		return self.controller.sensors["bedroom"].getTemperature()

class AwayDetector(object):
	def isAway(self):
		pass

class iCloudAwayDetector(AwayDetector):
	homeLat = 40.435311
	homeLong = -74.496817

	def __init__(self, username, password, threshold=3.0):
		#urllib3.disable_warnings()

		self.username = username
		self.password = password
		self.threshold = threshold
		
		self.initConnection()

		self.currentDistance = self.getDistance()
		t = Thread(target=self.checkThread)
		t.daemon = True
		t.start()

		self.logger = logging.getLogger("iCloudAwayDetector")

	def initConnection(self):
		self.api = PyiCloudService(self.username, self.password)
		self.iphone = None

		for device in self.api.devices:
			if device.data["deviceClass"] == "iPhone":
				self.iphone = device
				break

	# From: http://www.johndcook.com/blog/python_longitude_latitude/
	def distance_on_unit_sphere(self, lat1, long1, lat2, long2):
	    # Convert latitude and longitude to
	    # spherical coordinates in radians.
	    degrees_to_radians = math.pi/180.0

	    # phi = 90 - latitude
	    phi1 = (90.0 - lat1)*degrees_to_radians
	    phi2 = (90.0 - lat2)*degrees_to_radians

	    # theta = longitude
	    theta1 = long1*degrees_to_radians
	    theta2 = long2*degrees_to_radians

	    # Compute spherical distance from spherical coordinates.

	    # For two locations in spherical coordinates
	    # (1, theta, phi) and (1, theta', phi')
	    # cosine( arc length ) =
	    #    sin phi sin phi' cos(theta-theta') + cos phi cos phi'
	    # distance = rho * arc length

	    cos = (math.sin(phi1)*math.sin(phi2)*math.cos(theta1 - theta2) +
	           math.cos(phi1)*math.cos(phi2))
	    arc = math.acos( cos )

	    # Remember to multiply arc by the radius of the earth
	    # in your favorite set of units to get length.
	    return arc * 3959.0

	def checkThread(self):
		while True:
			try:
				self.currentDistance = self.getDistance()
			except Exception as e:
				self.logger.error("Exception getting distance: %s" % str(e))
				self.logger.info("Resetting connection...")
				self.initConnection()

			time.sleep(120)

	def getDistance(self):
		if not self.iphone:
			return -1.0

		location = self.iphone.location()
		distance = self.distance_on_unit_sphere(self.homeLat, self.homeLong, location["latitude"], location["longitude"])
		return distance

	def distance(self):
		return self.currentDistance

	def isAway(self):
		if self.currentDistance > self.threshold:
			return True
		else:
			return False

class ClimateControllerDataSource(object):
	pass

	
class ClimateController(object):
	# sensors is a dictionary by location
	def __init__(self, thermostat, sensors, outsideSensor, defaultPolicy=None, setpoint=74.0):
		self.thermostat = thermostat
		self.sensors = sensors
		self.outsideSensor = outsideSensor
		self.policies = {}
		if defaultPolicy == None:
			self.defaultPolicy = SimplePolicy(self)
		self.awayDetectors = {}
		self.setpoint = setpoint
		self.keepLooping = True

		self.logger = logging.getLogger("ClimateController")

	def shellCmd(self, cmd, args):
		print "cmd: %s, args=%s" % (cmd, str(args))

		if cmd == "status":
			readings = []
			for sensor in self.sensors:
				temp = self.sensors[sensor].getTemperature()
				if temp == None:
					temp = float("nan")
				else:
					readings.append(temp)
				print "Sensor (%s):\t%0.2f F" % (sensor, temp)

			print "Sensor Mean:\t\t%0.2f F" % numpy.mean(readings)
			print "Sensor StdDev:\t\t%0.2f F" % numpy.std(readings)

			print "Outside Sensor:\t\t%0.2f F" % self.outsideSensor.getTemperature()

			for name in self.awayDetectors:
				detector = self.awayDetectors[name]
				print "Away Detector (%s):\t%s (%0.2f mi)" % (name, "Away" if detector.isAway() else "Home", detector.distance())

			try:
				print "Setpoint:\t\t%0.2f F" % self.setpoint
				print "Fan Mode:\t\t%s" % self.thermostat.constToString(self.thermostat.getFanMode())
				print "Fan State:\t\t%s" % self.thermostat.constToString(self.thermostat.getFanState())
				print "System State:\t\t%s" % self.thermostat.constToString(self.thermostat.getSystemMode())
			except Exception as e:
				print "Exception printing", e

		elif cmd == "fan":
			if len(args) >= 1 and args[0] == "on":
				self.thermostat.setFanMode(ujouleZWaveThermostat.FAN_MODE_ON)
			elif len(args) >= 1 and args[0] == "auto":
				self.thermostat.setFanMode(ujouleZWaveThermostat.FAN_MODE_AUTO)
			else:
				print "invalid command for \"fan\""

		elif cmd == "setpoint":
			if len(args) >= 1:
				temp = float(args[0])
				self.setpoint = temp
			else:
				print "invalid command for \"setpoint\""

		elif cmd == "mode":
			if len(args) >= 1 and args[0] == "heat":
				self.thermostat.setSystemMode(ujouleZWaveThermostat.SYS_MODE_HEAT)
			elif len(args) >= 1 and args[0] == "off":
				self.thermostat.setSystemMode(ujouleZWaveThermostat.SYS_MODE_OFF)
			else:
				print "invalid command for \"mode\""

		elif cmd == "exit":
			self.stop()
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

	def addPolicy(self, policy, times=None):
		self.policies[times] = policy

	def addAwayDetector(self, name, detector):
		self.awayDetectors[name] = detector

	def away(self):
		for name in self.awayDetectors:
			detector = self.awayDetectors[name]
			if not detector.isAway():
				return False

		return True

	def loop(self):
		self.logger.info("Started main loop...")
		time.sleep(240)
		while self.keepLooping:
			nowTime = datetime.now().time()

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

			self.logger.info("using policy: %s" % str(policy))
			policy.execute()
			time.sleep(240)

	def start(self):
		t = Thread(target=self.loop)
		t.daemon = True
		t.start()

	def stop(self):
		self.keepLooping = False

if __name__ == "__main__":
	sensors = {"livingroom" : TemperatureSensor(None), "office" : TemperatureSensor(None), "bedroom" : TemperatureSensor(None)}
	controller = ClimateController(None, sensors)
	controller.shell()
