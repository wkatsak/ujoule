#!/usr/bin/python

from datetime import datetime
from Queue import Queue
from threading import Lock

def unix_ts(dt):
	epoch = datetime(month=1, day=1, year=1970)
	return int((dt - epoch).total_seconds())

class ujouleMessage(object)
	SHUTDOWN_QUEUE = 0
	SENSOR_UPDATE = 1
	
	def __init__(self, messageType, sensorId=None, valueName=None, valueData=None):
		self.messageType = messageType
		self.sensorId = sensorId
		self.valueName = valueName
		self.valueData = valueData

# relays ujouleMessages (or technically any object) to all registered recipients
class ujouleMessageRelay(object):
	
	def __init__(self):
		self.queues = {}
		self.lock = Lock()
	
	# returns a queue that can be waited on for messages
	def registerRecipient(self, recipient):
		with self.lock:
			if recipient in self.queues:
				return self.queues[recipient]
			
			newQueue = Queue()
			self.queues[recipient] = newQueue
			
			return newQueue
	
	def unregisterRecipient(self, recipient):
		with self.lock:
			if not recipient in self.queues:
				return
			
			self.sendMessageInternal(recipient, uJouleMessage(uJouleMessage.SHUTDOWN_QUEUE))
			del self.queues[recipient]
	
	def sendMessage(self, message):
		with self.lock:
			for recipient in self.queues:
				self.sendMessageInternal(message, recipient)
		
	# lock must already be held when you call this
	def sendMessageInternal(self, message, recipient):
		assert recipient in self.queues
		queue = self.queues[recipient]
		queue.put(message)


class ujoulePlugin(object):
	pass