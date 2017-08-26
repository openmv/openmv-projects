# Donkey Self-Driving Car

This instructable shows off how to create a [DIY Robocar](https://diyrobocars.com/) forked off of the ["Donkey"](https://www.donkeycar.com/) Self-Driving car platform using the OpenMV Cam instead of the RaspberryPi. You can see the car in action in this video [here](https://youtu.be/Pm88BEz3upM).

![OpenMV Cam powered Donkey Car](images/donkey-car-web.jpg "OpenMV Cam powered Donkey Car")

## Parts

The OpenMV Cam Donkey Car is designed to be easy to build out of parts that you can buy online and assemble together with basic tools. Below is the list of essential parts you'll need to build the self-driving car.

Part Description | Part Link | Part Count | Part Cost
---------------- | --------- | ---------- | ---------
1/16 2.4Ghz Exceed RC Magnet Car<br />![1/16 2.4Ghz Exceed RC Magnet Car](images/parts/magnet-car.jpg "1/16 2.4Ghz Exceed RC Magnet Car") | https://www.amazon.com/2-4Ghz-Exceed-RC-Magnet-Electric/dp/9269803775 | 1 | $79.95
Magenet Car Base Plate<br />![Magnet Car Base Plate](images/parts/base.jpg "Magnet Car Base Plate") | https://www.shapeways.com/product/6YD3XR9ND/magnet-car-base-plate<br /><br />You can download the STL file for this part [here](https://www.shapeways.com/product/download/6YD3XR9ND).<br /><br />*Magnet Base Plate by Adam Conway*. | 1 | $55.10
Magnet Car Roll Cage</br >![Magnet Car Roll Cage](images/parts/cage.jpg "Magnet Car Roll Cage") | https://www.shapeways.com/product/74VXFV7AT/magnet-car-roll-cage<br /><br />You can download the STL file for this part [here](https://www.shapeways.com/product/download/74VXFV7AT).<br /><br />*Magnet Car Roll Cage by Adam Conway*. | 1 | $66.92
OpenMV Cam Donkey Mount<br />![OpenMV Cam Donkey Mount](images/parts/camera-mount.jpg "OpenMV Cam Donkey Mount") | https://www.shapeways.com/product/G7YQBUMRC/openmv-cam-donkey-mount<br /><br />You can download the STL file for this part [here](https://www.shapeways.com/product/download/G7YQBUMRC).<br /><br />*OpenMV Cam Donkey Mount by Chris Anderson*. | 1 | $21.18
M2 Machine Screw Set<br />![M2 Machine Screw Set](images/parts/screws.jpg "M2 Machine Screw Set") | https://www.amazon.com/Glarks-280-Pieces-Phillips-Stainless-Assortment/dp/B01G0KRGXC | 1 | $11.89
M3 35mm Machine Screws<br />![M3 35mm Machine Screws](images/parts/long.jpg "M3 35mm Machine Screws") | https://www.amazon.com/M3-3mm-0-50-Stainless-MonsterBolts/dp/B016YZTEB0 | 1 | $4.00
M3 Machine Screw Nuts<br />![M3 Machine Screw Nuts](images/parts/nuts.jpg "M3 Machine Screw Nuts") | https://www.amazon.com/M3-0-5-3mm-Metric-Stainless-MonsterBolts/dp/B01528BPIU | 1 | $3.49
30 CM Servo Lead Extension Assemblies<br />![30 CM Servo Lead Extension Assemblies](images/parts/extensions.jpg "30 CM Servo Lead Extension Assemblies") | https://hobbyking.com/en_us/30cm-servo-lead-extention-jr-with-hook-26awg-5pcs-bag-1.html | 1 | $1.39
OpenMV Cam M7<br />![OpenMV Cam M7](images/parts/camera.jpg "OpenMV Cam M7") | https://openmv.io/products/openmv-cam-m7<br /><br />Note: You will need a soldering iron and solder to attach the pin headers for this part. | 1 | $65.00
OpenMV Cam Servo Shield<br />![OpenMV Cam Servo Shield](images/parts/servos.jpg "OpenMV Cam Servo Shield") | https://openmv.io/products/servo-shield<br /><br />Note: You will need a soldering iron and solder to attach the pin headers for this part. | 1 | $15.00
Zip Ties<br />![Zip Ties](images/parts/ties.jpg "Zip Ties") | https://www.amazon.com/Cable-Zip-Ties-Fastening-Organization/dp/B01LPOB2JW | 1 | $9.99
Micro USB Cable<br />![Micro USB Cable](images/parts/uusb.jpg "Micro USB Cable") | https://www.amazon.com/AmazonBasics-USB-Male-Micro-Cable/dp/B01EK87T9M | 1 | $5.99

**Sub-Total $339.90** - However, if you can 3D print parts it's significantly cheaper to build the robocar. You may also have some of the above parts lying around (like the Micro USB cable).

While the above parts list is all you need you may wish to instead control your robocar's servos using the below parts for an arduino based servo controller board which will allow you to control your robot remotely using the RC transmitter that comes with the magnet car. You don't need the servo shield above if you build your car using the below components.

Part Description | Part Link | Part Count | Part Cost
---------------- | --------- | ---------- | ---------
5V 16 MHz Arduino Pro Mini<br />![5V 16 MHz Arduino Pro Mini](images/parts/arduino.jpg "5V 16 MHz Arduino Pro Mini") | https://www.amazon.com/Arducam-Atmega328-Development-Compatible-Arduino/dp/B01981EBBA | 1 | $6.49
Arduino Pro Mini Programmer<br />![Arduino Pro Mini Programmer](images/parts/programmer.jpg "Arduino Pro Mini Programmer") | https://www.amazon.com/Micro-Basic-Breakout-Module-Arduino/dp/B00N4MCS1A | 1 | $9.95
Servo Controller Board<br />![Servo Controller Board](images/parts/controller.jpg "Servo Controller Board") | https://oshpark.com/shared_projects/2bKUWmbq<br /><br />You can download the Gerber files for this part [here](https://644db4de3505c40a0444-327723bce298e3ff5813fb42baeefbaa.ssl.cf1.rackcdn.com/ab7a7db45c3c6b37bcca1d8fc84e26e4.zip).<br /><br />*Servo Controller Board by Chris Anderson*. | 1 | $10.50 
Male Headers<br />![Male Headers](images/parts/male.jpg "Male Headers") | https://www.amazon.com/SamIdea-15-Pack-Straight-Connector-Prototype/dp/B01M9FCAXW<br /><br />Note: You will need a soldering iron and solder to attach these pin headers to the above PCB. | 1 | $5.69
8-pin Stackable Headers<br />![8-pin Stackable Headers](images/parts/headers.jpg "8-pin Stackable Headers") | https://www.amazon.com/Venel-Electronic-Component-Stackable-Shields/dp/B071454KP1<br /><br />Note: You will need a soldering iron and solder to attach these pin headers to the above PCB. | 1 | $5.08
RC Receiver Servo Adapters<br />![RC Receiver Servo Adapters](images/parts/shorts.jpg "RC Receiver Servo Adapters") | https://www.amazon.com/Hobbypower-Futaba-Servo-Extension-Cable/dp/B00RVDVWTC | 1 | $4.49
Mini USB Cable<br />![Mini USB Cable](images/parts/musb.jpg "Mini USB Cable") | https://www.amazon.com/AmazonBasics-USB-2-0-Cable-Male/dp/B00NH11N5A | 1 | $5.49

**Sub-Total $47.69** - You may have some of the above parts lying around (like the Mini USB cable).

In addition to all of the above I **heavily** recommend that your purchase a wide angle lens for your OpenMV Cam. With the wide angle lens it's much easier for your self-driving car to make tight turns and not loose sight of the road ahead. Without it you *will* have to reduce your maximum speed in-order to make tight turns.

Part Description | Part Link | Part Count | Part Cost
---------------- | --------- | ---------- | ---------
OpenMV Cam Wide Angle Lens<br />![OpenMV Cam Wide Angle Lens](images/parts/wide.jpg "OpenMV Cam Wide Angle Lens") | https://openmv.io/products/ultra-wide-angle-lens | 1 | $15.00

**Sub-Total $15.00**

Moving on, for better performance I recommend that you purchase LiPo batteries, adapters, and a LiPo charger. The NiMh battery that comes with the Magnet Car will quickly run out of power making it hard for you to test for hours before a race on the same day.

Part Description | Part Link | Part Count | Part Cost
---------------- | --------- | ---------- | ---------
Turnigy 1300mAh 2S 20C LiPo Pack<br />![Turnigy 1300mAh 2S 20C LiPo Pack](images/parts/lipo.jpg "Turnigy 1300mAh 2S 20C LiPo Pack") | https://hobbyking.com/en_us/turnigy-1300mah-2s-20c-lipo-pack-suit-1-18th-truck.html | 3 | $10.03
Tamiya Mini Female to XT60 Male Adapters<br />![Tamiya Mini Female to XT60 Male Adapters](images/parts/adapters.jpg "Tamiya Mini Female to XT60 Male Adapters") | https://hobbyking.com/en_us/female-mini-tamiya-gt-male-xt60-3pcs-bag.html | 1 | $3.36
Turnigy E3 Compact 2S/3S Lipo Charger<br />![Turnigy E3 Compact 2S/3S Lipo Charger](images/parts/lipo-charger.jpg "Turnigy E3 Compact 2S/3S Lipo Charger") | https://hobbyking.com/en_us/turnigy-e3-compact-2s-3s-lipo-charger-100-240v-us-plug.html | 1 | $12.35

**Sub-Total $45.77**

Finally, for wireless programming I recommend that you purchase a WiFi shield for the OpenMV Cam. With the WiFi shield you'll be able to comfortably test your self-driving car from one position versus having to follow your car around tethered by a USB cable.

Part Description | Part Link | Part Count | Part Cost
---------------- | --------- | ---------- | ---------
OpenMV Cam WiFi Shield<br />![OpenMV Cam WiFi Shield](images/parts/wifi.jpg "OpenMV Cam WiFi Shield") | https://openmv.io/products/wifi-shield | 1 | $35.00

*Note, as of 8/15/2017 wireless programming has not yet been implemented for the OpenMV Cam but it is comming soon.*

**Sub-Total $35.00**

## Assembly

Once you've purchased and recieved all the parts you want for your dyi robocar above you can now build it. Note that you're going to need an exacto knife, a file, a philips screw driver, pliers, a soldering iron, and some solder.

### Step 1 - Clean up parts:

Your 3D printed parts are most-likely going to need some cleanup. Using the extaco knife remove any burs on the 3D printed parts and cleanout any excess material in any of the holes in the 3D printed parts. In particular, you're going to want to make sure to clear out material left over in the slots on the sides of the roll bar.

Next, try to insert the 3D printed OpenMV Cam mount neck part into it's holder. Most-likely it's not going to be a perfect fit. So, use the file to sand the edges of the 3D printed material until the neck part fits into it's holder snuggly.

### Step 2 - Assemble the body:

The rollbar mounts to the base plate using three M2 screws and nuts - a pair for each leg on the rollbar. Additionally, feel free to use any M2 screw length that fits. Anyway, to before mounting the rollbar to the base plate make sure the screw stands on the base plate are facing up. The screw stands are for a Raspberry Pi and a servo controller which we won't be using. Moving on, to attach the rollbar to the base plate you need to insert a nut into the slots on either side of the front two rollbar legs (note that the screws are inserted from the bottom of the base plate). You then have to keep the nuts in place while screwing in the M2 screws. Doing this isn't particularly easy but doesn't require more that two hands. You may wish to use a tool to keep the nuts from spinning in their slots. After you've attached both of the front legs to the base plate you can then attach the third back leg. This should be rather easy as you can just press down on the nut from the top to keep it from spinning as you tighten the M2 screw from the bottom.

Next, attach the OpenMV Cam neck holder mount to the top of the rollbar using four more long M2 screws. Once that's on you should be able to slide the OpenMV Cam neck part into the neck mount. Since we want the most height possible for the OpenMV Cam insert one of the long M3 screws in between the neck holder and the neck part's bottom hole. Use an M3 locknut afterwards to tighten the connection to make sure the neck part is stable. Now, attach the the OpenMV Cam holder to the top of the neck part and use another long M3 screw and locknut secure the holder in place.

Finally, remove the plastic hood from your RC car. The hood is held on by four metal pin clips. Mount the base plate onto the four stands exposed after you removed the plastic hood from your RC car. The base plate should snuggly sit on the four mounting posts. If you to make sure the base plate is mounted more securely you can file down the slots on the base plate more until you can insert the four metal pins back into their holes the mounting posts.

### Step 3 - Assemble the head:

Now we're going to attach the OpenMV Cam to the body. First, remove the lens mount from your OpenMV Cam using a screw driver and clean off the camera IC under the lens mount using some isopropyl alchol and a microfiber cloth. Make sure to get off any dirt and don't leave any fibers on the camera IC. Then reattach the lens mount. Next, we need to solder the pin headers onto the OpenMV Cam that it comes with. Using a soldering iron attach the two 8-pin headers on each side of the camera so that the 8-pin header legs are sticking out the back of the OpenMV Cam. Finally, if you bought the wide angle lens above replace the lens that your OpenMV Cam comes with with the wide angle lens.

Next, let's build up the servo shield for your OpenMV Cam so that it can control the RC car. You need to solder on the two 8-pin headers on either side of the servo controller board with the pin legs facing down. Then, solder on the two servo connection headers. The plastic parts on each header should be vertical and not flat against the servo controller board.

If you bought a WiFi shield let's build that up too. Solder the two 8-pin headers it came with on either side of it with the legs facing down.

Finally, let's stack everything up. You can mount shields on the OpenMV Cam from either the top or bottom of the board. Let's put the WiFi shield on the top of the OpenMV Cam and the servo shield on the bottom. However, let's use some of those extra 8-pin headers we have to space out the servo shield from the OpenMV Cam so we have more space to mount it to the body. So, insert an extra 8-pin header on each side of the OpenMV Cam between the OpenMV Cam and the servo shield connection.

### Step 4 - Putting it together:

Attach the OpenMV Cam using it's two screw mounting holes to the OpenMV Cam mount on the top of the robocar body. To give yourself more freedom mount the OpenMV Cam upside down. You'll be able to rotate the OpenMV Cam's field of view in software.

Next, using the servo extension header attach channels 0 and 1 from the servo shield to the throttle and steering servo wires respectively. Make sure to thread the servo extension wires through the hole in the base plate.

Now, let's tiddy everything up. Use the zip ties to tie down all your wires so they aren't swaying everywhere. You don't want your robocar accidentally destroying itself by running over one of its wires.

Finally, if you bought the battery upgrade option remove the NiMh battery from your robocar and install the lipo battery with the XT60 to Tamiya adapter.

### Step 5 - Installing the software:

Because you're using the OpenMV Cam this is going to be the easiest part. Download OpenMV IDE from [here](https://openmv.io/pages/download) and install it on your laptop. Once that's done attach the micro usb cable to your OpenMV Cam and to your laptop. Next, launch OpenMV IDE and hit the connect button the bottom left hand corner of the IDE. After doing so OpenMV IDE should display on the bottom right hand corner that your OpenMV Cam's firmware is out of date. Click on the text and walk through the dialog to update your OpenMV Cam's firmware. When OpenMV IDE asks you if you want to erase the OpenMV Cam's flash drive select yes. After doing all of this download the code for the robocar [here](https://github.com/openmv/openmv-projects/blob/master/donkey-car/main.py) and open the script in OpenMV IDE. How the script works is documented in the comments.

Finally, the run the script click the run button on OpenMV IDE in the lower left-hand corner and your robocar should come to life! Once you're done tweaking settings go to ``Tools->Save open script to OpenMV Cam`` and save the script while keeping comments. Then ``Tools->Reset OpenMV Cam``. You can now disconnect your OpenMV Cam from your laptop and it will run the script by itself. Follow the above two steps each time you want your OpenMV Cam to run the script without the laptop attached to it. For quick testing and debug while your laptop is connected just use the run button and stop button.

### Optional Step 1 - Building the Arduino based Servo Controller:

If you opted to get the Arduino based Servo Controller so you can use your RC controller to act as a kill switch for your robocar (which is a good idea) here's how to build it.

First, solder two 8-pin female headers onto either side of the servo controller board. Note that since we want this servo controller to mount onto the back of the OpenMV Cam we're going to do this in reverse. The female side of these headers should be on the side of the PCB that says ``123D Circuits``. Next, on the Arduino Pro Mini solder male pin headers facing down on either side of it. As for the row of pin headers that go across it on it's back solder male pin headers there facing up. Finally, solder the Arduino Pro Mini to the servo controller board such that the button on it is over the row of holes going across the bottom of the servo controller board.

Now, install male pin headers facing up on the servo controller board in all the available remaining holes not covered by the Arduino Pro Mini. The only holes that should have anything in them are the eight holes going across the bottom of the servo controller board under the Arduino Pro Mini.

Finally mount the Arduino based Servo Controller board to the back of your OpenMV Cam. You'll want to use two of the extra 8-pin female headers to act as spacers between the OpenMV Cam and the servo controller board. Note that the servo controller board should mount such that it's not sticking out of the OpenMV Cam's form factor.


