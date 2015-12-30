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
		self.zwaveValuesByIndex = {}
		self.zwaveValuesByLabel = {}
			
	# methods should call this to ensure activation
	def checkActivation(self):
		if not self.isActivated:
			raise Exception("Node %d is not yet activated..." % self.nodeId)
	
	def valueException(self, message, label=None, index=None, value_id=None):
		raise Exception("Value (label=%s, index=%s, value_id=%s): %s" % (str(label), str(index), str(value_id), message))
	
	# controller will call this when registered
	def activate(self, zwaveNetwork, zwaveNode):
		self.zwaveNode = zwaveNode
		for value_id in zwaveNode.get_values():
			value = ZWaveValue(value_id, zwaveNetwork, zwaveNode)
			self.zwaveValuesById[value_id] = value
			self.zwaveValuesByIndex[value.index] = value
			self.zwaveValuesByLabel[value.label] = value
			self.logger.debug("value: %s" % value)
		
		self.activated()
		
		self.isActivated = True
	
	# called when activated. subclasses can use to register overrides
	# or set up polling, etc.
	def activated(self):
		pass

	def logValue(self, zwaveValue):
		fileLabel = zwaveValue.label.replace(" ", "-")
		with open("data/node%s-%s.dat" % (self.nodeId, fileLabel), "a") as f:
			unixTimeNow = unix_ts(datetime.now())
			f.write("%d %s\n" % (unixTimeNow, str(self.getData(zwaveValue.value_id))))

		with open("data/node%s-%s-raw.dat" % (self.nodeId, fileLabel), "a") as f:
			unixTimeNow = unix_ts(datetime.now())
			f.write("%d %s\n" % (unixTimeNow, str(self.getRawData(zwaveValue.value_id))))

	def valueUpdate(self, zwaveValue):
		self.logger.debug("received update: node_id: %s, value_id %s, label %s, index=%s, raw data %s, transformed data: %s" % (self.nodeId, zwaveValue.value_id, zwaveValue.label, zwaveValue.index, zwaveValue.data, self.getData(value_id=zwaveValue.value_id)))
		self.updateTimes[zwaveValue.value_id] = datetime.now()
		self.logValue(zwaveValue)

	def getValueId(self, label=None, index=None):
		if label == None and index == None:
			self.valueException("Need to specify either label or index", label=label, index=index)
		
		if label != None and index != None:
			self.valueException("Need to specify either label or index", label=label, index=index)

		if label != None:
			try:
				zwaveValue = self.zwaveValuesByLabel[label]
			except KeyError:
				self.valueException("Invalid label", label=level, index=index)
			
			value_id = zwaveValue.value_id

		elif index != None:
			try:
				zwaveValue = self.zwaveValuesByIndex[index]
			except KeyError:
				self.valueException("Invalid index", label=label, index=index)
		
			value_id = zwaveValue.value_id

		return value_id
	
	def getZwaveValue(self, value_id):
		zwaveValue = self.zwaveValuesById[value_id]
		return zwaveValue
	
	def registerTransform(self, func, value_id):
		self.transforms[value_id] = func

	def getData(self, value_id):
		zwaveValue = self.zwaveValuesById[value_id]
		
		if zwaveValue.is_write_only:
			self.valueException("Write only value", value_id=value_id)
		
		# here the target_id will be set
		# check for a transform
		if zwaveValue.value_id in self.transforms:
			return self.transforms[zwaveValue.value_id](zwaveValue.data)
		# if no transform, just return the data
		else:
			return zwaveValue.data

	def getRawData(self, value_id):
		zwaveValue = self.zwaveValuesById[value_id]

		if zwaveValue.is_write_only:
			self.valueException("Write only value", value_id=value_id)

		return zwaveValue.data

	def setData(self, data, value_id):
		zwaveValue = self.zwaveValuesById[value_id]
	
		if zwaveValue.is_read_only:
			self.valueException("Read only value", value_id=value_id)
		
		zwaveValue.data = data
		
	def getLastUpdateTime(self, value_id):
		try:
			updateTime = self.updateTimes[value_id]
		except KeyError:
			self.valueException("Value never updated", value_id=value_id)

class ZWaveMultisensor(ujouleZWaveNode):
	def __init__(self, nodeId, description=None, tempCorrection=3.0):
		super(ZWaveMultisensor, self).__init__(nodeId, description)
		self.tempCorrection = tempCorrection
	
	def activated(self):
		self.logger.info("Activated multisensor-%d" % self.nodeId)
		
		self.registerTransform(self.correctTemperature, value_id=self.getValueId(label="Temperature"))
		self.setData(240, value_id=self.getValueId(index=3))	# timeout period after motion sensor trigger
		self.setData("True", value_id=self.getValueId(index=4))	# enable PIR motion sensor
		self.setData(224, value_id=self.getValueId(index=101))	# Set sensors to be reported
		self.setData(240, value_id=self.getValueId(index=111))	# Set reporting interval

	def correctTemperature(self, temperature):
		corrected = temperature + self.tempCorrection
		corrected = (int(corrected*10.0) -(int(corrected*10.0) % 5)) / 10.0
		return corrected

class ZWaveThermostat(ujouleZWaveNode):
	def __init__(self, nodeId, description=None):
		super(ZWaveThermostat, self).__init__(nodeId, description)
	
	def activated(self):
		self.logger.info("Activated thermostat-%d" % self.nodeId)
		self.getZwaveValue(self.getValueId(label="Temperature")).enable_poll(intensity=4)
		self.getZwaveValue(self.getValueId(label="Heating 1")).enable_poll(intensity=4)
		self.getZwaveValue(self.getValueId(label="Cooling 1")).enable_poll(intensity=4)
		self.getZwaveValue(self.getValueId(label="Fan State")).enable_poll(intensity=4)
		self.getZwaveValue(self.getValueId(label="Fan Mode")).enable_poll(intensity=4)
		self.getZwaveValue(self.getValueId(label="Operating State")).enable_poll(intensity=4)
		self.getZwaveValue(self.getValueId(label="Mode")).enable_poll(intensity=4)
