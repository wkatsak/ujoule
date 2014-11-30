#!/usr/bin/python

import logging
from helpers import unix_ts
from threading import Lock
from datetime import datetime, timedelta

class ZWaveDataSource(object):
	
	def __init__(self, nodeId, description):
		self.nodeId = nodeId
		self.description = description
	
	def getNodeId(self):
		return self.nodeId
	
	def getDescription(self):
		return self.description
	
	def start(self, network):
		pass
	
	# value will be a ZWaveValue object
	def valueUpdate(self, value):
		pass

class Multisensor(ZWaveDataSource):
	def __init__(self, nodeId, description=None, tempCorrection=3.0):
		super(Multisensor, self).__init__(nodeId, description)
		
		self.logger = logging.getLogger("Multisensor-%d" % nodeId)
		self.tempCorrection = tempCorrection
		self.battery = float("NaN")
		self.temperature = float("NaN")
		self.humdity = float("NaN")
		self.luminance = float("NaN")
		self.motion = False
		
		#self.outfile = open("multisensor.out", "w")

	def start(self, network):
		self.network = network
		
	def valueUpdate(self, value):
		if value.label == "Battery":
			self.logger.info("Received update for Battery: %0.2f" % value.data)
			self.setBattery(value.data)
			return True
		elif value.label == "Temperature":
			self.logger.info("Received update for Temperature: %0.2f" % value.data)
			self.setTemperature(value.data)
			return True
		elif value.label == "Humidity":
			self.logger.info("Received update for Humidity: %0.2f" % value.data)
			self.setHumidity(value.data)
			return True
		elif value.label == "Luminance":
			self.logger.info("Received update for Luminance: %0.2f" % value.data)
			self.setLuminance(value.data)
			return True
		elif value.label == "Motion":
			self.logger.info("Received update for Motion: %s" % str(value.data))
			self.setMotion(value.data)
			return True
		else:
			return False
		
	def getBattery(self):
		return self.battery
	
	def getTemperature(self):
		return self.temperature
	
	def getHumidity(self):
		return self.humdity
	
	def getLuminance(self):
		return self.luminance
	
	def getMotion(self):
		return self.motion

	def setBattery(self, value):
		self.battery = value
	
	# we know the temperature on this sensor is weird, so we need to correct
	# otherwise, use raw value rounded to tenth place
	def setTemperature(self, value):
		corrected = value + self.tempCorrection
		#self.temperature = round(corrected * 2.0)/2.0
		self.temperature = round(corrected, 1)
		#now = datetime.now()
		#string = "%d %0.2f %0.2f\n" % (unix_ts(now), self.temperature, value)
		#print now, self.temperature, value, "multisensor"
		#self.outfile.write(string)
		#self.outfile.flush()
	
	def setHumidity(self, value):
		self.humidity = value
	
	def setLuminance(self, value):
		self.luminance = value
	
	def setMotion(self, value):
		self.motion = value

class Thermostat(ZWaveDataSource):
	def __init__(self, nodeId, description=None):
		super(Thermostat, self).__init__(nodeId, description)

		self.logger = logging.getLogger("Thermostat-%d" % nodeId)
		#self.outfile = open("thermostat.out", "w")
	
	def start(self, network):
		self.network = network
	
	def valueUpdate(self, value):
		if value.label == "Temperature":
			self.setTemperature(value.data)
			self.logger.info("Received update for Temperature: %0.2f" % value.data)
			return True
		else:
			return False
		
	def getTemperature(self):
		return self.temperature
	
	def setTemperature(self, value):
		self.temperature = value
			
		#now = datetime.now()
		#string = "%d %0.2f\n" % (unix_ts(now), self.temperature)
		#print now, self.temperature, "thermostat"
			
		#self.outfile.write(string)
		#self.outfile.flush()