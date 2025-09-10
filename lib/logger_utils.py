import logging
import sys
import socket


class SocketStreamHandler(logging.Handler):
    """
    Custom logging handler that streams logs over TCP to the central log server.
    """
    def __init__(self, host, port):
        super().__init__()
        self.host = host
        self.port = port
        self.sock = None
        self._connect()

    def _connect(self):
        try:
            self.sock = socket.create_connection((self.host, self.port))
        except Exception as e:
            print(f"[LoggerUtils] Failed to connect to log server at {self.host}:{self.port}: {e}")
            self.sock = None

    def emit(self, record):
        if not self.sock:
            self._connect()
        if not self.sock:
            return

        try:
            msg = self.format(record)
            self.sock.sendall((msg + "\n").encode('utf-8'))
        except Exception as e:
            print(f"[LoggerUtils] Error sending log: {e}")
            self.sock = None


def get_logger(source: str, log_type: str, level=logging.INFO,
               log_server_ip: str = "127.0.0.1", log_server_port: int = 5000) -> logging.Logger:
    """
    Returns a logger that emits structured logs to both console and a central TCP log server.

    Parameters:
    - source: Component name (e.g., "Access Point", "Coordinator", "Node", "Database")
    - log_type: Log category (e.g., "Console", "Metric", "Snapshot")
    - level: Logging level
    - log_server_ip: IP address of the log server
    - log_server_port: TCP port of the log server
    """
    logger_name = f"{source}_{log_type}"
    logger = logging.getLogger(logger_name)

    if logger.handlers:
        return logger  # Avoid duplicate handlers on multiple calls

    logger.setLevel(level)

    # Formatter: [Metric] [Coordinator] 2025-07-28 14:00:00 [INFO]: Message
    formatter = logging.Formatter(
        fmt=f"[{log_type}] [{source}] %(asctime)s [%(levelname)s]: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(level)
    logger.addHandler(console_handler)

    # Socket handler
    socket_handler = SocketStreamHandler(log_server_ip, log_server_port)
    socket_handler.setFormatter(formatter)
    socket_handler.setLevel(level)
    logger.addHandler(socket_handler)

    return logger
