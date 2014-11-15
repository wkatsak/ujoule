#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""

This file is part of **python-openzwave** project http://code.google.com/p/python-openzwave.
    :platform: Unix, Windows, MacOS X
    :sinopsis: openzwave wrapper

.. moduleauthor:: bibi21000 aka Sébastien GALLET <bibi21000@gmail.com>

License : GPL(v3)

**python-openzwave** is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

**python-openzwave** is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
GNU General Public License for more details.
You should have received a copy of the GNU General Public License
along with python-openzwave. If not, see http://www.gnu.org/licenses.

"""

import logging
import sys, os, signal
from datetime import datetime

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
import time
from louie import dispatcher, All

device="/dev/ttyUSB0"
log="None"
sniff=300.0

for arg in sys.argv:
    if arg.startswith("--device"):
        temp,device = arg.split("=")
    elif arg.startswith("--log"):
        temp,log = arg.split("=")
    elif arg.startswith("--sniff"):
        temp,sniff = arg.split("=")
        sniff = float(sniff)
    elif arg.startswith("--help"):
        print("help : ")
        print("  --device=/dev/yourdevice ")
        print("  --log=Info|Debug")

#Define some manager options
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
    print('%s: Hello from value : %s.' % (str(datetime.now()), value))

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

#sensorGroup = ZWaveGroup(1, network, SENSOR_ID)
#thermostatGroup = ZWaveGroup(1, network, THERMOSTAT_ID)

#sensorGroup.add_association(1)
#sensorGroup.add_association(SENSOR_ID)
#thermostatGroup.add_association(1)
#thermostatGroup.add_association(THERMOSTAT_ID)

#print sensorGroup
#print thermostatGroup
#for node in network.nodes:
#	print node

CONTROLLER_NODE = network.nodes[CONTROLLER_ID]
THERMOSTAT_NODE = network.nodes[THERMOSTAT_ID]
SENSOR_NODE = network.nodes[SENSOR_ID]

SENSOR_REFRESH_INTERVAL_ID = 72057594081707763 # how often to send (should be 240)
SENSOR_REFRESH_REPORTS_ID = 72057594081707603  # what to send (should be 225)
THERMOSTAT_TEMPERATURE_ID = 72057594076479506  # value to get temperature

thermostatTemperatureValue = ZWaveValue(THERMOSTAT_TEMPERATURE_ID, network, THERMOSTAT_NODE)
thermostatTemperatureValue.enable_poll(intensity=1)
#thermostatTemperatureValue.disable_poll()
sensorRefreshIntervalValue = ZWaveValue(SENSOR_REFRESH_INTERVAL_ID, network, SENSOR_NODE)
sensorRefreshReportsValue = ZWaveValue(SENSOR_REFRESH_REPORTS_ID, network, SENSOR_NODE)


#from IPython import embed
#embed()
#network.stop()
#sys.exit()

print "Starting loop"
while True:
	time.sleep(3600.0)
network.stop()
