import struct

class JoystickReader:
    def __init__(self, device_path='/dev/input/js0'):
        self.device_path = device_path
        self.EVENT_FORMAT = "IhBB"  # (time, value, type, number)
        self.EVENT_SIZE = struct.calcsize(self.EVENT_FORMAT)

    def read_events(self):
        """
        Lit les événements du joystick et les retourne sous forme de dictionnaire.
        """
        try:
            with open(self.device_path, "rb") as device:
                print(f"Listening for events on {self.device_path}...")
                while True:
                    event = device.read(self.EVENT_SIZE)
                    if not event:
                        break

                    # Décomposer l'événement
                    time, value, event_type, number = struct.unpack(self.EVENT_FORMAT, event)

                    yield {
                        "time": time,
                        "value": value,
                        "type": event_type,
                        "number": number
                    }
        except FileNotFoundError:
            print(f"Device {self.device_path} not found. Make sure the controller is connected.")
        except PermissionError:
            print(f"Permission denied. Try running the script with sudo.")
        except OSError as e:
            print(f"Error accessing {self.device_path}: {e}")