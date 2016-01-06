#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
import sys, os, signal
import time
import argparse
import traceback

from datetime import datetime, timedelta, time
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

from zwave import ujouleZWaveController, ujouleZWaveNode, ujouleZWaveMultisensor, ujouleZWaveThermostat
from climate import ClimateController, SimplePolicy, BedtimePolicy, iCloudAwayDetector, WeatherUndergroundTemperature

CONTROLLER_ID = 1
THERMOSTAT_ID = 2
BEDROOM_SENSOR_ID = 3
OFFICE_SENSOR_ID = 4

# configure logger basics
logging.basicConfig(filename="ujoule.log", level=logging.INFO, format='%(asctime)s %(name)s %(levelname)s: %(message)s', datefmt='%m/%d/%Y %I:%M:%S %p')

# don't print messages to screen
#logging.getLogger().addHandler(logging.StreamHandler(sys.stdout))

def sigint(signum, other):
	print "SIGINT"
	controller.stop()
	sys.exit()

if __name__ == "__main__":
	signal.signal(signal.SIGINT, sigint)

	# initialize zwave stuff
	zwaveController = ujouleZWaveController(CONTROLLER_ID)
	zwaveMultisensorBedroom = ujouleZWaveMultisensor(BEDROOM_SENSOR_ID)
	zwaveMultisensorOffice = ujouleZWaveMultisensor(OFFICE_SENSOR_ID)
	zwaveThermostat = ujouleZWaveThermostat(THERMOSTAT_ID)
	zwaveController.registerNode(zwaveThermostat)
	zwaveController.registerNode(zwaveMultisensorBedroom)
	zwaveController.registerNode(zwaveMultisensorOffice)
	zwaveController.start()
	zwaveController.ready()

	# initialize climate control stuff
	insideSensors = {
		"bedroom" : zwaveMultisensorBedroom,
		"office" : zwaveMultisensorOffice,
		"livingroom" : zwaveThermostat,
	}
	outsideSensor = WeatherUndergroundTemperature()

	climateController = ClimateController(zwaveThermostat, insideSensors, outsideSensor)

	bedtimePolicy = BedtimePolicy(climateController)
	#climateController.addPolicy(bedtimePolicy, (time(hour=19, minute=45), time(hour=7)))

	billDetector = iCloudAwayDetector("wkatsak@cs.rutgers.edu", "Bill1085")
	firuzaDetector = iCloudAwayDetector("firuzaa8@gmail.com", "Bill1085")
	climateController.addAwayDetector("Bill", billDetector)
	climateController.addAwayDetector("Firuza", firuzaDetector)

	climateController.start()
	climateController.shell()

	controller.stop()
	sys.exit()
