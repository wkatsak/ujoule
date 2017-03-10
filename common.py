#!/usr/bin/python

import logging
import inspect

# common reference to controller for flask
controller = None

UJOULE_LOUIE_SIGNAL_MAGIC = 2**32

class ujouleLouieSignals(object):
	SIGNAL_TEMPERATURE_CHANGED					= UJOULE_LOUIE_SIGNAL_MAGIC | 2**0
	SIGNAL_TEMPERATURE_UPDATED 					= UJOULE_LOUIE_SIGNAL_MAGIC | 2**1
	SIGNAL_OUTSIDE_TEMPERATURE_CHANGED 			= UJOULE_LOUIE_SIGNAL_MAGIC | 2**2
	SIGNAL_OUTSIDE_TEMPERATURE_UPDATED 			= UJOULE_LOUIE_SIGNAL_MAGIC | 2**3
	SIGNAL_AWAY_STATE_CHANGED					= UJOULE_LOUIE_SIGNAL_MAGIC | 2**4
	SIGNAL_AWAY_STATE_UPDATED					= UJOULE_LOUIE_SIGNAL_MAGIC | 2**5
	SIGNAL_SETPOINT_CHANGED						= UJOULE_LOUIE_SIGNAL_MAGIC | 2**6
	SIGNAL_SETPOINT_UPDATED						= UJOULE_LOUIE_SIGNAL_MAGIC | 2**7
	SIGNAL_POLICY_CHANGED						= UJOULE_LOUIE_SIGNAL_MAGIC | 2**8
	SIGNAL_POLICY_UPDATED						= UJOULE_LOUIE_SIGNAL_MAGIC | 2**9
	SIGNAL_HEAT_ON_CHANGED						= UJOULE_LOUIE_SIGNAL_MAGIC | 2**10
	SIGNAL_HEAT_ON_UPDATED						= UJOULE_LOUIE_SIGNAL_MAGIC | 2**11
	SIGNAL_FAN_ON_CHANGED						= UJOULE_LOUIE_SIGNAL_MAGIC | 2**12
	SIGNAL_FAN_ON_UPDATED						= UJOULE_LOUIE_SIGNAL_MAGIC | 2**13
	SIGNAL_RELATIVE_HUMIDITY_CHANGED			= UJOULE_LOUIE_SIGNAL_MAGIC | 2**14
	SIGNAL_RELATIVE_HUMIDITY_UPDATED			= UJOULE_LOUIE_SIGNAL_MAGIC | 2**15
	SIGNAL_OUTSIDE_RELATIVE_HUMIDITY_CHANGED	= UJOULE_LOUIE_SIGNAL_MAGIC | 2**16
	SIGNAL_OUTSIDE_RELATIVE_HUMIDITY_UPDATED	= UJOULE_LOUIE_SIGNAL_MAGIC | 2**17

# base classes
class Policy(object):
	def __init__(self, controller):
		self.controller = controller
		self.logger = getLogger(self)

	def execute(self):
		pass

class AwayDetector(object):
	def isAway(self):
		pass

def getLogger(instance):
	return logging.getLogger("%s" % instance.__class__.__name__)

def getObjectName(obj):

	return str(obj)

	'''
	if not obj:
		return "None"
	elif inspect.isclass(obj):
		return obj.__class__.__name__
	else:
		return obj.__name__
	'''
