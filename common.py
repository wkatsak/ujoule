#!/usr/bin/python

import logging

UJOULE_LOUIE_SIGNAL_MAGIC = 32768

class ujouleLouieSignals(object):
	SIGNAL_TEMPERATURE_CHANGED			= UJOULE_LOUIE_SIGNAL_MAGIC | 1
	SIGNAL_TEMPERATURE_UPDATED 			= UJOULE_LOUIE_SIGNAL_MAGIC | 2
	SIGNAL_OUTSIDE_TEMPERATURE_CHANGED 	= UJOULE_LOUIE_SIGNAL_MAGIC | 4
	SIGNAL_OUTSIDE_TEMPERATURE_UPDATED 	= UJOULE_LOUIE_SIGNAL_MAGIC | 8
	SIGNAL_AWAY_STATE_CHANGED			= UJOULE_LOUIE_SIGNAL_MAGIC | 16
	SIGNAL_SETPOINT_CHANGED				= UJOULE_LOUIE_SIGNAL_MAGIC | 32
	SIGNAL_SETPOINT_UPDATED				= UJOULE_LOUIE_SIGNAL_MAGIC | 64

# base classes
class Policy(object):
	def __init__(self, controller):
		self.controller = controller
		self.logger = logging.getLogger("Policy")

	def execute(self):
		pass

class AwayDetector(object):
	def isAway(self):
		pass