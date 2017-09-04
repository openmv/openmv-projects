
# Teensy 3.5/OpenMV Rover
This project was based off a couple of other rover's that I built using multi-sonar sensors for obstacle detection and avoidance.  Needless to say they eye sores with everything hanging off the platform.  For many years wanted to do something with machine vision but most of the papers and projects used stereo vision vs monocular vision.  This also required you to send back to the PC the image to process and then send the commands back.  I wanted to keep the whole system closed on the rover platform with the need for any desktop software.  That’s where the OpenMV camera came into play.  Forgot how I found out about it but when I saw it I knew I was going to start another project.

About the same time I found another project that used a web camera and OpenCV to identify objects and associated avoidance code.  Peter Neal of [Big Face Robotics](https://bigfacerobotics.wordpress.com/2014/12/18/obstacle-detection-using-opencv/) describes the process as follows:
>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;The method I am using involves capturing an image, converting it to grayscale, blurring it slightly
and then using canny edge detection to highlight the edges in the image. Using the edge detected image, starting from the left and moving 
along the width of the image in intervals, I scan from the bottom of the image until I reach a pixel that is white, indicating the first 
edge encountered. I am left with an array that contains coordinates of the first edges found in front of the robot. Using this array, I 
then look for changes in the direction of the slope of the edges that may indicate an object is present. At the moment I am ignoring 
anything in the top half of the image as anything found here will probably be far enough away from the robot to not be too concerned 
about. This will change depending on the angle of the head. If the head is looking down towards the ground, obviously everything in the 
scene may be of interest. With the changes of slope found, I then scan in both directions to try and find the edge of the object, 
indicated by a sharp change in values in the array of nearest edges.

With the help of Nyamekye over at OpenMV I was able to implement a similar method.  Instead of changing the head angle, as Mr. Neal does, I determined the center position of large gaps (you can specify the gap size in pixels in the code) and found the center point.  Using this I was able to determing the angluar position in the FOV and then transmitted over the OpenMV UART to the Teensy 3.5 which does the rest.  I did add WiFi capabality to send the images but it slows the frame rate down too much.  The results of this process is illustrated in following figure:

![EdgeDetection Test](https://github.com/mjs513/TeensyOpenMV/blob/master/images/EdgeDetectionTest.png)

Now for the Rover design itself.  I used an off the shelf tracked chasis that I picked up off ebay quite a while ago.  Couldn't find the link to the exact one that i am using but a similar one is still available, http://www.ebay.com/itm/Tracked-Robot-Smart-Car-Platform-Aluminum-alloy-Chassis-with-Dual-DC-9V-Motor-/282615264298?hash=item41cd2eb42a:g:~FQAAOSw3ntZkVza .  One of the nice things about the chasis is that it had a Hall Effector Sensor that I could use for odometry.  A little different than the quad encoders but usuable.

Angular information is passed to the T3.5 which does the Obstacle avoidance stuff. It uses a single VL53L0X TOF sensor for distance measures, a BN055 for orientation which is used for turn control once the obstacle free direction is picked, a RC TX/Receiver and a RF module for telemetry and commands. As in my other project it has an odometry module for relative tracking based on the hall effect sensors on the motors (fixed the errors in my other code). It also has a manual mode for just sending motor commands. The odometry module receives manual commands individually in the format fx, bx, ly,ry where x is distance you want to travel in cm's and y is the relative angle you want to turn. I also use odometry once a direction is picked by the detection algorithm and then move half that distance before another round of image analysis is performed.

The whole thing is powered from a single 7.4 battery.  For power to the OpenMV camera the battery power goes to a 3.3v Pololu regulator.

I designed custom break out board for the T3.5 so it would fit on a Arduino Mega type foot print with a custom IO board where I break out where i can mount Arduino break out boards.  In this case i use a Adafruit Motor Shield V2 to control the motors and a breadboard shield to hold a Adafruit TSL2561 light sensor.

If the camera can not see an edge, can happen if it gets too close to walls the obstacle avoidance algorith Tuses a modified vfh/bubble alogithm is the camera can not detect edge which relies on the VL53 sensor to get distances.


To see it in action check the video out, https://photos.app.goo.gl/JIc3378SOzJR2bSn1.  Discussion of the process and challenges can be seen in the OpenMV forum.


Source Code and this readme is found on the TeensyOpenMV github page: https://github.com/mjs513/TeensyOpenMV

Here are a couple of screen shots of the rover:
1. http://forums.openmv.io/viewtopic.php?f=5&t=276
2. http://forums.openmv.io/viewtopic.php?f=6&t=393

![Front View](https://github.com/mjs513/TeensyOpenMV/blob/master/images/Rover2.png)

![Side View](https://github.com/mjs513/TeensyOpenMV/blob/master/images/Rover1.png)



