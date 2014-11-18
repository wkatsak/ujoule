#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
import sys, os, signal
import time
import argparse
from datetime import datetime, timedelta
from threading import Lock, Condition

import openzwave
from openzwave.node import ZWaveNode
from openzwave.value import ZWaveValue
from openzwave.scene import ZWaveScene
from openzwave.controller import ZWaveController
from openzwave.network import ZWaveNetwork
from openzwave.option import ZWaveOption
from openzwave.group import ZWaveGroup
from louie import dispatcher, All

from structures import Multisensor, Thermostat

CONTROLLER_ID = 1
THERMOSTAT_ID = 2
SENSOR_ID = 3

# TODO: need some way to set parameters like polling, etc. from objects
#CONTROLLER_NODE = network.nodes[CONTROLLER_ID]
#THERMOSTAT_NODE = network.nodes[THERMOSTAT_ID]
#SENSOR_NODE = network.nodes[SENSOR_ID]
#SENSOR_REFRESH_INTERVAL_ID = 72057594081707763 # how often to send (should be 240)
#SENSOR_REFRESH_REPORTS_ID = 72057594081707603  # what to send (should be 225)
#THERMOSTAT_TEMPERATURE_ID = 72057594076479506  # value to get temperature
#SENSOR_TEMPERATURE_ID = 72057594093256722      # value to get temperature
#thermostatTemperatureValue = ZWaveValue(THERMOSTAT_TEMPERATURE_ID, network, THERMOSTAT_NODE)
#thermostatTemperatureValue.enable_poll(intensity=1)
#sensorRefreshIntervalValue = ZWaveValue(SENSOR_REFRESH_INTERVAL_ID, network, SENSOR_NODE)
#sensorRefreshReportsValue = ZWaveValue(SENSOR_REFRESH_REPORTS_ID, network, SENSOR_NODE)

# configure logger basics
logging.basicConfig(filename="ujoule.log", level=logging.INFO, format='%(asctime)s %(name)s %(levelname)s: %(message)s', datefmt='%m/%d/%Y %I:%M:%S %p')

# this should encapsulate everything
# roles are monitoring anything zwave (done by class objects representing the sensors)
# and HVAC control (done by another class)
# 
# the controller should take care of the zwave network and objects
class uJouleController(object):
	def __init__(self, device="/dev/zwave", options=None):
		self.logger = logging.getLogger("uJouleController")
		
		# table for sensors to register their callbacks in
		self.valueCallbackTable = {}
		
		# openzwave configuration
		if options != None:
			self.options = options
		else:
			options = ZWaveOption(device, \
			config_path="/home/wkatsak/python-openzwave/openzwave/config", \
			user_path=".", cmd_line="")
			options.set_log_file("OZW_Log.log")
			options.set_append_log_file(False)
			options.set_console_output(False)
			options.set_save_log_level('Debug')
			options.set_logging(True)
			options.set_poll_interval(240000)
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
		self.dataSources = []
		
	# start the stop the zwave network
	def start(self):
		#Create a network object
		self.network = ZWaveNetwork(self.options, autostart=False)

		#We connect to the louie dispatcher
		dispatcher.connect(self.louie_network_started, ZWaveNetwork.SIGNAL_NETWORK_STARTED)
		dispatcher.connect(self.louie_network_failed, ZWaveNetwork.SIGNAL_NETWORK_FAILED)
		dispatcher.connect(self.louie_network_ready, ZWaveNetwork.SIGNAL_NETWORK_READY)

		# start the network
		self.network.start()
	
	def stop(self):
		pass
	
	def registerDataSource(self, dataSource):
		self.dataSources.append(dataSource)
	
	# sleeps until ready
	def ready(self):
		self.logger.info("Waiting for network to be ready")
		
		# wait on condition
		self.readyCondition.acquire()
		while not self.readyFlag:
			self.readyCondition.wait()
		self.readyCondition.release()

	# louie callbacks for zwave
	def louie_network_started(self, network):
		self.logger.info("Network started, homeid %0.8x, found %d nodes" % (network.home_id, network.nodes_count))
	
	def louie_network_failed(self, network):
		self.logger.error("Network failed to start")
	
	def louie_network_ready(self, network):
		self.logger.info("Network ready, %d nodes found, controller is %s" % (network.nodes_count, network.controller))
		
		# register callbacks for node and value updates
		dispatcher.connect(self.louie_node_update, ZWaveNetwork.SIGNAL_NODE)
		self.logger.debug("Registered callback for SIGNAL_NODE")
		
		dispatcher.connect(self.louie_value_update, ZWaveNetwork.SIGNAL_VALUE)
		self.logger.debug("Registered callback for SIGNAL_VALUE")
		
		# signal the ready condition
		self.readyCondition.acquire()
		self.readyFlag = True
		self.readyCondition.notify()
		self.readyCondition.release()	

	def louie_node_update(self, network, node):
		self.logger.info("Received update from node: %s" % node)

	# this one is important, it needs to relay the values received from
	# zwave network to their associated objects
	def louie_value_update(self, network, node, value):	
		# short circuit if we received a duplicate within 1 second
		if value in self.lastUpdateTimes and (datetime.now() - self.lastUpdateTimes[value]) < timedelta(seconds=1):
			self.logger.info("Dropped duplicate value: %s" % value)
			return
		
		# otherwise, process as normal
		self.lastUpdateTimes[value] = datetime.now()
		self.logger.info("Received value: %s" % value)
		
		for dataSource in self.dataSources:
			if node.node_id == dataSource.getNodeId():
				valueFuncs = dataSource.getValueFuncs()
				for valueFuncKey in valueFuncs:
					if value.label == valueFuncKey:
						try:
							valueFuncs[valueFuncKey](value.data)
						except Exception as e:
							self.logger.info("Exception calling func: %s" % e)
							
						return

#from IPython import embed
#embed()
#network.stop()
#sys.exit()

def sigint(signum, other):
	controller.stop()
	sys.exit()

if __name__ == "__main__":
	signal.signal(signal.SIGINT, sigint)
	
	controller = uJouleController()
	multisensor = Multisensor(SENSOR_ID)
	thermostat = Thermostat(THERMOSTAT_ID)
	
	controller.registerDataSource(multisensor)
	controller.registerDataSource(thermostat)
	
	controller.start()
	controller.ready()

	print "Starting loop"
	while True:
		time.sleep(60.0)
