import io
import threading


# Class to handle streaming output
class StreamingOutput(io.BufferedIOBase):
    def __init__(self):
        self.frame = None
        self.condition = threading.Condition()
        self.buffer_size = 65536  # 64KB buffer

    def write(self, buf):
        with self.condition:
            self.frame = buf[:self.buffer_size]  # Limite la taille du buffer
            self.condition.notify_all()
