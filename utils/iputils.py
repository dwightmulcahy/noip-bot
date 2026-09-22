import socket


def getMyIpAddr():
    """Return the preferred outbound IPv4 address without sending data."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("8.8.8.8", 80))
        return probe.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        probe.close()


def findFreePort(bind_addr="127.0.0.1"):
    """Ask the operating system for an available TCP port."""
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        listener.bind((bind_addr, 0))
        return listener.getsockname()[1]
    finally:
        listener.close()
