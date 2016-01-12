#!/usr/bin/python

import logging
import openzwave
from openzwave.node import ZWaveNode
from openzwave.value import ZWaveValue
from openzwave.scene import ZWaveScene
from openzwave.controller import ZWaveController
from openzwave.network import ZWaveNetwork
from openzwave.option import ZWaveOption
from openzwave.group import ZWaveGroup
from louie import dispatcher, All

from helpers import unix_ts
from threading import Lock, Condition
from datetime import datetime, timedelta
from common import ujouleLouieSignals, getLogger

class ujouleZWaveException(Exception):
	def __init__(self, msg):
		super(ujouleZWaveException, self).__init__(self)

# the controller should take care of the zwave network and objects
class ujouleZWaveController(object):
	def __init__(self, nodeId, device="/dev/zwave", options=None):
		self.logger = getLogger(self)
		self.nodeId = nodeId

		# openzwave configuration
		if options != None:
			self.options = options
		else:
			options = ZWaveOption(device, \
			config_path="/home/wkatsak/arm/python-openzwave/openzwave/config", \
			user_path=".", cmd_line="")
			options.set_log_file("OZW_Log.log")
			options.set_append_log_file(False)
			options.set_console_output(False)
			options.set_save_log_level('Debug')
			options.set_logging(True)
			options.set_poll_interval(60000)
			options.set_interval_between_polls(True)
			options.set_associate(True)
			options.lock()
			self.options = options

		# we have this weird thing where we get two updates from multisensor
		# lets keep a table of update times and and discard the second one within
		# one second
		self.lastUpdateTimes = {}

		# condition variable for ready
		self.readyCondition = Condition()
		self.readyFlag = False

		# data sources
		self.registeredNodes = []

	# start the stop the zwave network
	def start(self):
		#Create a network object
		self.network = ZWaveNetwork(self.options, autostart=False)

		#Create a controller object
		self.controller = ZWaveController(self.nodeId, self.network)
		#self.logger.info("Soft resetting controller...")
		#self.controller.soft_reset()

		#We connect to the louie dispatcher
		dispatcher.connect(self.louie_network_started, ZWaveNetwork.SIGNAL_NETWORK_STARTED)
		dispatcher.connect(self.louie_network_failed, ZWaveNetwork.SIGNAL_NETWORK_FAILED)
		dispatcher.connect(self.louie_network_ready, ZWaveNetwork.SIGNAL_NETWORK_READY)

		# start the network
		self.network.start()

	def stop(self):
		self.network.stop()

	def registerNode(self, ujouleNode):
		self.registeredNodes.append(ujouleNode)

	# sleeps until ready
	def ready(self):
		self.logger.info("Waiting for network to be ready")

		# wait on condition
		self.readyCondition.acquire()
		while not self.readyFlag:
			self.readyCondition.wait()
		self.readyCondition.release()

		self.logger.info("...ready")

	# louie callbacks for zwave
	def louie_network_started(self, network):
		self.logger.debug("Network started, homeid %0.8x, found %d nodes" % (network.home_id, network.nodes_count))

	def louie_network_failed(self, network):
		self.logger.error("Network failed to start")

	def louie_network_ready(self, network):
		self.logger.debug("Network ready, %d nodes found, controller is %s" % (network.nodes_count, network.controller))

		# register callbacks for node and value updates
		dispatcher.connect(self.louie_node_update, ZWaveNetwork.SIGNAL_NODE)
		self.logger.debug("Registered callback for SIGNAL_NODE")

		dispatcher.connect(self.louie_value_update, ZWaveNetwork.SIGNAL_VALUE)
		self.logger.debug("Registered callback for SIGNAL_VALUE")

		# activate the registered nodes
		for registeredNode in self.registeredNodes:
			for node in self.network.nodes:
				if self.network.nodes[node].node_id == registeredNode.nodeId:
					registeredNode.activate(self.network, self.network.nodes[node])

		# signal the ready condition
		self.readyCondition.acquire()
		self.readyFlag = True
		self.readyCondition.notify()
		self.readyCondition.release()

	def louie_node_update(self, network, node):
		self.logger.debug("Received update from node: %s" % node)
		pass

	# this one is important, it needs to relay the fact that a value was updated
	# from the zwave network to their associated objects
	def louie_value_update(self, network, node, value):
		try:
			# short circuit if we received a duplicate within 1 second
			if value in self.lastUpdateTimes and (datetime.now() - self.lastUpdateTimes[value]) < timedelta(seconds=1):
				self.logger.debug("Dropped duplicate value: %s" % value)
				return

			# otherwise, process as normal
			self.lastUpdateTimes[value] = datetime.now()
			self.logger.debug("Received value: %s" % value)

			for registeredNode in self.registeredNodes:
				if node.node_id == registeredNode.nodeId:
					# pass the entire ZWaveValue object
					registeredNode.notifyValueUpdated(value)
		except Exception as e:
			print "Exception", e
			traceback.print_exc()

class ujouleZWaveNode(object):
	def __init__(self, nodeId, description=None):
		self.nodeId = nodeId
		self.description = description
		
		self.isActivated = False
		self.logger = getLogger(self)
		self.transforms = {} # indexed by Id
		self.updateTimes = {} # indexed by Id
		self.zwaveValuesById = {}
		self.zwaveValuesByIndex = {}
		self.zwaveValuesByLabel = {}

		# condition variable for ready
		self.readyCondition = Condition()
		self.readyFlag = False
			
	# methods should call this to ensure activation
	def checkActivation(self):
		if not self.isActivated:
			raise Exception("Node %d is not yet activated..." % self.nodeId)
	
	def valueException(self, message, label=None, index=None, value_id=None):
		raise ujouleZWaveException("Value (label=%s, index=%s, value_id=%s): %s" % (str(label), str(index), str(value_id), message))
	
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

	def ready(self):
		# wait on condition
		self.readyCondition.acquire()
		while not self.readyFlag:
			self.readyCondition.wait()
		self.readyCondition.release()

	def signalReady(self):
		# signal the ready condition
		self.readyCondition.acquire()
		self.readyFlag = True
		self.readyCondition.notify()
		self.readyCondition.release()

	def notifyValueUpdated(self, zwaveValue):
		self.logger.debug("received update: node_id: %s, value_id %s, label %s, index=%s, raw data %s, transformed data: %s" % (self.nodeId, zwaveValue.value_id, zwaveValue.label, zwaveValue.index, zwaveValue.data, self.getData(value_id=zwaveValue.value_id)))
		self.updateTimes[zwaveValue.value_id] = datetime.now()
		self.valueUpdated(zwaveValue.label, self.getData(zwaveValue.value_id))

	# subclasses should implement this
	def valueUpdated(self, label, value):
		pass

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

class ujouleZWaveMultisensor(ujouleZWaveNode):
	def __init__(self, nodeId, description=None, tempCorrection=0.0):
		super(ujouleZWaveMultisensor, self).__init__(nodeId, description)
		self.tempCorrection = tempCorrection
		self.prevTemperature = None

	def activated(self):
		self.logger.debug("Activated multisensor-%d" % self.nodeId)
		
		self.registerTransform(self.transformTemperature, value_id=self.getValueId(label="Temperature"))
		self.setData(240, value_id=self.getValueId(index=3))	# timeout period after motion sensor trigger
		self.setData("True", value_id=self.getValueId(index=4))	# enable PIR motion sensor
		self.setData(224, value_id=self.getValueId(index=101))	# Set sensors to be reported
		self.setData(240, value_id=self.getValueId(index=111))	# Set reporting interval

	# only report temperatures at 0.5 degree boundaries
	def transformTemperature(self, temperature):
		transformed = temperature + self.tempCorrection
		transformed = (int(transformed*10.0) -(int(transformed*10.0) % 5)) / 10.0

		if transformed > 50.0 and transformed < 100.0:
			return transformed
		else:
			return float("nan")

	def valueUpdated(self, label, value):
		if label == "Temperature":
			self.signalReady()

			dispatcher.send(signal=ujouleLouieSignals.SIGNAL_TEMPERATURE_UPDATED, sender=self, value=value)

			if value != self.prevTemperature:
				self.prevTemperature = value
				dispatcher.send(signal=ujouleLouieSignals.SIGNAL_TEMPERATURE_CHANGED, sender=self, value=value)

	def getTemperature(self):
		valueId = self.getValueId(label="Temperature")
		return self.getData(valueId)

class ujouleZWaveThermostat(ujouleZWaveNode):
	SYS_MODE_OFF = 0
	SYS_MODE_HEAT = 1
	SYS_MODE_COOL = 2
	FAN_MODE_AUTO = 4
	FAN_MODE_ON = 8
	FAN_STATE_RUNNING = 16
	FAN_STATE_IDLE = 32

	def __init__(self, nodeId, description=None):
		super(ujouleZWaveThermostat, self).__init__(nodeId, description)
		self.prevTemperature = None

	def activated(self):
		self.logger.debug("Activated thermostat-%d" % self.nodeId)
		self.getZwaveValue(self.getValueId(label="Temperature")).enable_poll(intensity=4)
		self.getZwaveValue(self.getValueId(label="Heating 1")).enable_poll(intensity=4)
		self.getZwaveValue(self.getValueId(label="Cooling 1")).enable_poll(intensity=4)
		self.getZwaveValue(self.getValueId(label="Fan State")).enable_poll(intensity=4)
		self.getZwaveValue(self.getValueId(label="Fan Mode")).enable_poll(intensity=4)
		self.getZwaveValue(self.getValueId(label="Operating State")).enable_poll(intensity=4)
		self.getZwaveValue(self.getValueId(label="Mode")).enable_poll(intensity=4)

	def constToString(self, mode):
		if mode == ujouleZWaveThermostat.SYS_MODE_OFF:
			return "Off"
		elif mode == ujouleZWaveThermostat.SYS_MODE_HEAT:
			return "On (Heat)"
		elif mode == ujouleZWaveThermostat.SYS_MODE_COOL:
			return "On (Cool)"
		elif mode == ujouleZWaveThermostat.FAN_MODE_AUTO:
			return "Auto"
		elif mode == ujouleZWaveThermostat.FAN_MODE_ON:
			return "On"
		elif mode == ujouleZWaveThermostat.FAN_STATE_RUNNING:
			return "Running"
		elif mode == ujouleZWaveThermostat.FAN_STATE_IDLE:
			return "Idle"
		else:
			return "Invalid Mode"

	def valueUpdated(self, label, value):
		if label == "Temperature":
			self.signalReady()

			dispatcher.send(signal=ujouleLouieSignals.SIGNAL_TEMPERATURE_UPDATED, sender=self, value=value)

			if value != self.prevTemperature:
				self.prevTemperature = value
				dispatcher.send(signal=ujouleLouieSignals.SIGNAL_TEMPERATURE_CHANGED, sender=self, value=value)

	def getTemperature(self):
		valueId = self.getValueId(label="Temperature")
		return self.getData(valueId)

	def setFanMode(self, setting):
		valueId = self.getValueId(label="Fan Mode")
		if setting == ujouleZWaveThermostat.FAN_MODE_ON:
			self.setData("On Low", valueId)
		elif setting == ujouleZWaveThermostat.FAN_MODE_AUTO:
			self.setData("Auto Low", valueId)
		else:
			raise ujouleZWaveException("Invalid fan mode specified: %d" % data)

	def getFanMode(self):
		valueId = self.getValueId(label="Fan Mode")
		data = self.getData(valueId)
		if data == "Auto Low":
			return ujouleZWaveThermostat.FAN_MODE_AUTO
		elif data == "On Low":
			return ujouleZWaveThermostat.FAN_MODE_ON
		else:
			raise ujouleZWaveException("Invalid fan mode received from ZWave: %s" % data)

	def getFanState(self):
		valueId = self.getValueId(label="Fan State")
		data = self.getData(valueId)
		if data == "Running":
			return ujouleZWaveThermostat.FAN_STATE_RUNNING
		elif data == "Idle":
			return ujouleZWaveThermostat.FAN_STATE_IDLE
		else:
			raise ujouleZWaveException("Invalid fan state received from ZWave: %s" % data)

	def setSystemMode(self, setting):
		if setting == ujouleZWaveThermostat.SYS_MODE_HEAT:
			modeValueId = self.getValueId(label="Mode")
			self.setData("Heat", modeValueId)
			self.setHeatTarget(80.0)
		elif setting == ujouleZWaveThermostat.SYS_MODE_COOL:
			modeValueId = self.getValueId(label="Mode")
			self.setData("Cool", modeValueId)
			self.setCoolTarget(60.0)
		elif setting == ujouleZWaveThermostat.SYS_MODE_OFF:
			modeValueId = self.getValueId(label="Mode")
			self.setData("Off", modeValueId)
		else:
			raise ujouleZWaveException("Invalid system mode specified: %d" % data)

	def getSystemMode(self):
		valueId = self.getValueId(label="Mode")
		data = self.getData(valueId)
		if data == "Heat":
			return ujouleZWaveThermostat.SYS_MODE_HEAT
		elif data == "Cool":
			return ujouleZWaveThermostat.SYS_MODE_COOL
		elif data == "Off":
			return ujouleZWaveThermostat.SYS_MODE_OFF
		else:
			raise ujouleZWaveException("Invalid system mode received from ZWave: %s" % data)

	def setHeatTarget(self, target):
		targetValueId = self.getValueId(label="Heating 1")
		self.setData(target, targetValueId)

	def getHeatTarget(self):
		targetValueId = self.getValueId(label="Heating 1")
		data = self.getData(targetValueId)
		return data

	def setCoolTarget(self, target):
		targetValueId = self.getValueId(label="Cooling 1")
		self.setData(target, targetValueId)

	def getCoolTarget(self):
		targetValueId = self.getValueId(label="Cooling 1")
		data = self.getData(targetValueId)
		return data
