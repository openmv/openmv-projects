# This file is part of the OpenMV project.
# Copyright (c) 2013-2017 Ibrahim Abdelkader <iabdalkader@openmv.io> & Kwabena W. Agyeman <kwagyeman@openmv.io>
# This work is licensed under the MIT license, see the file LICENSE for details.

###########
# Settings
###########

COLOR_OBSTACLE_DETECTION = True # False to use grayscale thresholds, true to use color thresholds.
COLOR_THRESHOLDS = [( 70, 100,    0,  127, -128,  127)] # Hay Color.
GRAYSCALE_THRESHOLDS = [(200, 255)] # Bright things.
BINARY_VIEW = False # Helps debugging but costs FPS if on.
DO_NOTHING = False # Just capture frames...
AREA_THRESHOLD = 10 # Raise to filter out false detections.
PIXELS_THRESHOLD = 200 # Raise to filter out false detections.

# Tweak these values for your robocar.
THROTTLE_CUT_OFF_ANGLE = 10.0 # Maximum angular distance from 90 before we cut speed [0.0-90.0).
THROTTLE_CUT_OFF_RATE = 0.5 # How much to cut our speed boost (below) once the above is passed (0.0-1.0].
THROTTLE_GAIN = 3.0 # e.g. how much to speed up on a straight away
THROTTLE_OFFSET = 23.0 # e.g. default speed
THROTTLE_P_GAIN = 1.0
THROTTLE_I_GAIN = 0.0
THROTTLE_I_MIN = -0.0
THROTTLE_I_MAX = 0.0
THROTTLE_D_GAIN = 0.0

# Tweak these values for your robocar.
STEERING_BIAS = -10
STEERING_P_GAIN = -0.5
STEERING_I_GAIN = -1
STEERING_I_MIN = -10.0
STEERING_I_MAX = 10.0
STEERING_D_GAIN = 0.1

# Tweak these values for your robocar.
THROTTLE_SERVO_MIN_US = 1500
THROTTLE_SERVO_MAX_US = 2000

# Tweak these values for your robocar.
STEERING_SERVO_MIN_US = 700
STEERING_SERVO_MAX_US = 2300

###########
# Setup
###########

import sensor, image, time, math, pyb

THROTTLE_CUT_OFF_ANGLE = max(min(THROTTLE_CUT_OFF_ANGLE, 89.99), 0)
THROTTLE_CUT_OFF_RATE = max(min(THROTTLE_CUT_OFF_RATE, 1.0), 0.01)

# Handle if these were reversed...
tmp = max(THROTTLE_SERVO_MIN_US, THROTTLE_SERVO_MAX_US)
THROTTLE_SERVO_MIN_US = min(THROTTLE_SERVO_MIN_US, THROTTLE_SERVO_MAX_US)
THROTTLE_SERVO_MAX_US = tmp

# Handle if these were reversed...
tmp = max(STEERING_SERVO_MIN_US, STEERING_SERVO_MAX_US)
STEERING_SERVO_MIN_US = min(STEERING_SERVO_MIN_US, STEERING_SERVO_MAX_US)
STEERING_SERVO_MAX_US = tmp

# Find the largest blob and try to drive to keep it in the center of the field of view.
# This algorithm does not drive straight but should avoid non-ground things...
def figure_out_my_steering(blobs, img):
    biggest_blob = max(blobs, key = lambda x: x.pixels())
    img.draw_rectangle(biggest_blob.rect(), color = (255, 0, 0) if COLOR_OBSTACLE_DETECTION else 127)
    img.draw_cross(biggest_blob.cx(), biggest_blob.cy(), color = (255, 0, 0) if COLOR_OBSTACLE_DETECTION else 127)
    return biggest_blob.cx() - (img.width() / 2)

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

uart = pyb.UART(3, 19200, timeout_char = 1000)

# throttle [0:100] (101 values) -> [THROTTLE_SERVO_MIN_US, THROTTLE_SERVO_MAX_US]
# steering [0:180] (181 values) -> [STEERING_SERVO_MIN_US, STEERING_SERVO_MAX_US]
def set_servos(throttle, steering):
    throttle = THROTTLE_SERVO_MIN_US + ((throttle * (THROTTLE_SERVO_MAX_US - THROTTLE_SERVO_MIN_US + 1)) / 101)
    steering = STEERING_SERVO_MIN_US + ((steering * (STEERING_SERVO_MAX_US - STEERING_SERVO_MIN_US + 1)) / 181)
    uart.write("{%05d,%05d}\r\n" % (throttle, steering))

#
# Camera Control Code
#

sensor.reset()
sensor.set_pixformat(sensor.RGB565 if COLOR_OBSTACLE_DETECTION else sensor.GRAYSCALE)
sensor.set_framesize(sensor.QQVGA)
sensor.set_vflip(True)
sensor.set_hmirror(True)
sensor.skip_frames(time = 0)
sensor.set_auto_gain(False)
sensor.set_auto_whitebal(False)
clock = time.clock()

###########
# Loop
###########

old_time = pyb.millis()

throttle_old_result = None
throttle_i_output = 0
throttle_output = 0

steering_old_result = None
steering_i_output = 0
steering_output = 90

while True:
    clock.tick()
    img = sensor.snapshot().histeq()
    if BINARY_VIEW: img = img.binary(COLOR_THRESHOLDS if COLOR_OBSTACLE_DETECTION else GRAYSCALE_THRESHOLDS)
    if DO_NOTHING: continue

    # The key insight here is that the ground is normally more reflective than the walls or other objects.
    # So, our goal is to basically follow the brightest thing on the ground (maybe of a particular color).
    blobs = img.find_blobs(([(50, 100, -128, 127, -128, 127)] if BINARY_VIEW else COLOR_THRESHOLDS) \
        if COLOR_OBSTACLE_DETECTION else ([(127, 255)] if BINARY_VIEW else GRAYSCALE_THRESHOLDS), \
        area_threshold = AREA_THRESHOLD, pixels_threshold = PIXELS_THRESHOLD, merge = True, margin = 1, \
        roi = (0, sensor.height() // 4, sensor.width(), sensor.height())) # Bottom 3/4ths of the image only.
    print_string = ""

    if blobs:
        new_time = pyb.millis()
        delta_time = new_time - old_time
        old_time = new_time

        #
        # Figure out steering and do steering PID
        #

        steering_new_result = figure_out_my_steering(blobs, img)
        steering_delta_result = (steering_new_result - steering_old_result) if (steering_old_result != None) else 0
        steering_old_result = steering_new_result

        steering_p_output = steering_new_result # Standard PID Stuff here... nothing particularly interesting :)
        steering_i_output = max(min(steering_i_output + steering_new_result, STEERING_I_MAX), STEERING_I_MIN)
        steering_d_output = ((steering_delta_result * 1000) / delta_time) if delta_time else 0
        steering_pid_output = (STEERING_P_GAIN * steering_p_output) + \
                              (STEERING_I_GAIN * steering_i_output) + \
                              (STEERING_D_GAIN * steering_d_output)

        # Steering goes from [-90,90] but we need to output [0,180] for the servos.
        steering_output = 90 + max(min(round(steering_pid_output + STEERING_BIAS), 90), -90)

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

    print_string = "Line Lost - throttle %d, steering %d" % \
        (throttle_output , steering_output)

    set_servos(throttle_output, steering_output)
    print("FPS %f, %s" % (clock.fps(), print_string))
