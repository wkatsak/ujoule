set terminal png size 1500,900
set output "temps.png"
set yrange [55:90]
set y2range [-10:140]
set ytics nomirror
set y2tics
set ylabel "Inside Temperature (F)"
set y2label "Outside Temperature (F)"
set timefmt "%s" 
set format x "%H:%M"
set xdata time

#set style rect fc lt -1 fs solid 0.15 noborder
set style rect fc lt -1 fs solid
load "heat-rects.gp"

plot "data/sensor-livingroom-last.dat" using 1:($2) with lines axes x1y1, \
	"data/sensor-bedroom-last.dat" using 1:($2) with lines axes x1y1, \
	"data/sensor-office-last.dat" using 1:($2) with lines axes x1y1, \
	"data/setpoint-last.dat" using 1:($2) with lines axes x1y1, \
	"data/sensor-outside-last.dat" using 1:($2) with lines axes x1y2
