#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
import sys, os, signal
import time
import argparse
import traceback
from datetime import datetime, timedelta, time

import common
from zwave import ujouleZWaveController, ujouleZWaveNode, ujouleZWaveMultisensor, ujouleZWaveThermostat
from climate import ClimateController, ClimateControllerConfig, iCloudAwayDetector, WeatherUndergroundService
from policy import CoolingDaytimePolicy, CoolingBedtimePolicy, HeatingDaytimePolicy, HeatingBedtimePolicy
from web import FlaskThread

CONTROLLER_ID = 1
THERMOSTAT_ID = 2
BEDROOM_SENSOR_ID = 3
OFFICE_SENSOR_ID = 4

# configure logger basics
logging.basicConfig(filename="ujoule.log", level=logging.DEBUG, format='%(asctime)s %(name)s %(levelname)s: %(message)s', datefmt='%m/%d/%Y %I:%M:%S %p')
# supress INFO from requests package
logging.getLogger("requests").setLevel(logging.WARNING)
# supress most messages from werkzeug package (flask)
#logging.getLogger('werkzeug').setLevel(logging.ERROR)
# main logger
logger = logging.getLogger("ujoule")

# don't print messages to screen
# logging.getLogger().addHandler(logging.StreamHandler(sys.stdout))

# 'global' so flask can find the controller
controller = None

def sigint(signum, other):
	print "SIGINT"
	zwaveController.stop()
	sys.exit()

if __name__ == "__main__":
	logger.info("")
	logger.info("uJoule Climate Control System")
	logger.info("Copyright (C) 2015, 2016 William Katsak")
	logger.info("Initializing...")

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

	# make sure we have good values from the zwave stuff before we start the climate logic
	zwaveThermostat.ready()
	zwaveMultisensorBedroom.ready()
	zwaveMultisensorOffice.ready()

	# initialize climate control stuff
	insideSensors = {
		"bedroom" : zwaveMultisensorBedroom,
		"office" : zwaveMultisensorOffice,
		"livingroom" : zwaveThermostat,
	}
	outsideSensor = WeatherUndergroundService()

	climateController = ClimateController(zwaveThermostat, insideSensors, outsideSensor, mode=ClimateController.MODE_HEAT, autoCoolThreshold=70.0)

	climateController.setDefaultConfig(ClimateController.MODE_HEAT, ClimateControllerConfig(policy=HeatingDaytimePolicy, setpoint=73.0))
	climateController.addScheduledConfig(ClimateController.MODE_HEAT, ClimateControllerConfig(policy=HeatingBedtimePolicy, setpoint=70.0), startTime=time(hour=17, minute=45), endTime=time(hour=5))

	climateController.setDefaultConfig(ClimateController.MODE_COOL, ClimateControllerConfig(policy=CoolingDaytimePolicy, setpoint=71.5))
	climateController.addScheduledConfig(ClimateController.MODE_COOL, ClimateControllerConfig(policy=CoolingBedtimePolicy, setpoint=71.5), startTime=time(hour=20, minute=00), endTime=time(hour=7))

	#billDetector = iCloudAwayDetector("wkatsak@cs.rutgers.edu", "Bill1085")
	#firuzaDetector = iCloudAwayDetector("firuzaa8@gmail.com", "Bill1085")
	#arturDetector = iCloudAwayDetector("abramyan62@icloud.com", "Artur1962")

	#climateController.addAwayDetector("Bill", billDetector)
	#climateController.addAwayDetector("Firuza", firuzaDetector)
	#climateController.addAwayDetector("Artur", arturDetector)

	climateController.start()
	common.controller = climateController
	flaskThread = FlaskThread()
	flaskThread.start()

	climateController.shell()

	climateController.stop()
	zwaveController.stop()
	sys.exit()
