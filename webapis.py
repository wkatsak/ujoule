#!/usr/bin/python

import logging
import sys
import time
import math
import urllib2
import json
from threading import Thread
from pyicloud import PyiCloudService
from common import AwayDetector, ujouleLouieSignals, getLogger
from louie import dispatcher

# based on http://www.pythonforbeginners.com/scraping/scraping-wunderground
class WeatherUndergroundService(object):
	apiKey = "912fc499d4de6771"
	state = "NJ"
	city = "North_Brunswick"
	url = "http://api.wunderground.com/api/%s/conditions/q/%s/%s.json"

	def __init__(self, updateInterval=240):
		self.updateInterval = updateInterval
		self.temperature = float("nan")
		self.relativeHumidity = float("nan")
		self.prevTemperature = None
		self.prevRelativeHumidity = None

		t = Thread(target=self.checkThread)
		t.daemon = True
		t.start()
		self.logger = getLogger(self)

	def getTemperature(self):
		return self.temperature

	def getRelativeHumidity(self):
		return self.relativeHumidity

	def checkThread(self):
		while True:
			try:
				url = self.url % (self.apiKey, self.state, self.city)
				f = urllib2.urlopen(url)
				json_string = f.read()
				f.close()

				parsed_json = json.loads(json_string)
				temp_f = parsed_json["current_observation"]["temp_f"]
				relative_humidity = float(parsed_json["current_observation"]["relative_humidity"].replace("%", "").strip())
				self.temperature = temp_f
				self.relativeHumidity = relative_humidity

				if temp_f != self.prevTemperature:
					self.prevTemperature = temp_f
					dispatcher.send(signal=ujouleLouieSignals.SIGNAL_OUTSIDE_TEMPERATURE_CHANGED, sender=self, value=temp_f)

				dispatcher.send(signal=ujouleLouieSignals.SIGNAL_OUTSIDE_TEMPERATURE_UPDATED, sender=self, value=temp_f)

				if relative_humidity != self.prevRelativeHumidity:
					self.prevRelativeHumidity = relative_humidity
					dispatcher.send(signal=ujouleLouieSignals.SIGNAL_OUTSIDE_RELATIVE_HUMIDITY_CHANGED, sender=self, value=relative_humidity)

				dispatcher.send(signal=ujouleLouieSignals.SIGNAL_OUTSIDE_RELATIVE_HUMIDITY_UPDATED, sender=self, value=relative_humidity)

			except Exception as e:
				self.logger.error("Exception getting data from weather underground: %s" % str(e))
				self.temperature = float("nan")
				self.relativeHumidity = float("nan")

			time.sleep(self.updateInterval)

class iCloudAwayDetector(AwayDetector):
	homeLat = 40.435311
	homeLong = -74.496817

	def __init__(self, username, password, threshold=5.0, updateInterval=120):
		#urllib3.disable_warnings()

		self.username = username
		self.password = password
		self.threshold = threshold
		self.updateInterval = updateInterval
		
		self.initConnection()

		self.currentDistance = 0.0
		self.prevState = None

		t = Thread(target=self.checkThread)
		t.daemon = True
		t.start()

		self.logger = getLogger(self)

	def initConnection(self):
		while True:
			try:
				self.api = PyiCloudService(self.username, self.password)
				self.iphone = None

				for device in self.api.devices:
					if device.data["deviceClass"] == "iPhone":
						self.iphone = device
						break
				return
			except Exception as e:
				self.logger.info("Error initing connection: %s" % e)
				time.sleep(60)

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

			away = self.isAway()
			if away != self.prevState:
				dispatcher.send(signal=ujouleLouieSignals.SIGNAL_AWAY_STATE_CHANGED, sender=self, value=away)

			self.prevState = away
			dispatcher.send(signal=ujouleLouieSignals.SIGNAL_AWAY_STATE_UPDATED, sender=self, value=away)

			time.sleep(self.updateInterval)

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
