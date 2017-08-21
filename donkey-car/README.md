# Donkey Self-Driving Car

This instructable shows off how to create a [DYI Robocar](http://diyrobocars.com/) forked off of the ["Donkey"](http://www.donkeycar.com/) Self-Driving car platform using the OpenMV Cam instead of the RaspberryPi. You can see the car in action in this video [here](http://youtu.be/Pm88BEz3upM).

![OpenMV Cam powered Donkey Car](images/donkey-car-web.jpg "OpenMV Cam powered Donkey Car")

## Parts

The OpenMV Cam Donkey Car is designed to be easy to build out of parts that you can buy online and assemble together with basic tools. Below is the list of essential parts you'll need to build the self-driving car.

Part Description | Part Link | Part Count | Part Cost
---------------- | --------- | ---------- | ---------
1/16 2.4Ghz Exceed RC Magnet Car<br />![1/16 2.4Ghz Exceed RC Magnet Car](images/parts/magnet-car.jpg "1/16 2.4Ghz Exceed RC Magnet Car") | http://www.amazon.com/2-4Ghz-Exceed-RC-Magnet-Electric/dp/9269803775 | 1 | $79.95
Magenet Car Base Plate<br />![Magnet Car Base Plate](images/parts/base.jpg "Magnet Car Base Plate") | http://www.shapeways.com/product/6YD3XR9ND/magnet-car-base-plate<br /><br />If you have a 3D printer you can print this part instead of buying it by downloading the STL file for the part which you can find at the above link. | 1 | $55.10
Magnet Car Roll Cage</br >![Magnet Car Roll Cage](images/parts/cage.jpg "Magnet Car Roll Cage") | http://www.shapeways.com/product/74VXFV7AT/magnet-car-roll-cage<br /><br />If you have a 3D printer you can print this part instead of buying it by downloading the STL file for the part which you can find at the above link. | 1 | $66.92
OpenMV Cam Donkey Mount<br />![OpenMV Cam Donkey Mount](images/parts/camera-mount.jpg "OpenMV Cam Donkey Mount") | http://www.shapeways.com/product/G7YQBUMRC/openmv-cam-donkey-mount<br /><br />If you have a 3D printer you can print this part instead of buying it by downloading the STL file for the part which you can find at the above link. | 1 | $21.18
30 CM Servo Lead Extension Assemblies<br />![30 CM Servo Lead Extension Assemblies](images/parts/extensions.jpg "30 CM Servo Lead Extension Assemblies") | http://hobbyking.com/en_us/30cm-servo-lead-extention-jr-with-hook-26awg-5pcs-bag-1.html | 1 | $1.39
OpenMV Cam M7<br />![OpenMV Cam M7](images/parts/camera.jpg "OpenMV Cam M7") | http://openmv.io/products/openmv-cam-m7<br /><br />Note: You will need a soldering iron and solder to solder the pin headers for this part on. | 1 | $65.00
OpenMV Cam Servo Shield<br />![OpenMV Cam Servo Shield](images/parts/servos.jpg "OpenMV Cam Servo Shield") | http://openmv.io/products/servo-shield<br /><br />Note: You will need a soldering iron and solder to solder the pin headers for this part on. | 1 | $15.00

**Sub-Total $xx.xx**

While the above parts list is all you need you may wish to instead control your robocar's servos using the below parts for an arduino based servo controller board which will allow you to control your robot remotely using the RC transmitter that comes with the magnet car. You don't need the servo shield above if you build your car using the below components.

Part Description | Part Link | Part Count | Part Cost
---------------- | --------- | ---------- | ---------

**Sub-Total $xx.xx**

In addition to all of the above I **heavily** recommend that your purchase a wide angle lens for your OpenMV Cam. With the wide angle lens it's much easier for your self-driving car to make tight turns and not loose sight of the road ahead. Without it you *will* have to reduce your maximum speed in-order to make tight turns.

Part Description | Part Link | Part Count | Part Cost
---------------- | --------- | ---------- | ---------
OpenMV Cam Wide Angle Lens<br />![OpenMV Cam Wide Angle Lens](images/parts/wide.jpg "OpenMV Cam Wide Angle Lens") | http://openmv.io/collections/products/products/ultra-wide-angle-lens | 1 | $15.00

**Sub-Total $15.00**

Moving on, for better performance I recommend that you purchase LiPo batteries, adapters, and a LiPo charger. The NiMh battery that comes with the Magnet Car will quickly run out of power making it hard for you to test for hours before a race on the same day.

Part Description | Part Link | Part Count | Part Cost
---------------- | --------- | ---------- | ---------
Turnigy 1300mAh 2S 20C LiPo Pack<br />![Turnigy 1300mAh 2S 20C LiPo Pack](images/parts/lipo.jpg "Turnigy 1300mAh 2S 20C LiPo Pack") | http://hobbyking.com/en_us/turnigy-1300mah-2s-20c-lipo-pack-suit-1-18th-truck.html | 3 | $10.03
Tamiya Mini Female to XT60 Male Adapters<br />![Tamiya Mini Female to XT60 Male Adapters](images/parts/adapters.jpg "Tamiya Mini Female to XT60 Male Adapters") | http://hobbyking.com/en_us/female-mini-tamiya-gt-male-xt60-3pcs-bag.html | 1 | $3.36
Turnigy E3 Compact 2S/3S Lipo Charger<br />![Turnigy E3 Compact 2S/3S Lipo Charger](images/parts/lipo-charger.jpg "Turnigy E3 Compact 2S/3S Lipo Charger") | http://hobbyking.com/en_us/turnigy-e3-compact-2s-3s-lipo-charger-100-240v-us-plug.html | 1 | $12.35

**Sub-Total $45.77**

Finally, for wireless programming I recommend that you purchase a WiFi shield for the OpenMV Cam. With the WiFi shield you'll be able to comfortably test your self-driving car from one position versus having to follow your car around tethered by a USB cable.

Part Description | Part Link | Part Count | Part Cost
---------------- | --------- | ---------- | ---------
OpenMV Cam WiFi Shield<br />![OpenMV Cam WiFi Shield](images/parts/wifi.jpg "OpenMV Cam WiFi Shield") | http://openmv.io/collections/products/products/wifi-shield | 1 | $35.00

*Note, as of 8/15/2017 wireless programming has not yet been implemented for the OpenMV Cam but it is comming soon.*

**Sub-Total $35.00**
