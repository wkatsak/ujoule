#!/bin/bash

HOURS=48

python lastnhrs.py "data/sensor-livingroom.dat" $HOURS
python lastnhrs.py "data/sensor-bedroom.dat" $HOURS
python lastnhrs.py "data/sensor-office.dat" $HOURS
python lastnhrs.py "data/setpoint.dat" $HOURS
python lastnhrs.py "data/sensor-outside.dat" $HOURS

python gen_rects.py data/heat.dat > heat-rects.gp
gnuplot plot_temps.plot

xdg-open temps.png