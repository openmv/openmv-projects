# This file is part of the OpenMV project.
# Copyright (c) 2013-2017 Ibrahim Abdelkader <iabdalkader@openmv.io> & Kwabena W. Agyeman <kwagyeman@openmv.io>
# This work is licensed under the MIT license, see the file LICENSE for details.

###########
# Settings
###########

COLOR_LINE_FOLLOWING = True # False to use grayscale thresholds, true to use color thresholds.
COLOR_THRESHOLDS = [(20, 100, -20, 20, 20, 127)] # Yellow Line.
GRAYSCALE_THRESHOLDS = [(240, 255)] # White Line.
BINARY_VIEW = True # Helps debugging but costs FPS if on.
DO_NOTHING = False # Just capture frames...

MAG_THRESHOLD = 5 # Raise to filter out false detections.
THETA_AVERAGE_WINDOW_SIZE = 4 # Sliding window of averages of this size.
RHO_AVERAGE_WINDOW_SIZE = 4 # Sliding window of averages of this size.

# Tweak these values for your robocar.
THROTTLE_CUT_OFF_ANGLE = 10.0 # Maximum angular distance from 90 before we cut speed [0.0-90.0).
THROTTLE_CUT_OFF_RATE = 0.5 # How much to cut our speed boost (below) once the above is passed (0.0-1.0].
THROTTLE_GAIN = 2.0 # e.g. how much to speed up on a straight away
THROTTLE_OFFSET = 23.0 # e.g. default speed
THROTTLE_P_GAIN = 1.0
THROTTLE_I_GAIN = 0.0
THROTTLE_I_MIN = -0.0
THROTTLE_I_MAX = 0.0
THROTTLE_D_GAIN = 0.0

# Tweak these values for your robocar.
STEERING_BOOST_ANGLE = 30.0 # Once we need to turn more than this then boost our turn output [0.0-90.0).
STEERING_BOOST_RATE = 0.5 # How much to boost our turn by (percentage) (0.0-1.0] for 100% to 200%.
STEERING_THETA_GAIN = 30.0
STEERING_RHO_GAIN = -1.0
STEERING_P_GAIN = 0.4
STEERING_I_GAIN = 0.0
STEERING_I_MIN = -0.0
STEERING_I_MAX = 0.0
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

THETA_AVERAGE_WINDOW_SIZE = max(THETA_AVERAGE_WINDOW_SIZE, 1)
RHO_AVERAGE_WINDOW_SIZE = max(RHO_AVERAGE_WINDOW_SIZE, 1)

THROTTLE_CUT_OFF_ANGLE = max(min(THROTTLE_CUT_OFF_ANGLE, 89.99), 0)
THROTTLE_CUT_OFF_RATE = max(min(THROTTLE_CUT_OFF_RATE, 1.0), 0.01)

STEERING_BOOST_ANGLE = max(min(STEERING_BOOST_ANGLE, 89.99), 0)
STEERING_BOOST_RATE = max(min(STEERING_BOOST_RATE, 1.0), 0.01)

# Handle if these were reversed...
tmp = max(THROTTLE_SERVO_MIN_US, THROTTLE_SERVO_MAX_US)
THROTTLE_SERVO_MIN_US = min(THROTTLE_SERVO_MIN_US, THROTTLE_SERVO_MAX_US)
THROTTLE_SERVO_MAX_US = tmp

# Handle if these were reversed...
tmp = max(STEERING_SERVO_MIN_US, STEERING_SERVO_MAX_US)
STEERING_SERVO_MIN_US = min(STEERING_SERVO_MIN_US, STEERING_SERVO_MAX_US)
STEERING_SERVO_MAX_US = tmp

# This function maps the output of the linear regression function to a driving vector for steering
# the robocar. See https://openmv.io/blogs/news/linear-regression-line-following for more info.

t_average = []
r_average = []

def figure_out_my_steering(line, img):
    global t_average
    global r_average

    # Sliding window average. Way easier to do in python versus C.
    t_average.append(line.theta())
    if len(t_average) > THETA_AVERAGE_WINDOW_SIZE: t_average.pop(0)
    t = sum(t_average) / len(t_average)

    # Sliding window average. Way easier to do in python versus C.
    r_average.append(line.rho())
    if len(r_average) > RHO_AVERAGE_WINDOW_SIZE: r_average.pop(0)
    r = sum(r_average) / len(r_average)

    # Step 1: Undo negative rho: [theta + 0, -rho] == [theta + 180, +rho]

    if r < 0:
        t += 180
        r = -r

    # Step 2: Determine the driving direction for the quadrant theta is in.

    t_reflected = 0

    if t < 45: # Quadrant 1 (The first 90 degrees are split into two 45 degree quadrants)
        t_reflected = 180 - t

    elif t < 90: # Quadrant 2 (The first 90 degrees are split into two 45 degree quadrants)
        t_reflected = t - 180

    elif t < 180: # Quadrant 3 (90 to 179)
        t_reflected = 180 - t

    else: # Quadrant 4 (270 to 359 degrees - 180 to 269 never happens)
        t_reflected = t

    # Step 3: We need two error function outputs to drive the robocar. One that tries to make the
    # slope of the line zero and another that tries to center the line in the middle of the field
    # of view. Both of these error outputs will then be mixed togheter using different gains and
    # feed into a PID controller in the main loop.

    # sin() produces a larger error output as the slope of the line grows...
    t_result = math.sin(math.radians(t_reflected))

    # Assuming the slope of the line is zero then cos(t) should be one. One multiplied by rho()
    # gives you the position of the line on the screen. We then subtract where the line should
    # be (the center) to get an error output.
    r_result = math.cos(math.radians(t)) *  (r - (img.width() / 2))

    return (t_result * STEERING_THETA_GAIN) + (r_result * STEERING_RHO_GAIN)

# Solve: STEERING_BOOST_RATE = pow(sin(90 +/- STEERING_BOOST_ANGLE), x) for x...
#        -> sin(90 +/- STEERING_BOOST_ANGLE) = cos(STEERING_BOOST_ANGLE)
s_power = math.log(STEERING_BOOST_RATE) / math.log(math.cos(math.radians(STEERING_BOOST_ANGLE)))

def figure_out_my_steering_boost(steering): # steering -> [0:180]

    # 2 - pow(sin()) of the steering angle is only one when driving straight... e.g. steering ~= 0
    s_result = 2 - math.pow(math.sin(math.radians(max(min(steering, 179.99), 0.0))), s_power)

    return s_result * steering # This increases steering by up to 2x...

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
sensor.set_pixformat(sensor.RGB565 if COLOR_LINE_FOLLOWING else sensor.GRAYSCALE)
sensor.set_framesize(sensor.QQVGA)
sensor.set_vflip(True)
sensor.set_hmirror(True)
sensor.skip_frames(time = 0)
if COLOR_LINE_FOLLOWING: sensor.set_auto_gain(False)
if COLOR_LINE_FOLLOWING: sensor.set_auto_whitebal(False)
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
    img = sensor.snapshot() if COLOR_LINE_FOLLOWING else sensor.snapshot().histeq()
    if BINARY_VIEW: img = img.binary(COLOR_THRESHOLDS if COLOR_LINE_FOLLOWING else GRAYSCALE_THRESHOLDS)
    if DO_NOTHING: continue

    # We call get regression below to get a robust linear regression of the field of view. This returns
    # a line object which we can use to steer. Note that the ROI is set to the bottom 3/4ths of the
    # screen because the top quater of the image is most likely not part of the road.
    line = img.get_regression(([(50, 100, -128, 127, -128, 127)] if BINARY_VIEW else COLOR_THRESHOLDS) \
           if COLOR_LINE_FOLLOWING else ([(127, 255)] if BINARY_VIEW else GRAYSCALE_THRESHOLDS), \
           robust = True, roi = (0, sensor.height() // 4, sensor.width(), sensor.height()))
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
        steering_output = 90 + max(min(round(steering_pid_output), 90), -90)
        steering_output = figure_out_my_steering_boost(steering_output)
        steering_output = max(min(round(steering_output), 180), 0)

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
        print_string = "Line Lost - throttle %d, steering %d" % \
            (throttle_output , steering_output)

    set_servos(throttle_output, steering_output)
    print("FPS %f, %s" % (clock.fps(), print_string))
