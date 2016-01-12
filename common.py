#!/usr/bin/python

import logging
import inspect

UJOULE_LOUIE_SIGNAL_MAGIC = 32768

class ujouleLouieSignals(object):
	SIGNAL_TEMPERATURE_CHANGED			= UJOULE_LOUIE_SIGNAL_MAGIC | 1
	SIGNAL_TEMPERATURE_UPDATED 			= UJOULE_LOUIE_SIGNAL_MAGIC | 2
	SIGNAL_OUTSIDE_TEMPERATURE_CHANGED 	= UJOULE_LOUIE_SIGNAL_MAGIC | 4
	SIGNAL_OUTSIDE_TEMPERATURE_UPDATED 	= UJOULE_LOUIE_SIGNAL_MAGIC | 8
	SIGNAL_AWAY_STATE_CHANGED			= UJOULE_LOUIE_SIGNAL_MAGIC | 16
	SIGNAL_AWAY_STATE_UPDATED			= UJOULE_LOUIE_SIGNAL_MAGIC | 32
	SIGNAL_SETPOINT_CHANGED				= UJOULE_LOUIE_SIGNAL_MAGIC | 64
	SIGNAL_SETPOINT_UPDATED				= UJOULE_LOUIE_SIGNAL_MAGIC | 128
	SIGNAL_POLICY_CHANGED				= UJOULE_LOUIE_SIGNAL_MAGIC | 256
	SIGNAL_POLICY_UPDATED				= UJOULE_LOUIE_SIGNAL_MAGIC | 512

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
	if not obj:
		return "None"
	elif inspect.isclass(obj):
		return obj.__class__.__name__
	else:
		return obj.__name__
