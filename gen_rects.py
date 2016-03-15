#!/usr/bin/python

import sys

def outputLine(start, end):
	#y = 55, 90
	#print "set object rect from %0.2f,%0.2f to %0.2f,%0.2f" % (start, 55.0, end, 90.0)
	print "set obj rect from %0.2f, graph 0 to %0.2f, graph 1" % (start, end)

if __name__ == "__main__":

	filename = sys.argv[1]

	with open(filename, "r") as f:
		lines = f.readlines()

	currentRectStart = None
	currentRectEnd = None

	convertedLines = []

	for line in lines:
		line = line.strip()
		timestamp, value = line.split()
		timestamp = int(timestamp)
		value = float(value)
		convertedLines.append((timestamp, value))

	prevTimestamp = None
	prevValue = None
	#for i in xrange(0, len(convertedLines)):
	for timestamp, value in convertedLines:
		if value and not currentRectStart:
			currentRectStart = timestamp

		elif (prevValue and not value) and currentRectStart:
			currentRectEnd = prevTimestamp

		prevTimestamp = timestamp
		prevValue = value

		if currentRectStart and currentRectEnd:
			outputLine(currentRectStart, currentRectEnd)
			currentRectStart = None
			currentRectEnd = None

	if currentRectStart and not currentRectEnd:
		currentRectEnd = timestamp
		outputLine(currentRectStart, currentRectEnd)
