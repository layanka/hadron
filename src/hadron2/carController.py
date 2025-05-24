# For Raspberry Pi 5
# Code based on Adafruit MotorHat example code

import atexit
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from queue import Queue
from threading import Thread


# Configuration constants
class MotorConfig:
    """Configuration constants for motor setup"""
    MIN_SPEED = -1.0
    MAX_SPEED = 1.0
    DEFAULT_SPEED = 0.5
    STOP_SPEED = 0.0
    RAMP_TIME = 0.1  # Time to ramp up/down speeds
    MAX_ACCELERATION = 2.0  # Max speed change per second


class Direction(Enum):
    """Direction enumeration for better readability"""
    LEFT = -1
    STRAIGHT = 0
    RIGHT = 1


class RobotState(Enum):
    """Robot movement states"""
    STOPPED = "stopped"
    MOVING_FORWARD = "moving_forward"
    MOVING_BACKWARD = "moving_backward"
    TURNING_LEFT = "turning_left"
    TURNING_RIGHT = "turning_right"
    SPINNING_LEFT = "spinning_left"
    SPINNING_RIGHT = "spinning_right"
    STEERING = "steering"
    EMERGENCY_STOP = "emergency_stop"


@dataclass
class MotorSetup:
    """Configuration for motor setup"""
    left_motor_port: int = 2
    right_motor_port: int = 1
    left_motor_inverted: bool = True
    right_motor_inverted: bool = False
    enable_ramping: bool = True  # Smooth speed transitions
    max_acceleration: float = 2.0  # Max speed change per second


@dataclass 
class MovementCommand:
    """Represents a movement command with timing"""
    action: str
    speed: float
    direction: float = 0.0
    duration: float | None = None
    callback: Callable[[], None] | None = None


# Setup logging
logger = logging.getLogger(__name__)

try:
    from adafruit_crickit import crickit

    class RobotCar:
        def __init__(
            self,
            left_trim: float = 0,
            right_trim: float = 0,
            stop_at_exit: bool = True,
            motor_config: MotorSetup | None = None,
        ):
            """Create an instance of the robot car.
            
            Args:
                left_trim: Amount to offset the speed of the left motor (-1 to 1)
                right_trim: Amount to offset the speed of the right motor (-1 to 1)
                stop_at_exit: Whether motors should stop on program exit
                motor_config: Motor configuration (ports and inversion settings)
            """
            # Validate trim values
            self._validate_speed(left_trim, "left_trim")
            self._validate_speed(right_trim, "right_trim")

            self._left_trim = left_trim
            self._right_trim = right_trim
            self._dummy = False
            self._motor_config = motor_config or MotorSetup()
            self._is_moving = False
            self._state = RobotState.STOPPED

            # Get motor references
            left_port = self._motor_config.left_motor_port
            right_port = self._motor_config.right_motor_port
            self._left_motor = getattr(crickit, f"dc_motor_{left_port}")
            self._right_motor = getattr(crickit, f"dc_motor_{right_port}")

            if stop_at_exit:
                atexit.register(self.stop)

            logger.info(
                f"RobotCar initialized with left_trim={left_trim}, "
                f"right_trim={right_trim}"
            )

            # Command processing setup
            self._command_queue = Queue()
            self._command_thread = Thread(target=self._process_commands)
            self._running = True
            self._command_thread.start()

        def _validate_speed(self, speed: float, param_name: str = "speed") -> None:
            """Validate speed parameter is within valid range."""
            if not isinstance(speed, int | float):
                raise TypeError(f"{param_name} must be a number")
            min_speed = MotorConfig.MIN_SPEED
            max_speed = MotorConfig.MAX_SPEED
            if not (min_speed <= speed <= max_speed):
                raise ValueError(
                    f"{param_name} must be between {min_speed} and {max_speed}"
                )

        def _constrain_speed(self, speed: float) -> float:
            """Constrain speed to valid range."""
            return max(MotorConfig.MIN_SPEED, min(MotorConfig.MAX_SPEED, speed))

        def _left_speed(self, speed: float) -> None:
            """Set the speed of the left motor, taking into account its trim."""
            self._validate_speed(speed)
            speed += self._left_trim
            speed = self._constrain_speed(speed)

            # Apply inversion if configured
            if self._motor_config.left_motor_inverted:
                speed = -speed

            self._left_motor.throttle = speed
            logger.debug(f"Left motor speed set to {speed}")

        def _right_speed(self, speed: float) -> None:
            """Set the speed of the right motor, taking into account its trim."""
            self._validate_speed(speed)
            speed += self._right_trim
            speed = self._constrain_speed(speed)

            # Apply inversion if configured
            if self._motor_config.right_motor_inverted:
                speed = -speed

            self._right_motor.throttle = speed
            logger.debug(f"Right motor speed set to {speed}")

        def stop(self) -> None:
            """Stop all movement."""
            self._left_motor.throttle = MotorConfig.STOP_SPEED
            self._right_motor.throttle = MotorConfig.STOP_SPEED
            self._is_moving = False
            self._state = RobotState.STOPPED
            logger.info("Robot stopped")

        def is_moving(self) -> bool:
            """Check if the robot is currently moving."""
            return self._is_moving

        def forward(
            self,
            speed: float = MotorConfig.DEFAULT_SPEED,
            seconds: float | None = None,
        ) -> None:
            """Move forward at the specified speed.
            
            Args:
                speed: Speed value between -1 and 1
                seconds: Optional time to move before stopping
            """
            self._validate_speed(speed)
            log_msg = f"Moving forward at speed {speed}"
            if seconds:
                log_msg += f" for {seconds}s"
            logger.info(log_msg)

            self._left_speed(speed)
            self._right_speed(speed)
            self._is_moving = True
            self._state = RobotState.MOVING_FORWARD

            if seconds is not None:
                if seconds < 0:
                    raise ValueError("seconds must be non-negative")
                time.sleep(seconds)
                self.stop()

        def backward(
            self,
            speed: float = MotorConfig.DEFAULT_SPEED,
            seconds: float | None = None,
        ) -> None:
            """Move backward at the specified speed.
            
            Args:
                speed: Speed value between -1 and 1
                seconds: Optional time to move before stopping
            """
            self._validate_speed(speed)
            log_msg = f"Moving backward at speed {speed}"
            if seconds:
                log_msg += f" for {seconds}s"
            logger.info(log_msg)

            self._left_speed(-speed)
            self._right_speed(-speed)
            self._is_moving = True
            self._state = RobotState.MOVING_BACKWARD

            if seconds is not None:
                if seconds < 0:
                    raise ValueError("seconds must be non-negative")
                time.sleep(seconds)
                self.stop()

        def steer(self, speed: float, direction: float) -> None:
            """Move with steering control.
            
            Args:
                speed: Forward/backward speed (-1 to 1)
                direction: Steering direction (-1 left, 0 straight, 1 right)
            """
            self._validate_speed(speed, "speed")
            self._validate_speed(direction, "direction")

            # Calculate differential steering
            left_speed = speed + (direction * 0.5)
            right_speed = speed - (direction * 0.5)

            # Normalize if speeds exceed limits
            max_speed = max(abs(left_speed), abs(right_speed))
            if max_speed > 1.0:
                left_speed /= max_speed
                right_speed /= max_speed

            self._left_speed(left_speed)
            self._right_speed(right_speed)
            self._is_moving = True
            self._state = RobotState.STEERING

            logger.debug(
                f"Steering: speed={speed}, direction={direction}, "
                f"left={left_speed}, right={right_speed}"
            )

        def turn_left(
            self,
            speed: float = MotorConfig.DEFAULT_SPEED,
            seconds: float | None = None,
        ) -> None:
            """Turn left by moving only the right motor."""
            self._validate_speed(speed)
            log_msg = f"Turning left at speed {speed}"
            if seconds:
                log_msg += f" for {seconds}s"
            logger.info(log_msg)

            self._left_speed(MotorConfig.STOP_SPEED)
            self._right_speed(speed)
            self._is_moving = True
            self._state = RobotState.TURNING_LEFT

            if seconds is not None:
                if seconds < 0:
                    raise ValueError("seconds must be non-negative")
                time.sleep(seconds)
                self.stop()

        def turn_right(
            self,
            speed: float = MotorConfig.DEFAULT_SPEED,
            seconds: float | None = None,
        ) -> None:
            """Turn right by moving only the left motor."""
            self._validate_speed(speed)
            log_msg = f"Turning right at speed {speed}"
            if seconds:
                log_msg += f" for {seconds}s"
            logger.info(log_msg)

            self._left_speed(speed)
            self._right_speed(MotorConfig.STOP_SPEED)
            self._is_moving = True
            self._state = RobotState.TURNING_RIGHT

            if seconds is not None:
                if seconds < 0:
                    raise ValueError("seconds must be non-negative")
                time.sleep(seconds)
                self.stop()

        def spin_left(
            self,
            speed: float = MotorConfig.DEFAULT_SPEED,
            seconds: float | None = None,
        ) -> None:
            """Spin left in place by rotating motors in opposite directions."""
            self._validate_speed(speed)
            log_msg = f"Spinning left at speed {speed}"
            if seconds:
                log_msg += f" for {seconds}s"
            logger.info(log_msg)

            self._left_speed(-speed)
            self._right_speed(speed)
            self._is_moving = True
            self._state = RobotState.SPINNING_LEFT

            if seconds is not None:
                if seconds < 0:
                    raise ValueError("seconds must be non-negative")
                time.sleep(seconds)
                self.stop()

        def spin_right(
            self,
            speed: float = MotorConfig.DEFAULT_SPEED,
            seconds: float | None = None,
        ) -> None:
            """Spin right in place by rotating motors in opposite directions."""
            self._validate_speed(speed)
            log_msg = f"Spinning right at speed {speed}"
            if seconds:
                log_msg += f" for {seconds}s"
            logger.info(log_msg)

            self._left_speed(speed)
            self._right_speed(-speed)
            self._is_moving = True
            self._state = RobotState.SPINNING_RIGHT

            if seconds is not None:
                if seconds < 0:
                    raise ValueError("seconds must be non-negative")
                time.sleep(seconds)
                self.stop()

        # Compatibility aliases for existing code
        def left(
            self,
            speed: float = MotorConfig.DEFAULT_SPEED,
            seconds: float | None = None,
        ) -> None:
            """Alias for turn_left for backward compatibility."""
            self.turn_left(speed, seconds)

        def right(
            self,
            speed: float = MotorConfig.DEFAULT_SPEED,
            seconds: float | None = None,
        ) -> None:
            """Alias for turn_right for backward compatibility."""
            self.turn_right(speed, seconds)

        def emergency_stop(self) -> None:
            """Emergency stop - immediately halt all motors."""
            self._left_motor.throttle = MotorConfig.STOP_SPEED
            self._right_motor.throttle = MotorConfig.STOP_SPEED
            self._is_moving = False
            self._state = RobotState.EMERGENCY_STOP
            logger.warning("Emergency stop activated")

        def get_status(self) -> dict:
            """Get current robot status."""
            return {
                "is_moving": self._is_moving,
                "left_trim": self._left_trim,
                "right_trim": self._right_trim,
                "dummy_mode": self._dummy,
                "motor_config": {
                    "left_port": self._motor_config.left_motor_port,
                    "right_port": self._motor_config.right_motor_port,
                    "left_inverted": self._motor_config.left_motor_inverted,
                    "right_inverted": self._motor_config.right_motor_inverted,
                },
                "state": self._state.name,
            }


        def _ramp_to_speed(self, target_left: float, target_right: float) -> None:
            """Transition en douceur vers les vitesses cibles"""
            current_left = self._left_motor.throttle
            current_right = self._right_motor.throttle

            # Calculate step changes based on max acceleration
            step_left = max(
                MotorConfig.MIN_SPEED,
                min(MotorConfig.MAX_SPEED, target_left - current_left),
            )
            step_right = max(
                MotorConfig.MIN_SPEED,
                min(MotorConfig.MAX_SPEED, target_right - current_right),
            )

            # Ramp up/down in steps
            for _ in range(int(MotorConfig.MAX_ACCELERATION)):
                current_left += step_left
                current_right += step_right

                # Apply constraints and set speeds
                self._left_motor.throttle = max(
                    MotorConfig.MIN_SPEED, min(MotorConfig.MAX_SPEED, current_left)
                )
                self._right_motor.throttle = max(
                    MotorConfig.MIN_SPEED, min(MotorConfig.MAX_SPEED, current_right)
                )

                time.sleep(MotorConfig.RAMP_TIME / MotorConfig.MAX_ACCELERATION)

            logger.info(
                f"Ramped to speeds - Left: {target_left}, Right: {target_right}"
            )

        def queue_command(self, command: MovementCommand) -> None:
            """Ajouter une commande à la queue d'exécution"""
            self._command_queue.put(command)

        def _process_commands(self) -> None:
            """Traiter les commandes de manière asynchrone"""
            while self._running:
                try:
                    command = self._command_queue.get(timeout=1)
                    logger.info(f"Processing command: {command}")
                    # Execute command action
                    if command.action == "forward":
                        self.forward(command.speed, command.duration)
                    elif command.action == "backward":
                        self.backward(command.speed, command.duration)
                    elif command.action == "turn_left":
                        self.turn_left(command.speed, command.duration)
                    elif command.action == "turn_right":
                        self.turn_right(command.speed, command.duration)
                    elif command.action == "spin_left":
                        self.spin_left(command.speed, command.duration)
                    elif command.action == "spin_right":
                        self.spin_right(command.speed, command.duration)
                    elif command.action == "stop":
                        self.stop()
                    else:
                        logger.warning(f"Unknown command action: {command.action}")
                except Exception as e:
                    logger.error(f"Error processing command: {e}")

        def shutdown(self) -> None:
            """Shutdown the robot car, stopping all motors and terminating threads."""
            self._running = False
            self.stop()
            if self._command_thread.is_alive():
                self._command_thread.join()
            logger.info("RobotCar shutdown complete")


except (ImportError, ValueError) as e:
    logger.warning(f"Adafruit Crickit not available: {e}. Using dummy mode.")

    class RobotCar:
        """Dummy implementation when hardware is not available."""

        def __init__(
            self,
            left_trim: float = 0,
            right_trim: float = 0,
            stop_at_exit: bool = True,
            motor_config: MotorSetup | None = None,
        ):
            self._left_trim = left_trim
            self._right_trim = right_trim
            self._dummy = True
            self._motor_config = motor_config or MotorSetup()
            self._is_moving = False
            self._state = RobotState.STOPPED
            logger.info("RobotCar initialized in DUMMY mode")

        def _validate_speed(self, speed: float, param_name: str = "speed") -> None:
            """Validate speed parameter is within valid range."""
            if not isinstance(speed, int | float):
                raise TypeError(f"{param_name} must be a number")
            min_speed = MotorConfig.MIN_SPEED
            max_speed = MotorConfig.MAX_SPEED
            if not (min_speed <= speed <= max_speed):
                raise ValueError(
                    f"{param_name} must be between {min_speed} and {max_speed}"
                )

        def _left_speed(self, speed: float) -> None:
            """Dummy left motor control."""
            self._validate_speed(speed)
            logger.debug(f"DUMMY: Left motor speed would be set to {speed}")

        def _right_speed(self, speed: float) -> None:
            """Dummy right motor control."""
            self._validate_speed(speed)
            logger.debug(f"DUMMY: Right motor speed would be set to {speed}")

        def stop(self) -> None:
            """Dummy stop."""
            self._is_moving = False
            self._state = RobotState.STOPPED
            logger.info("DUMMY: Robot stopped")

        def is_moving(self) -> bool:
            """Check if the robot is currently moving."""
            return self._is_moving

        def forward(
            self,
            speed: float = MotorConfig.DEFAULT_SPEED,
            seconds: float | None = None,
        ) -> None:
            """Dummy forward movement."""
            self._validate_speed(speed)
            log_msg = f"DUMMY: Moving forward at speed {speed}"
            if seconds:
                log_msg += f" for {seconds}s"
            logger.info(log_msg)
            self._is_moving = True
            self._state = RobotState.MOVING_FORWARD
            if seconds is not None:
                if seconds < 0:
                    raise ValueError("seconds must be non-negative")
                time.sleep(seconds)
                self.stop()

        def backward(
            self,
            speed: float = MotorConfig.DEFAULT_SPEED,
            seconds: float | None = None,
        ) -> None:
            """Dummy backward movement."""
            self._validate_speed(speed)
            log_msg = f"DUMMY: Moving backward at speed {speed}"
            if seconds:
                log_msg += f" for {seconds}s"
            logger.info(log_msg)
            self._is_moving = True
            self._state = RobotState.MOVING_BACKWARD
            if seconds is not None:
                if seconds < 0:
                    raise ValueError("seconds must be non-negative")
                time.sleep(seconds)
                self.stop()

        def steer(self, speed: float, direction: float) -> None:
            """Dummy steering."""
            self._validate_speed(speed, "speed")
            self._validate_speed(direction, "direction")
            logger.info(f"DUMMY: Steering with speed={speed}, direction={direction}")
            self._is_moving = True
            self._state = RobotState.STEERING

        def turn_left(
            self,
            speed: float = MotorConfig.DEFAULT_SPEED,
            seconds: float | None = None,
        ) -> None:
            """Dummy left turn."""
            self._validate_speed(speed)
            log_msg = f"DUMMY: Turning left at speed {speed}"
            if seconds:
                log_msg += f" for {seconds}s"
            logger.info(log_msg)
            self._is_moving = True
            self._state = RobotState.TURNING_LEFT
            if seconds is not None:
                if seconds < 0:
                    raise ValueError("seconds must be non-negative")
                time.sleep(seconds)
                self.stop()

        def turn_right(
            self,
            speed: float = MotorConfig.DEFAULT_SPEED,
            seconds: float | None = None,
        ) -> None:
            """Dummy right turn."""
            self._validate_speed(speed)
            log_msg = f"DUMMY: Turning right at speed {speed}"
            if seconds:
                log_msg += f" for {seconds}s"
            logger.info(log_msg)
            self._is_moving = True
            self._state = RobotState.TURNING_RIGHT
            if seconds is not None:
                if seconds < 0:
                    raise ValueError("seconds must be non-negative")
                time.sleep(seconds)
                self.stop()

        def spin_left(
            self,
            speed: float = MotorConfig.DEFAULT_SPEED,
            seconds: float | None = None,
        ) -> None:
            """Dummy spin left."""
            self._validate_speed(speed)
            log_msg = f"DUMMY: Spinning left at speed {speed}"
            if seconds:
                log_msg += f" for {seconds}s"
            logger.info(log_msg)
            self._is_moving = True
            self._state = RobotState.SPINNING_LEFT
            if seconds is not None:
                if seconds < 0:
                    raise ValueError("seconds must be non-negative")
                time.sleep(seconds)
                self.stop()

        def spin_right(
            self,
            speed: float = MotorConfig.DEFAULT_SPEED,
            seconds: float | None = None,
        ) -> None:
            """Dummy spin right."""
            self._validate_speed(speed)
            log_msg = f"DUMMY: Spinning right at speed {speed}"
            if seconds:
                log_msg += f" for {seconds}s"
            logger.info(log_msg)
            self._is_moving = True
            self._state = RobotState.SPINNING_RIGHT
            if seconds is not None:
                if seconds < 0:
                    raise ValueError("seconds must be non-negative")
                time.sleep(seconds)
                self.stop()

        # Compatibility aliases
        def left(
            self,
            speed: float = MotorConfig.DEFAULT_SPEED,
            seconds: float | None = None,
        ) -> None:
            """Alias for turn_left for backward compatibility."""
            self.turn_left(speed, seconds)

        def right(
            self,
            speed: float = MotorConfig.DEFAULT_SPEED,
            seconds: float | None = None,
        ) -> None:
            """Alias for turn_right for backward compatibility."""
            self.turn_right(speed, seconds)

        def emergency_stop(self) -> None:
            """Dummy emergency stop."""
            self._is_moving = False
            self._state = RobotState.EMERGENCY_STOP
            logger.warning("DUMMY: Emergency stop activated")

        def get_status(self) -> dict:
            """Get current robot status."""
            return {
                "is_moving": self._is_moving,
                "left_trim": self._left_trim,
                "right_trim": self._right_trim,
                "dummy_mode": self._dummy,
                "motor_config": {
                    "left_port": self._motor_config.left_motor_port,
                    "right_port": self._motor_config.right_motor_port,
                    "left_inverted": self._motor_config.left_motor_inverted,
                    "right_inverted": self._motor_config.right_motor_inverted,
                },
                "state": self._state.name,
            }
