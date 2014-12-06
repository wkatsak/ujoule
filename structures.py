#!/usr/bin/python

import logging
import openzwave

from helpers import unix_ts
from threading import Lock
from datetime import datetime, timedelta
from openzwave.node import ZWaveNode
from openzwave.value import ZWaveValue

class ujouleZWaveNode(object):
	
	def __init__(self, nodeId, description=None):
		self.nodeId = nodeId
		self.description = description
		
		self.isActivated = False
		self.logger = logging.getLogger("node-%d" % nodeId)
		self.transforms = {} # indexed by Id
		self.updateTimes = {} # indexed by Id
		self.zwaveValuesById = {}
		self.zwaveValuesByLabel = {}
			
	# methods should call this to ensure activation
	def checkActivation(self):
		if not self.isActivated:
			raise Exception("Node %d is not yet activated..." % self.nodeId)
	
	def valueException(self, label, value_id, message):
		raise Exception("Value (label=%s, value_id=%s): %s" % (str(label), str(value_id), message))
	
	# controller will call this when registered
	def activate(self, zwaveNetwork, zwaveNode):
		self.logger.info("activated")
		
		self.zwaveNode = zwaveNode
		for value_id in zwaveNode.get_values():
			value = ZWaveValue(value_id, zwaveNetwork, zwaveNode)
			self.zwaveValuesById[value_id] = value
			self.zwaveValuesByLabel[value.label] = value
			self.logger.info("value: %s" % value)
		
		self.activated()
		
		self.isActivated = True
	
	# called when activated. subclasses can use to register overrides
	# or set up polling, etc.
	def activated(self):
		pass
	
	def valueUpdate(self, zwaveValue):
		self.logger.info("received update: value_id %s, label %s, raw data %s, transformed data: %s" % (zwaveValue.value_id, zwaveValue.label, zwaveValue.data, self.getData(value_id=zwaveValue.value_id)))
		self.updateTimes[zwaveValue.value_id] = datetime.now()
		
	def getOrValidateValueId(self, label=None, value_id=None):
		if label == None and value_id == None:
			self.valueException(label, value_id, "Need to specify either label or id")
		
		if label != None:
			try:
				zwaveValue = self.zwaveValuesByLabel[label]
			except KeyError:
				self.valueException(label, value_id, "Invalid label")
			
			value_id = zwaveValue.value_id
		
		
		elif value_id != None:
			try:
				zwaveValue = self.zwaveValuesById[value_id]
			except KeyError:
				self.valueException(label, value_id, "Invalid value_id")
		
		return value_id
	
	def getZwaveValue(self, label=None, value_id=None):
		value_id = self.getOrValidateValueId(label=label, value_id=value_id)
		zwaveValue = self.zwaveValuesById[value_id]
		return zwaveValue
	
	def registerTransform(self, func, label=None, value_id=None):
		target_id = self.getOrValidateValueId(label=label, value_id=value_id)
		self.transforms[target_id] = func
		
	def getData(self, label=None, value_id=None):
		target_id = self.getOrValidateValueId(label=label, value_id=value_id)
		zwaveValue = self.zwaveValuesById[target_id]
		
		if zwaveValue.is_write_only:
			self.valueException(label, value_id, "Write only value")
		
		# here the target_id will be set
		# check for a transform
		if zwaveValue.value_id in self.transforms:
			return self.transforms[zwaveValue.value_id](zwaveValue.data)
		# if no transform, just return the data
		else:
			return zwaveValue.data
	
	def setData(self, data, label=None, value_id=None):
		target_id = self.getOrValidateValueId(label=label, value_id=value_id)
		zwaveValue = self.zwaveValuesById[target_id]
	
		if zwaveValue.is_read_only:
			self.valueException(label, value_id, "Read only value")
		
		zwaveValue.data = data
		
	def getLastUpdateTime(self, label=None, value_id=None):
		target_id = self.getOrValidateValueId(label=label, value_id=value_id)
		try:
			updateTime = self.updateTimes[target_id]
		except KeyError:
			self.valueException(label, value_id, "Value never updated")

class Multisensor(ujouleZWaveNode):
	def __init__(self, nodeId, description=None, tempCorrection=3.0):
		super(Multisensor, self).__init__(nodeId, description)
		self.tempCorrection = tempCorrection
	
	def activated(self):
		self.logger.info("Activated multisensor-%d" % self.nodeId)
		
		self.registerTransform(self.correctTemperature, label="Temperature")
		self.setData(225, label="Group 1 Reports")
		self.setData(240, label="Group 1 Interval")

	def correctTemperature(self, temperature):
		corrected = temperature + self.tempCorrection
		corrected = round(corrected, 1)
		return corrected

class Thermostat(ujouleZWaveNode):
	def __init__(self, nodeId, description=None):
		super(Thermostat, self).__init__(nodeId, description)
	
	def activated(self):
		self.logger.info("Activated thermostat-%d" % self.nodeId)
		self.getZwaveValue(label="Temperature").enable_poll(intensity=1)
		self.getZwaveValue(label="Fan State").enable_poll(intensity=1)
		self.getZwaveValue(label="Fan Mode").enable_poll(intensity=1)
		self.getZwaveValue(label="Heating 1").enable_poll(intensity=1)
		self.getZwaveValue(label="Cooling 1").enable_poll(intensity=1)
		self.getZwaveValue(label="Operating State").enable_poll(intensity=1)
		self.getZwaveValue(label="Mode").enable_poll(intensity=1)