# For Raspberry Pi 5

# Simple two DC motor robot class.  Exposes a simple LOGO turtle-like API for
# moving a robot forward, backward, and turning.

# Code based on Adafruit MotorHat example code

# I should make it more generic, but for now it is specific to my setup:
#   the Left motor is on Motor 2 and mounted in reverse,
#   the Right motor is on Motor 1.
import time
import atexit
from adafruit_crickit import crickit


class RobotCar:
    def __init__(self, left_trim=0, right_trim=0, stop_at_exit=True):
        """Create an instance of the robot.  Can specify the following optional
        parameter
         - left_trim: Amount to offset the speed of the left motor, can be positive
                      or negative and use useful for matching the speed of both
                      motors.  Default is 0.
         - right_trim: Amount to offset the speed of the right motor (see above).
         - stop_at_exit: Boolean to indicate if the motors should stop on program
                         exit.  Default is True (highly recommended to keep this
                         value to prevent damage to the bot on program crash!).
        """

        self._left_trim = left_trim
        self._right_trim = right_trim
        if stop_at_exit:
            atexit.register(self.stop)

    def _left_speed(self, speed):
        """Set the speed of the left motor, taking into account its trim offset."""
        speed += self._left_trim
        speed = max(-1, min(1, speed))  # Constrain speed to 0-255 after trimming.
        # Since, in our case, the left motor is mounted in reverse, we need to invert the speed
        speed = -speed
        crickit.dc_motor_2.throttle = speed

    def _right_speed(self, speed):
        """Set the speed of the right motor, taking into account its trim offset."""
        speed += self._right_trim
        speed = max(-1, min(1, speed))  # Constrain speed to 0-255 after trimming.
        crickit.dc_motor_1.throttle = speed

    @staticmethod
    def stop():
        """Stop all movement."""
        crickit.dc_motor_1.throttle = 0
        crickit.dc_motor_2.throttle = 0

    def forward(self, speed, seconds=None):
        """Move forward at the specified speed (0-255).  Will start moving
        forward and return unless a seconds value is specified, in which
        case the robot will move forward for that amount of time and then stop.
        """
        # Set motor speed and move both forward.
        self._left_speed(speed)
        self._right_speed(speed)
        # If an amount of time is specified, move for that time and then stop.
        if seconds is not None:
            time.sleep(seconds)
            self.stop()

    def steer(self, speed, direction):
        # Move forward at the specified speed (0- 1).  Direction is +- 1.
        # Full left is -1, Full right is +1
        if (speed + direction / 2) > 1:
            speed = (
                speed - direction / 2
            )  # calibrate so total motor output never goes above 1
        left = speed + direction / 2
        right = speed - direction / 2
        self._left_speed(left)
        self._right_speed(right)

    def backward(self, speed, seconds=None):
        """Move backward at the specified speed (0-255).  Will start moving
        backward and return unless a seconds value is specified, in which
        case the robot will move backward for that amount of time and then stop.
        """
        # Set motor speed and move both backward.
        self._left_speed(-1 * speed)
        self._right_speed(-1 * speed)
        # If an amount of time is specified, move for that time and then stop.
        if seconds is not None:
            time.sleep(seconds)
            self.stop()

    def right(self, speed, seconds=None):
        """Spin to the right at the specified speed.  Will start spinning and
        return unless a seconds value is specified, in which case the robot will
        spin for that amount of time and then stop.
        """
        # Set motor speed and move both forward.
        self._left_speed(speed)
        self._right_speed(0)
        # If an amount of time is specified, move for that time and then stop.
        if seconds is not None:
            time.sleep(seconds)
            self.stop()

    def left(self, speed, seconds=None):
        """Spin to the left at the specified speed.  Will start spinning and
        return unless a seconds value is specified, in which case the robot will
        spin for that amount of time and then stop.
        """
        # Set motor speed and move both forward.
        self._left_speed(0)
        self._right_speed(speed)
        # If an amount of time is specified, move for that time and then stop.
        if seconds is not None:
            time.sleep(seconds)
            self.stop()
