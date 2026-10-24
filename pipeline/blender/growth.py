"""Doubling maths for anything whose size, height or count doubles on a timer.

x(t) = x0 * 2^((t - t0) / T) for t >= t0, else x0. Its rate of change is x * ln2 / T.
Used by the `grow` effect.
"""
import math

R_EARTH = 6_371_000.0
R_MOON = 1_737_400.0
MOON_DIST = 384_400_000.0          # mean centre-to-centre distance (m)
C_LIGHT = 299_792_458.0


def smoothstep(x):
    x = min(1.0, max(0.0, x))
    return x * x * (3 - 2 * x)


class Growth:
    def __init__(self, x0, t0, T):
        self.x0, self.t0, self.T = float(x0), float(t0), float(T)

    def value(self, t):
        return self.x0 if t < self.t0 else self.x0 * 2 ** ((t - self.t0) / self.T)

    def rate(self, t):
        """d/dt of value (units per second)."""
        return 0.0 if t < self.t0 else self.value(t) * math.log(2) / self.T

    def time_at(self, x):
        return self.t0 + self.T * math.log2(x / self.x0)

    def time_at_rate(self, r):
        """When the rate of change reaches r."""
        return self.time_at(r * self.T / math.log(2))
