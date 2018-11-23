# This file is part of the OpenMV project.
# Copyright (c) 2013-2017 Ibrahim Abdelkader <iabdalkader@openmv.io> & Kwabena W. Agyeman <kwagyeman@openmv.io>
# This work is licensed under the MIT license, see the file LICENSE for details.

import sensor, image, time, math, pyb


###########
# Settings
###########

COLOR_LINE_FOLLOWING = True # False to use grayscale thresholds, true to use color thresholds.
COLOR_THRESHOLDS = [( 94, 100,  -27,    1,   20,  127)] # Yellow Line.
GRAYSCALE_THRESHOLDS = [(240, 255)] # White Line.
COLOR_HIGH_LIGHT_THRESHOLDS = [(80, 100, -10, 10, -10, 10)]
GRAYSCALE_HIGH_LIGHT_THRESHOLDS = [(250, 255)]
BINARY_VIEW = True # Helps debugging but costs FPS if on.
DO_NOTHING = False # Just capture frames...
FRAME_SIZE = sensor.QQVGA # Frame size.
FRAME_REGION = 0.75 # Percentage of the image from the bottom (0 - 1.0).
FRAME_WIDE = 1.0 # Percentage of the frame width.

AREA_THRESHOLD = 0 # Raise to filter out false detections.
PIXELS_THRESHOLD = 40 # Raise to filter out false detections.
MAG_THRESHOLD = 4 # Raise to filter out false detections.
MIXING_RATE = 0.9 # Percentage of a new line detection to mix into current steering.

# Tweak these values for your robocar.
THROTTLE_CUT_OFF_ANGLE = 1.0 # Maximum angular distance from 90 before we cut speed [0.0-90.0).
THROTTLE_CUT_OFF_RATE = 0.5 # How much to cut our speed boost (below) once the above is passed (0.0-1.0].
THROTTLE_GAIN = 0.0 # e.g. how much to speed up on a straight away
THROTTLE_OFFSET = 30.0 # e.g. default speed (0 to 100)
THROTTLE_P_GAIN = 1.0
THROTTLE_I_GAIN = 0.0
THROTTLE_I_MIN = -0.0
THROTTLE_I_MAX = 0.0
THROTTLE_D_GAIN = 0.0

# Tweak these values for your robocar.
STEERING_OFFSET = 90 # Change this if you need to fix an imbalance in your car (0 to 180).
STEERING_P_GAIN = -15.0 # Make this smaller as you increase your speed and vice versa.
STEERING_I_GAIN = 0.0
STEERING_I_MIN = -0.0
STEERING_I_MAX = 0.0
STEERING_D_GAIN = -12 # Make this larger as you increase your speed and vice versa.

# Selects motor/servo controller method...
ARDUINO_SERVO_CONTROLLER = False

NATIVE_SERVO_CONTROLLER = True

NATIVE_MOTOR_CONTROLLER = False

# Tweak these values for your robocar if you're using servos.
THROTTLE_SERVO_MIN_US = 1500
THROTTLE_SERVO_MAX_US = 2000

# Tweak these values for your robocar.
STEERING_SERVO_MIN_US = 700
STEERING_SERVO_MAX_US = 2300

###########
# Setup
###########

FRAME_REGION = max(min(FRAME_REGION, 1.0), 0.0)
FRAME_WIDE = max(min(FRAME_WIDE, 1.0), 0.0)
MIXING_RATE = max(min(MIXING_RATE, 1.0), 0.0)

THROTTLE_CUT_OFF_ANGLE = max(min(THROTTLE_CUT_OFF_ANGLE, 89.99), 0)
THROTTLE_CUT_OFF_RATE = max(min(THROTTLE_CUT_OFF_RATE, 1.0), 0.01)

THROTTLE_OFFSET = max(min(THROTTLE_OFFSET, 100), 0)
STEERING_OFFSET = max(min(STEERING_OFFSET, 180), 0)

# Handle if these were reversed...
tmp = max(THROTTLE_SERVO_MIN_US, THROTTLE_SERVO_MAX_US)
THROTTLE_SERVO_MIN_US = min(THROTTLE_SERVO_MIN_US, THROTTLE_SERVO_MAX_US)
THROTTLE_SERVO_MAX_US = tmp

# Handle if these were reversed...
tmp = max(STEERING_SERVO_MIN_US, STEERING_SERVO_MAX_US)
STEERING_SERVO_MIN_US = min(STEERING_SERVO_MIN_US, STEERING_SERVO_MAX_US)
STEERING_SERVO_MAX_US = tmp

device = None

if ARDUINO_SERVO_CONTROLLER:
    device = pyb.UART(3, 19200, timeout_char = 1000)

if NATIVE_SERVO_CONTROLLER:
    import servo
    import machine
    device = servo.Servos(machine.I2C(sda = machine.Pin("P5"), scl = machine.Pin("P4")), address = 0x40, freq = 50)

if NATIVE_MOTOR_CONTROLLER:
    from pyb import Pin, Timer

    # these are motor driver pins, which set the direction of each motor
    pinADir0 = pyb.Pin('P0', pyb.Pin.OUT_PP, pyb.Pin.PULL_NONE)
    pinADir1 = pyb.Pin('P1', pyb.Pin.OUT_PP, pyb.Pin.PULL_NONE)
    pinBDir0 = pyb.Pin('P2', pyb.Pin.OUT_PP, pyb.Pin.PULL_NONE)
    pinBDir1 = pyb.Pin('P3', pyb.Pin.OUT_PP, pyb.Pin.PULL_NONE)

    # Dir0/1 must be not equal to each other for forward or backwards
    # operation. If they are equal then that's a brake operation.
    # If they are not equal then the motor will spin one way other the
    # other depending on its hookup and the value of channel 0.

    pinADir0.value(1)
    pinADir1.value(0)

    # Dir0/1 must be not equal to each other for forward or backwards
    # operation. If they are equal then that's a brake operation.
    # If they are not equal then the motor will spin one way other the
    # other depending on its hookup and the value of channel 0.

    pinBDir0.value(0)
    pinBDir1.value(1)

    tim = Timer(4, freq=1000) # Frequency in Hz
    ch1 = tim.channel(1, pyb.Timer.PWM, pin=pyb.Pin("P7"))
    ch2 = tim.channel(2, pyb.Timer.PWM, pin=pyb.Pin("P8"))
    cruise_speed = 50
    radians_degrees = 57.3 # constant to convert from radians to degrees
    steering_direction = 1   # use this to revers the steering if your car goes in the wrong direction
    steering_gain = 1.0  # calibration for your car's steering sensitivity
    steering_center = 0  # set to your car's steering center point

def constrain(value, min, max):
    if value < min :
        return min
    if value > max :
        return max
    else:
        return value

def steer(throttle, angle):
    global steering_gain, cruise_speed, steering_center
    angle = int(round(angle+steering_center))
    angle = constrain(angle, 0, 180)
    angle = angle - 90
    angle = radians_degrees * math.tan(angle/radians_degrees) # take the tangent to create a non-linear response curver
    angle = angle * steering_gain
    print ("Calculated angle", angle)
    left = angle*steering_direction + throttle + cruise_speed
    left = constrain (left, 0, 100)
    right = -1*angle*steering_direction + throttle + cruise_speed
    right = constrain (right, 0, 100)
    print ("left: ", left)
    print ("right: ", right)
    # Generate a 1KHz square wave on TIM4 with each channel
    ch1.pulse_width_percent(left)
    ch2.pulse_width_percent(right)


# This function maps the output of the linear regression function to a driving vector for steering
# the robocar. See https://openmv.io/blogs/news/linear-regression-line-following for more info.

old_cx_normal = None
def figure_out_my_steering(line, img):
    global old_cx_normal

    # Rho is computed using the inverse of this code below in the actual OpenMV Cam code.
    # This formula comes from the Hough line detection formula (see the wikipedia page for more).
    # Anyway, the output of this calculations below are a point centered vertically in the middle
    # of the image and to the left or right such that the line goes through it (cx may be off the image).
    cy = img.height() / 2
    cx = (line.rho() - (cy * math.sin(math.radians(line.theta())))) / math.cos(math.radians(line.theta()))

    # "cx_middle" is now the distance from the center of the line. This is our error method to stay
    # on the line. "cx_normal" normalizes the error to something like -1/+1 (it will go over this).
    cx_middle = cx - (img.width() / 2)
    cx_normal = cx_middle / (img.width() / 2)
    # Note that "cx_normal" may be larger than -1/+1. When the value is between -1/+1 this means the
    # robot is driving basically straight and needs to only turn lightly left or right. When the value
    # is outside -1/+1 it means you need to turn VERY hard to the left or right to get back on the
    # line. This maps to the case of the robot driving into a horizontal line. "cx_normal" will
    # then approach -inf/+inf depending on how horizontal the line is. What's nice is that this
    # is exactly the behavior we want and it gets up back on the line!

    if old_cx_normal != None: old_cx_normal = (cx_normal * MIXING_RATE) + (old_cx_normal * (1.0 - MIXING_RATE))
    else: old_cx_normal = cx_normal
    return old_cx_normal

# Solve: THROTTLE_CUT_OFF_RATE = pow(sin(90 +/- THROTTLE_CUT_OFF_ANGLE), x) for x...
#        -> sin(90 +/- THROTTLE_CUT_OFF_ANGLE) = cos(THROTTLE_CUT_OFF_ANGLE)
t_power = math.log(THROTTLE_CUT_OFF_RATE) / math.log(math.cos(math.radians(THROTTLE_CUT_OFF_ANGLE)))

def figure_out_my_throttle(steering): # steering -> [0:180]

    # pow(sin()) of the steering angle is only non-zero when driving straight... e.g. steering ~= 90
    t_result = math.pow(math.sin(math.radians(max(min(steering, 179.99), 0.0))), t_power)

    return (t_result * THROTTLE_GAIN) + THROTTLE_OFFSET

#
# Servo Control Code
#



# throttle [0:100] (101 values) -> [THROTTLE_SERVO_MIN_US, THROTTLE_SERVO_MAX_US]
# steering [0:180] (181 values) -> [STEERING_SERVO_MIN_US, STEERING_SERVO_MAX_US]
def set_servos(throttle, steering):
    if NATIVE_MOTOR_CONTROLLER:
        steer(throttle, steering)
    if ARDUINO_SERVO_CONTROLLER:
        throttle = THROTTLE_SERVO_MIN_US + ((throttle * (THROTTLE_SERVO_MAX_US - THROTTLE_SERVO_MIN_US + 1)) / 101)
        steering = STEERING_SERVO_MIN_US + ((steering * (STEERING_SERVO_MAX_US - STEERING_SERVO_MIN_US + 1)) / 181)
        device.write("{%05d,%05d}\r\n" % (throttle, steering))
    if NATIVE_SERVO_CONTROLLER:
        throttle = THROTTLE_SERVO_MIN_US + ((throttle * (THROTTLE_SERVO_MAX_US - THROTTLE_SERVO_MIN_US + 1)) / 101)
        steering = STEERING_SERVO_MIN_US + ((steering * (STEERING_SERVO_MAX_US - STEERING_SERVO_MIN_US + 1)) / 181)
        device.position(0, us=throttle)
        device.position(1, us=steering)

#
# Camera Control Code
#

sensor.reset()
sensor.set_pixformat(sensor.RGB565 if COLOR_LINE_FOLLOWING else sensor.GRAYSCALE)
sensor.set_framesize(FRAME_SIZE)
sensor.set_vflip(True)
sensor.set_hmirror(True)
sensor.set_windowing((int((sensor.width() / 2) - ((sensor.width() / 2) * FRAME_WIDE)), int(sensor.height() * (1.0 - FRAME_REGION)), \
                     int((sensor.width() / 2) + ((sensor.width() / 2) * FRAME_WIDE)), int(sensor.height() * FRAME_REGION)))
sensor.skip_frames(time = 200)
if COLOR_LINE_FOLLOWING: sensor.set_auto_gain(False)
if COLOR_LINE_FOLLOWING: sensor.set_auto_whitebal(False)
clock = time.clock()
#sensor.set_auto_exposure(False, \
#    exposure_us = 300)


###########
# Loop
###########

old_time = pyb.millis()

throttle_old_result = None
throttle_i_output = 0
throttle_output = THROTTLE_OFFSET

steering_old_result = None
steering_i_output = 0
steering_output = STEERING_OFFSET

while True:
    clock.tick()
    img = sensor.snapshot()
    img.binary(COLOR_HIGH_LIGHT_THRESHOLDS if COLOR_LINE_FOLLOWING else GRAYSCALE_HIGH_LIGHT_THRESHOLDS, zero = True)
    img.histeq()

    if BINARY_VIEW: img = img.binary(COLOR_THRESHOLDS if COLOR_LINE_FOLLOWING else GRAYSCALE_THRESHOLDS)
    if BINARY_VIEW: img.erode(1, threshold = 5).dilate(1, threshold = 1)
    if DO_NOTHING: continue

    # We call get regression below to get a robust linear regression of the field of view.
    # This returns a line object which we can use to steer the robocar.
    line = img.get_regression(([(50, 100, -128, 127, -128, 127)] if BINARY_VIEW else COLOR_THRESHOLDS) if COLOR_LINE_FOLLOWING \
        else ([(127, 255)] if BINARY_VIEW else GRAYSCALE_THRESHOLDS), \
        area_threshold = AREA_THRESHOLD, pixels_threshold = PIXELS_THRESHOLD, \
        robust = True)

    print_string = ""
    if line and (line.magnitude() >= MAG_THRESHOLD):
        img.draw_line(line.line(), color = (127, 127, 127) if COLOR_LINE_FOLLOWING else 127)

        new_time = pyb.millis()
        delta_time = new_time - old_time
        old_time = new_time

        #
        # Figure out steering and do steering PID
        #

        steering_new_result = figure_out_my_steering(line, img)
        steering_delta_result = (steering_new_result - steering_old_result) if (steering_old_result != None) else 0
        steering_old_result = steering_new_result

        steering_p_output = steering_new_result # Standard PID Stuff here... nothing particularly interesting :)
        steering_i_output = max(min(steering_i_output + steering_new_result, STEERING_I_MAX), STEERING_I_MIN)
        steering_d_output = ((steering_delta_result * 1000) / delta_time) if delta_time else 0
        steering_pid_output = (STEERING_P_GAIN * steering_p_output) + \
                              (STEERING_I_GAIN * steering_i_output) + \
                              (STEERING_D_GAIN * steering_d_output)

        # Steering goes from [-90,90] but we need to output [0,180] for the servos.
        steering_output = STEERING_OFFSET + max(min(round(steering_pid_output), 180 - STEERING_OFFSET), STEERING_OFFSET - 180)

        #
        # Figure out throttle and do throttle PID
        #

        throttle_new_result = figure_out_my_throttle(steering_output)
        throttle_delta_result = (throttle_new_result - throttle_old_result) if (throttle_old_result != None) else 0
        throttle_old_result = throttle_new_result

        throttle_p_output = throttle_new_result # Standard PID Stuff here... nothing particularly interesting :)
        throttle_i_output = max(min(throttle_i_output + throttle_new_result, THROTTLE_I_MAX), THROTTLE_I_MIN)
        throttle_d_output = ((throttle_delta_result * 1000) / delta_time) if delta_time else 0
        throttle_pid_output = (THROTTLE_P_GAIN * throttle_p_output) + \
                              (THROTTLE_I_GAIN * throttle_i_output) + \
                              (THROTTLE_D_GAIN * throttle_d_output)

        # Throttle goes from 0% to 100%.
        throttle_output = max(min(round(throttle_pid_output), 100), 0)

        print_string = "Line Ok - throttle %d, steering %d - line t: %d, r: %d" % \
            (throttle_output , steering_output, line.theta(), line.rho())

    else:
        print_string = "Line Lost - throttle %d, steering %d" % (throttle_output , steering_output)

    set_servos(throttle_output, steering_output)
    print("FPS %f - %s" % (clock.fps(), print_string))
