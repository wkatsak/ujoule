#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
import sys, os, signal
from datetime import datetime, timedelta
import time
import argparse
from threading import Lock

#logging.getLogger('openzwave').addHandler(logging.NullHandler())
#logging.basicConfig(level=logging.DEBUG)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('openzwave')

try :
    import openzwave
    from openzwave.node import ZWaveNode
    from openzwave.value import ZWaveValue
    from openzwave.scene import ZWaveScene
    from openzwave.controller import ZWaveController
    from openzwave.network import ZWaveNetwork
    from openzwave.option import ZWaveOption
    from openzwave.group import ZWaveGroup
    print("Openzwave is installed.")
except :
    print("Openzwave is not installed. Get it from tmp directory.")
    sys.path.insert(0, os.path.abspath('../build/tmp/usr/local/lib/python2.6/dist-packages'))
    sys.path.insert(0, os.path.abspath('../build/tmp/usr/local/lib/python2.7/dist-packages'))
    sys.path.insert(0, os.path.abspath('build/tmp/usr/local/lib/python2.6/dist-packages'))
    sys.path.insert(0, os.path.abspath('build/tmp/usr/local/lib/python2.7/dist-packages'))
    import openzwave
    from openzwave.node import ZWaveNode
    from openzwave.value import ZWaveValue
    from openzwave.scene import ZWaveScene
    from openzwave.controller import ZWaveController
    from openzwave.network import ZWaveNetwork
    from openzwave.option import ZWaveOption

from louie import dispatcher, All

def unix_ts(dt):
	epoch = datetime(month=1, day=1, year=1970)
	return int((dt - epoch).total_seconds())
	
class Multisensor(object):

	def __init__(self, zwaveNetwork, zwaveNode, correction=2.0):
		self.zwaveNetwork = zwaveNetwork
		self.zwaveNode = zwaveNode
		self.correction = correction
		
		self.battery = float("NaN")
		self.temperature = float("NaN")
		self.humdity = float("NaN")
		self.luminance = float("NaN")
		self.motion = False
		
		self.outfile = open("multisensor.out", "w")
		
		self.lock = Lock()
		
	def getBattery(self):
		pass
	
	def getTemperature(self):
		return self.temperature
	
	def getHumidity(self):
		pass
	
	def getLuminance(self):
		pass
	
	def getMotion(self):
		pass

	def setBattery(self):
		pass
	
	def setTemperature(self, value):
		with self.lock:
			corrected = value + self.correction
			self.temperature = round(corrected * 2.0)/2.0
			now = datetime.now()
			string = "%d %0.2f %0.2f\n" % (unix_ts(now), self.temperature, value)
			print now, self.temperature, value, "multisensor"
			
			self.outfile.write(string)
			self.outfile.flush()
	
	def setHumidity(self, value):
		pass
	
	def setLuminance(self, value):
		pass
	
	def setMotion(self, value):
		pass
	

class Thermostat(object):
	
	def __init__(self, zwaveNetwork, zwaveNode):
		self.zwaveNetwork = zwaveNetwork
		self.zwaveNode = zwaveNode

		self.lock = Lock()
		self.outfile = open("thermostat.out", "w")
		
	def getTemperature(self):
		return self.temperature
	
	def setTemperature(self, value):
		with self.lock:
			self.temperature = value
			
			now = datetime.now()
			string = "%d %0.2f\n" % (unix_ts(now), self.temperature)
			print now, self.temperature, "thermostat"
			
			self.outfile.write(string)
			self.outfile.flush()

valueTable = {}
DEVICE="/dev/zwave"

#Define some manager options
options = ZWaveOption(DEVICE, \
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

def louie_network_started(network):
    print("Hello from network : I'm started : homeid %0.8x - %d nodes were found." % \
        (network.home_id, network.nodes_count))

def louie_network_failed(network):
    print("Hello from network : can't load :(.")

def louie_network_ready(network):
    print("Hello from network : I'm ready : %d nodes were found." % network.nodes_count)
    print("Hello from network : my controller is : %s" % network.controller)
    dispatcher.connect(louie_node_update, ZWaveNetwork.SIGNAL_NODE)
    dispatcher.connect(louie_value_update, ZWaveNetwork.SIGNAL_VALUE)

def louie_node_update(network, node):
    print('Hello from node : %s.' % node)

def louie_value_update(network, node, value):
    #print('%s: Hello from value : %s.' % (str(datetime.now()), value))
    key = (value.parent_id, value.value_id)
    #print "value has key", key
    if key in valueTable:
	    valueTable[key](value.data)    

def sigint(signum, other):
	network.stop()
	sys.exit()

signal.signal(signal.SIGINT, sigint)

#Create a network object
network = ZWaveNetwork(options, autostart=False)

#We connect to the louie dispatcher
dispatcher.connect(louie_network_started, ZWaveNetwork.SIGNAL_NETWORK_STARTED)
dispatcher.connect(louie_network_failed, ZWaveNetwork.SIGNAL_NETWORK_FAILED)
dispatcher.connect(louie_network_ready, ZWaveNetwork.SIGNAL_NETWORK_READY)

network.start()

#We wait for the network.
print "***** Waiting for network to become ready : "
for i in range(0,600):
    if network.state>=network.STATE_READY:
        print "***** Network is ready"
        break
    else:
        sys.stdout.write(".")
        sys.stdout.flush()
        time.sleep(1.0)

time.sleep(5.0)
#We update the name of the controller
print("Update controller name")
network.controller.node.name = "Katsak uJoule"
time.sleep(5.0)
#We update the location of the controller
print("Update controller location")
network.controller.node.location = "Katsak Home"
time.sleep(5.0)

# start our testing here
CONTROLLER_ID = 1
THERMOSTAT_ID = 2
SENSOR_ID = 3

CONTROLLER_NODE = network.nodes[CONTROLLER_ID]
THERMOSTAT_NODE = network.nodes[THERMOSTAT_ID]
SENSOR_NODE = network.nodes[SENSOR_ID]

SENSOR_REFRESH_INTERVAL_ID = 72057594081707763 # how often to send (should be 240)
SENSOR_REFRESH_REPORTS_ID = 72057594081707603  # what to send (should be 225)
THERMOSTAT_TEMPERATURE_ID = 72057594076479506  # value to get temperature
SENSOR_TEMPERATURE_ID = 72057594093256722      # value to get temperature

thermostatTemperatureValue = ZWaveValue(THERMOSTAT_TEMPERATURE_ID, network, THERMOSTAT_NODE)
thermostatTemperatureValue.enable_poll(intensity=1)
sensorRefreshIntervalValue = ZWaveValue(SENSOR_REFRESH_INTERVAL_ID, network, SENSOR_NODE)
sensorRefreshReportsValue = ZWaveValue(SENSOR_REFRESH_REPORTS_ID, network, SENSOR_NODE)

multisensor = Multisensor(network, SENSOR_NODE)
thermostat = Thermostat(network, THERMOSTAT_NODE)

valueTable[SENSOR_ID, SENSOR_TEMPERATURE_ID] = multisensor.setTemperature
valueTable[THERMOSTAT_ID, THERMOSTAT_TEMPERATURE_ID] = thermostat.setTemperature

#from IPython import embed
#embed()
#network.stop()
#sys.exit()

print "Starting loop"
while True:
	time.sleep(3600.0)
network.stop()
