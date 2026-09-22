import time


class UpTime:
    def __init__(self, clock=None):
        self._clock = clock or time.monotonic
        self._started = self._clock()

    @property
    def seconds(self):
        return max(0, int(self._clock() - self._started))

    def __str__(self):
        remaining = self.seconds
        days, remaining = divmod(remaining, 86400)
        hours, remaining = divmod(remaining, 3600)
        minutes, seconds = divmod(remaining, 60)
        parts = []
        if days:
            parts.append(f"{days}d")
        if days or hours:
            parts.append(f"{hours}h")
        if days or hours or minutes:
            parts.append(f"{minutes}m")
        parts.append(f"{seconds}s")
        return " ".join(parts)
