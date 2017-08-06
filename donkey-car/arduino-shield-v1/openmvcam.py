# This file is part of the OpenMV project.
# Copyright (c) 2013-2017 Ibrahim Abdelkader <iabdalkader@openmv.io> & Kwabena W. Agyeman <kwagyeman@openmv.io>
# This work is licensed under the MIT license, see the file LICENSE for details.

###########
# Settings
###########

BINARY_VIEW = True # Helps debugging but costs FPS if on.
GRAYSCALE_THRESHOLD = (240, 255)
MAG_THRESHOLD = 4 # Raise to filter out false detections.

# Tweak these values for your robocar.
THROTTLE_GAIN = 10.0 # e.g. how much to speed up on a straight away
THROTTLE_OFFSET = 20.0 # e.g. default speed
THROTTLE_P_GAIN = 1.0
THROTTLE_I_GAIN = 0.0
THROTTLE_I_MIN = -0.0
THROTTLE_I_MAX = 0.0
THROTTLE_D_GAIN = 0.1

# Tweak these values for your robocar.
STEERING_THETA_GAIN = 40.0
STEERING_RHO_GAIN = -1.0
STEERING_P_GAIN = 0.7
STEERING_I_GAIN = 0.0
STEERING_I_MIN = -0.0
STEERING_I_MAX = 0.0
STEERING_D_GAIN = 0.1

# Tweak these values for your robocar.
THROTTLE_SERVO_MIN_US = 1500
THROTTLE_SERVO_MAX_US = 2000

# Tweak these values for your robocar.
STEERING_SERVO_MIN_US = 1000
STEERING_SERVO_MAX_US = 2000

###########
# Setup
###########

import sensor, image, time, math, pyb

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
    if len(t_average) > 4: t_average.pop(0)
    t = sum(t_average) // len(t_average)

    # Sliding window average. Way easier to do in python versus C.
    r_average.append(line.rho())
    if len(r_average) > 4: r_average.pop(0)
    r = sum(r_average) // len(r_average)

    # Step 1: Undo negative rho: [theta + 0, -rho] == [theta + 180, +rho]

    if line.rho() < 0:
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
        t_reflected = t - 360

    # Step 3: We need two error function outputs to drive the robocar. One that tries to make the
    # slope of the line zero and another that tries to center the line in the middle of the field
    # of view. Both of these error outputs will then be mixed togheter using different gains and
    # feed into a PID controller in the main loop.

    # sin() produces a larger error output as the slope of the line grows...
    t_result = math.sin(math.radians(t_reflected))

    # Assuming the slope of the line is zero then cos(t) should be one. One multiplied by rho()
    # gives you the position of the line on the screen. We then subtract where the line should
    # be (the center) to get an error output.
    r_result = (math.cos(math.radians(t) * line.rho())) - (img.width() // 2)

    return (t_result * STEERING_THETA_GAIN) + (r_result * STEERING_RHO_GAIN)

def figure_out_my_throttle(steering):

    # sin() of the steering angle results in a value that falls smoothly the more we turn.
    t_result = math.sin(math.radians(steering % 180))

    return (t_result * THROTTLE_GAIN) + THROTTLE_OFFSET

#
# Servo Control Code
#

uart = pyb.UART(3, 19200, timeout_char = 1000)

# throttle [0:100] (101 values) -> [THROTTLE_SERVO_MIN_US, THROTTLE_SERVO_MAX_US]
# steering [0:180] (181 values) -> [STEERING_SERVO_MIN_US, STEERING_SERVO_MAX_US]
def set_servos(throttle, steering):
    throttle = THROTTLE_SERVO_MIN_US + ((throttle * (THROTTLE_SERVO_MAX_US - THROTTLE_SERVO_MIN_US)) / 101)
    steering = STEERING_SERVO_MIN_US + ((steering * (STEERING_SERVO_MAX_US - STEERING_SERVO_MIN_US)) / 181)
    uart.write("{%05d,%05d}\r\n" % (throttle, steering))

set_servos(0, 90) # throttle off - steering centered

#
# Camera Control Code
#

sensor.reset()
sensor.set_pixformat(sensor.GRAYSCALE)
sensor.set_framesize(sensor.QQQVGA)
sensor.set_vflip(True)
sensor.set_hmirror(True)
sensor.skip_frames(time = 2000)
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
    if BINARY_VIEW:
        img.binary([GRAYSCALE_THRESHOLD])
        img.erode(1)

    line = img.get_regression([(255, 255) if BINARY_VIEW else GRAYSCALE_THRESHOLD], robust = True)
    print_string = ""

    if line and (line.magnitude() >= MAG_THRESHOLD):
        img.draw_line(line.line(), color = 127)

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
        steering_d_output = (steering_delta_result * 1000) / delta_time
        steering_pid_output = (STEERING_P_GAIN * steering_p_output) + \
                              (STEERING_I_GAIN * steering_i_output) + \
                              (STEERING_D_GAIN * steering_d_output)

        # Steering goes from [-90,90] but we need to output [0,180] for the servos.
        steering_output = 90 + max(min(int(steering_pid_output), 90), -90)

        #
        # Figure out throttle and do throttle PID
        #

        throttle_new_result = figure_out_my_throttle(steering_output)
        throttle_delta_result = (throttle_new_result - throttle_old_result) if (throttle_old_result != None) else 0
        throttle_old_result = throttle_new_result

        throttle_p_output = throttle_new_result # Standard PID Stuff here... nothing particularly interesting :)
        throttle_i_output = max(min(throttle_i_output + throttle_new_result, THROTTLE_I_MAX), THROTTLE_I_MIN)
        throttle_d_output = (throttle_delta_result * 1000) / delta_time
        throttle_pid_output = (THROTTLE_P_GAIN * throttle_p_output) + \
                              (THROTTLE_I_GAIN * throttle_i_output) + \
                              (THROTTLE_D_GAIN * throttle_d_output)

        # Throttle goes from 0% to 100%.
        throttle_output = max(min(int(throttle_pid_output), 100), 0)

        print_string = "Line Ok - throttle %d, steering %d - line t: %d, r: %d" % \
            (throttle_output , steering_output, line.theta(), line.rho())
    else:
        print_string = "Line Lost - throttle %d, steering %d" % \
            (throttle_output , steering_output)

    set_servos(throttle_output, steering_output)
    print("FPS %f, %s" % (clock.fps(), print_string))
