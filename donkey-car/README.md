# Donkey Self-Driving Car

This instructable shows off how to create a [DIY Robocar](https://diyrobocars.com/) forked off of the ["Donkey"](http://www.donkeycar.com/) Self-Driving car platform using the OpenMV Cam instead of the RaspberryPi. You can see the car in action in this video [here](https://youtu.be/Pm88BEz3upM).

![OpenMV Cam powered Donkey Car](images/donkey-car-web.jpg "OpenMV Cam powered Donkey Car")

## Parts

The OpenMV Cam Donkey Car is designed to be easy to build out of parts that you can buy online and assemble together with basic tools. Below is the list of essential parts you'll need to build the self-driving car.

Part Description | Part Link | Part Count | Part Cost
---------------- | --------- | ---------- | ---------
1/16 2.4Ghz Exceed RC Magnet Car<br />![1/16 2.4Ghz Exceed RC Magnet Car](images/parts/magnet-car.jpg "1/16 2.4Ghz Exceed RC Magnet Car") | https://www.amazon.com/2-4Ghz-Exceed-RC-Magnet-Electric/dp/9269803775 | 1 | $79.95
Magnet Car Base Plate<br />![Magnet Car Base Plate](images/parts/base.jpg "Magnet Car Base Plate") | https://www.shapeways.com/product/6YD3XR9ND/magnet-car-base-plate<br /><br />You can download the STL file for this part [here](download/Magnet_Plate_v7.stl).<br /><br />*Magnet Base Plate by Adam Conway*. | 1 | $55.10
Magnet Car Roll Cage</br >![Magnet Car Roll Cage](images/parts/cage.jpg "Magnet Car Roll Cage") | https://www.shapeways.com/product/74VXFV7AT/magnet-car-roll-cage<br /><br />You can download the STL file for this part [here](download/Magnet_Roll_Cage_v2.stl).<br /><br />*Magnet Car Roll Cage by Adam Conway*. | 1 | $66.92
OpenMV Cam Donkey Mount<br />![OpenMV Cam Donkey Mount](images/parts/camera-mount.jpg "OpenMV Cam Donkey Mount") | https://www.shapeways.com/product/G7YQBUMRC/openmv-cam-donkey-mount<br /><br />You can download the STL file for these parts [here](download/OpenMV_Donkey_Mount.stl).<br /><br />*OpenMV Cam Donkey Mount by Chris Anderson*. | 1 | $21.18
M2 Machine Screw Set<br />![M2 Machine Screw Set](images/parts/screws.jpg "M2 Machine Screw Set") | https://www.amazon.com/Glarks-280-Pieces-Phillips-Stainless-Assortment/dp/B01G0KRGXC | 1 | $11.89
M3 35mm Machine Screws<br />![M3 35mm Machine Screws](images/parts/long.jpg "M3 35mm Machine Screws") | https://www.amazon.com/M3-3mm-0-50-Stainless-MonsterBolts/dp/B016YZTEB0 | 1 | $4.00
M3 Machine Screw Nuts<br />![M3 Machine Screw Nuts](images/parts/nuts.jpg "M3 Machine Screw Nuts") | https://www.amazon.com/M3-0-5-3mm-Metric-Stainless-MonsterBolts/dp/B01528BPIU | 1 | $3.49
30 CM Servo Lead Extension Assemblies<br />![30 CM Servo Lead Extension Assemblies](images/parts/extensions.jpg "30 CM Servo Lead Extension Assemblies") | http://hobbyking.com/en_us/30cm-servo-lead-extention-jr-with-hook-26awg-5pcs-bag-1.html | 1 | $1.39
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

**Sub-Total $42.20** - You may have some of the above parts lying around.

In addition to all of the above I **strongly** recommend that your purchase a wide angle lens for your OpenMV Cam. With the wide angle lens it's much easier for your self-driving car to make tight turns and not lose sight of the road ahead. Without it you *will* have to reduce your maximum speed in-order to make tight turns.

Part Description | Part Link | Part Count | Part Cost
---------------- | --------- | ---------- | ---------
OpenMV Cam Wide Angle Lens<br />![OpenMV Cam Wide Angle Lens](images/parts/wide.jpg "OpenMV Cam Wide Angle Lens") | https://openmv.io/products/ultra-wide-angle-lens | 1 | $15.00

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
OpenMV Cam WiFi Shield<br />![OpenMV Cam WiFi Shield](images/parts/wifi.jpg "OpenMV Cam WiFi Shield") | https://openmv.io/products/wifi-shield | 1 | $35.00

*Note, as of 8/15/2017 wireless programming has not yet been implemented for the OpenMV Cam but it is coming soon.*

**Sub-Total $35.00**

## Assembly

Once you've purchased and received all the parts you want for your DIY Robocar above you can now build it.

![Parts](images/build/step(1)small.jpg "Parts")

Note that you're going to need an exacto knife, a philips screw driver, pliers, a soldering iron, and some solder.

![Tools](images/build/step(2)small.jpg "Tools")

### Step 1 - Clean up parts:

Your 3D printed parts are most-likely going to need some cleanup. Using the extaco knife remove any burs on the 3D printed parts and cleanout any excess material in any of the holes in the 3D printed parts. In particular, you're going to want to make sure to clear out material left over in the slots on the sides of the roll bar.

![De-bur](images/build/step(3)small.jpg "De-bur")

Next, try to insert the 3D printed OpenMV Cam mount neck part into its holder. The parts are designed to fit snuggly so this takes a bit of work. If you're having trouble try widening the neck holder with a file. Since we want the most height for the camera you just need to get the neck mount in enough to line up the first set of holes.

![Insert](images/build/step(4)small.jpg "Insert")

### Step 2 - Assemble the body:

The rollbar mounts to the base plate using three M2 screws and nuts - a pair for each leg on the rollbar. Feel free to use any M2 screw length that fits. Moving on, before mounting the rollbar to the base plate make sure the screw stands on the base plate are facing up. The screw stands are for a Raspberry Pi and a servo controller which we won't be using, but, the screw holes shouldn't be upside down if you want to mount something else on there later on.

![Body](images/build/step(5)small.jpg "Body")

To attach the rollbar to the base plate you need to insert a nut into the slots on either side of the front two rollbar legs (note that the screws are inserted from the bottom of the base plate). You then have to keep the nuts in place while screwing in the M2 screws. Doing this isn't particularly easy. You may wish to use a tool to keep the nuts from spinning in their slots.

![Body](images/build/step(6)small.jpg "Body")

After you've attached both of the front legs to the base plate you can then attach the third back leg. This should be rather easy as you can just press down on the nut from the top to keep it from spinning as you tighten the M2 screw from the bottom.

![Last](images/build/step(7)small.jpg "Last")

Next, attach the OpenMV Cam neck holder mount to the top of the rollbar using four more medium-length M2 screws. Note that this will take some work since the screw holes are unlikely to lineup exactly. I recommend screwing in all four screws only a little bit to get them started first before screwing each one in all the way.

![Align](images/build/step(8)small.jpg "Align")

Moving on, insert one of the long M3 screws in between the neck holder and the neck part's bottom hole. Use an M3 locknut afterwards to tighten the connection to make sure the neck part is stable.

![Lock](images/build/step(9)small.jpg "Lock")

Now, attach the OpenMV Cam holder to the top of the neck part and use another long M3 screw and locknut secure the holder in place. Make sure to get the orientation right like in the picture below.

![Holder](images/build/step(10)small.jpg "Holder")

Next, remove the plastic hood from your RC car. The hood is held on by four metal pin clips. After removing the hood you should see the guts of your RC car like in the image below. We'll mount the base onto the four posts on your RC car. To secure the base we'll use the same metal clips the hood was held on with. However, we'll have to put some effort into doing this since cutouts on the base to secure the base to the RC car are tight.

![Hood](images/build/step(11)small.jpg "Hood")

So first, bend the four metal clips slightly so we can more easily get them through the holes in the mounting stands after we've attached the base.

![Clip](images/build/step(12)small.jpg "Clip")

Afterwards, cut away material using your exacto knife from the groves in the base to make space for the metal pins to go through the stand holes.

![Exacto](images/build/step(13)small.jpg "Exacto")

Finally, push each pin through each stand hole to firmly attach the base to the RC Car.

![Attach](images/build/step(14)small.jpg "Attach")

Once you've finished this your car should look like this below.

![Done](images/build/step(15)small.jpg "Done")

### Step 3 - Assemble the head:

Now we're going to assemble the OpenMV Cam head of your Robocar. First, remove the lens mount from your OpenMV Cam using a screw driver and clean off the camera IC under the lens mount using some isopropyl alcohol and a Q-Tip. Make sure to get off any dirt and don't leave any fibers on the camera IC.

![Clean-up](images/build/step(16)small.jpg "Clean-up")

Then reattach the lens mount. Next, we need to solder the pin headers onto the OpenMV Cam that it comes with. Using a soldering iron attach the two 8-pin headers on each side of the camera so that the 8-pin header legs are sticking out the back of the OpenMV Cam.

![Legs](images/build/step(17)small.jpg "Legs")

Finally, if you bought the wide angle lens above replace the lens that your OpenMV Cam comes with the wide angle lens.

![Lens](images/build/step(18)small.jpg "Lens")

Next, let's build up the servo shield for your OpenMV Cam so that it can control the RC car.

![Shield](images/build/step(19)small.jpg "Shield")

You need to solder on the two 8-pin headers on either side of the servo controller board with the pin legs facing down. Then, solder on the two servo connection headers. The plastic parts on each header should be vertical and not flat against the servo controller board.

![Soldered](images/build/step(20)small.jpg "Soldered")

If you bought a WiFi shield let's build that up too. Solder the two 8-pin headers it came with on either side of it with the legs facing down.

![WiFi](images/build/step(21)small.jpg "WiFi")

Finally, let's stack everything up. You can mount shields on the OpenMV Cam from either the top or bottom of the board. But, let's put the WiFi shield on the bottom of the OpenMV Cam and the servo shield on the top.

![Stack](images/build/step(22)small.jpg "Stack")

### Step 4 - Putting it together:

Attach the OpenMV Cam using it's two screw mounting holes to the OpenMV Cam mount on the top of the robocar body. To give ourselves more freedom we're mounting the OpenMV Cam upside down. You'll be able to un-rotate the OpenMV Cam's field of view in software.

![Mounting](images/build/step(23)small.jpg "Mounting")

Next, using the servo extension headers attach channels 0 and 1 from the servo shield to the throttle and steering servo wires respectively. Make sure to thread the servo extension wires through the hole in the base plate. Also, use the zip ties to tie down all your wires so they aren't swaying everywhere. You don't want your robocar accidentally destroying itself by running over one of its wires. Your car should like the picture below once done.

![Controller](images/build/step(24)small.jpg "Controller")

Finally, put the black tube that comes with your RC Car over the antenna to protect the antenna.

![Antenna](images/build/step(25)small.jpg "Antenna")

If you bought the LiPo battery upgrade parts let's install those next. First, attach the XT60 adapters to each LiPo battery.

![Adapters](images/build/step(26)small.jpg "Adapters")

Then, replace the NiMh battery on your RC car with one of the LiPo batteries. Make sure to place the battery with the wires going towards the front of the car like in the picture below.

![Lipo](images/build/step(27)small.jpg "Lipo")

After your done it should look like the picture below.

![Done](images/build/step(28)small.jpg "Done")

**LAST, MAKE SURE TO MOVE THE JUMPER ON YOUR ESC TO THE LIPO POSITION TOO!**

![Danger](images/build/step(29)small.jpg "Danger")

### Step 5 - Installing the software:

Because you're using the OpenMV Cam this is going to be the easiest part. Download OpenMV IDE from [here](https://openmv.io/pages/download) and install it on your laptop. Once that's done attach the micro USB cable to your OpenMV Cam and to your laptop.

![OpenMV_Cam](images/build/step(40)small.jpg "OpenMV_Cam")

Next, launch OpenMV IDE and hit the connect button the bottom left hand corner of the IDE. After doing so OpenMV IDE should display on the bottom right hand corner that your OpenMV Cam's firmware is out-of-date.

![Update](images/build/step(41).png "Update")

Click on the text and walk through the dialog to update your OpenMV Cam's firmware. When OpenMV IDE asks you if you want to erase the OpenMV Cam's flash drive select yes. Afterwards, OpenMV IDE will update your OpenMV Cam's firmware. Note that your OpenMV Cam is unbrickable, so, if anything goes wrong you can recover.

![Firmware](images/build/step(42).png "Firmware")

Now that your OpenMV Cam is updated. You need to focus the lens. Please run the hello world script (click the green run arrow) and turn the lens until the picture comes into focus on the frame buffer viewer in OpenMV IDE.

![View](images/build/step(43).png "View")

After doing all of this download the code for the robocar [here](https://github.com/openmv/openmv-projects/blob/master/donkey-car/line_follower_main.py) and open the script in OpenMV IDE. How the script works is documented in the comments. Note that you need to set the ``ARDUINO_SERVO_CONTROLLER_ATTACHED`` variable to ``True`` for the OpenMV Cam to output serial data to control the Arduino Servo Controller Shield and ``False`` for the OpenMV Cam to output serial data to control the Servo Controller Shield (the non-Arduino one).

![Script](images/build/step(44).png "Script")

Finally, once you're done tweaking settings go to ``Tools->Save open script to OpenMV Cam`` and save the script while keeping comments. Then click ``Tools->Reset OpenMV Cam``. You can now disconnect your OpenMV Cam from your laptop and it will run the script by itself. Follow the above two steps each time you want your OpenMV Cam to run the script without the laptop attached to it. For quick testing and debug while your laptop is connected just use the run button and stop button to start and stop the script between edits.

*If you're using the Servo Controller Shield (the non-Arduino one), you also need to copy two scripts from OpenMV IDE to the OpenMV Cam board for things to work. Please go to ``Files->Examples->15-Servo-Shield->pca9865.py`` and save it on your OpenMV Cam's internal flash drive. Additionally, you also need to save ``Files->Examples->15-Servo-Shield->servo.py`` on your OpenMV Cam's internal flash drive. These two steps only need to be done once.*

### Optional Step 1 - Building the Arduino based Servo Controller:

If you opted to get the Arduino based Servo Controller so you can use your RC controller to act as a kill switch for your robocar (which is a **VERY** good idea) here's how to build it.

![Parts](images/build/step(30)small.jpg "Parts")

First, solder up the Arduino Pro Mini like the image below.

![Arduino](images/build/step(31)small.jpg "Arduino")

Next, solder the Arduino onto the ``123D Circuits`` circuits main board like below. We're trying to mount this onto the back of the OpenMV Cam board so the layout looks a little bit reversed. Just copy what's in the image below.

![Controller](images/build/step(32)small.jpg "Controller")

It should look like this on the bottom.

![Bottom](images/build/step(33)small.jpg "Bottom")

Now, mount the board onto the back of the OpenMV Cam shield stack-up. Note that we don't need the extra length of the board connectors coming out of the back. Feel free to trim them if you like. Or, leave them on to stack more boards. If you decide to leave them on make sure they don't short with each other.

![Stack-up](images/build/step(34)small.jpg "Stack-up")

Finally, let's connect the steering servo to channel (1) on the Arduino, the throttle servo to channel (2), the RC radio receiver steering output to channel (3), and the RC radio receiver throttle output to channel (4). Note that the RC radio receiver's steering output is channel (1) and its throttle output is channel (2). Also, you're going to need to use the short-length female-to-female RC servo wire extension cables and long extension cables to wire up the RC radio receiver to the Arduino Servo Controller board.

![Wire](images/build/step(35)small.jpg "Wire")

Once you're finished with all of this your robot should look like this below. Note that you should use the cable ties to clean-up the wiring job.

![Done](images/build/step(36)small.jpg "Done")

### Optional Step 2 - Programming the Arduino based Servo Controller:

Connect the USB to serial adapter to the 6-pin header sticking out of the top on your Arduino Pro Mini. Make sure to connect ``GND`` to ``GND`` and ``DTR`` to ``DTR``. Next, connect the micro USB cable to the USB to serial converter and your laptop.

![Programmer](images/build/step(37)small.jpg "Programmer")

Install the Arduino IDE from [here](https://www.arduino.cc/en/Main/Software). Download the servo controller code from [here](https://github.com/openmv/openmv-projects/blob/master/donkey-car/servo_controller/servo_controller.ino) and open it using the Arduino IDE. Go to ``Tools->Board`` and select ``Arduino Pro or Arduino Pro Mini`` and ``Tools->Processor`` and select ``Atmega328 (5V, 16Mhz)`` .

![Arduino_IDE](images/build/step(38).png "Arduino_IDE")

Finally, go to ``Tools->Port`` and select the COM port your USB to serial convert is connected to (it's usually the highest numbered COM port) and then click the upload button (round right arrow). The Arduino IDE should then compile the code and start programming the Arduino Pro Mini. Once it's finished remove the USB to serial converter from your Arduino Pro Mini and your servo controller board will be ready to use.

![Arduino_IDE_Done](images/build/step(39).png "Arduino_IDE_Done")

The Arduino Servo Controller board allows you to directly control the robot's throttle and steering when the OpenMV Cam isn't running using the RC transmitter. Once the OpenMV Cam starts running and sending commands to the Arduino the Arduino will only drive the steering servo if the RC transmitter is on and will only drive the throttle if the RC transmitter throttle trigger is engaged (either for going forward or backwards). At any time you can use the steering control on the RC transmitter to override the OpenMV Cam steering. Finally, for fully autonomous control just adjust the throttle trim knob on the RC transmitter after turning it on with the throttle trim knob set to zero. Make sure to set the throttle trim knob back to zero after turning off the RC transmitter.

## How does the robocar follow the line?

The OpenMV Cam uses linear regression to detect where the line is and then follow it. With the OpenMV Cam the machine vision part is simple. Most of the work the script the OpenMV Cam is running has to do with turning the line detection into servo outputs to control the robocar. You can read more about what's going on at the blog post [here](https://openmv.io/blogs/news/linear-regression-line-following).
