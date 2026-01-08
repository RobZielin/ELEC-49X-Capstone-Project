import numpy as np
import pandas as pd
from typing import Iterable, Optional, Tuple, List

from averageStroke import getStrokes, getAverageStroke


class LiveStrokeAverager:
    """
    Incrementally collects acceleration samples and computes an average stroke
    compatible with the CSV-based pipeline.

    Usage:
      averager = LiveStrokeAverager(sampling_rate_hz=15.0)
      averager.add_ay_batch([0.1, -0.2, ...])  # acceleration in g
      acc_avg, vel_avg = averager.compute_average()
    """

    def __init__(self, sampling_rate_hz: float = 15.0):
        self.sampling_rate_hz = sampling_rate_hz
        self._ay: List[float] = []

    def add_sample(self, sensor2_value_m_s2: float) -> None:
        """
        Add a single raw accelerometer sample in m/s^2 (Sensor2 convention).
        Converts to 'g' to match the CSV pipeline.
        """
        ay_g = -(sensor2_value_m_s2) / 9.81
        self._ay.append(ay_g)

    def add_ay(self, ay_g: float) -> None:
        """Add a single acceleration sample already in 'g'."""
        self._ay.append(ay_g)

    def add_ay_batch(self, ay_batch: Iterable[float]) -> None:
        """Add a batch of acceleration samples (in 'g')."""
        self._ay.extend(ay_batch)

    def clear(self) -> None:
        """Clear the internal buffer of acceleration samples."""
        self._ay.clear()

    def compute_strokes(self, plot: bool = False) -> List[np.ndarray]:
        """
        Segment the current buffer into strokes using the same peak logic
        as the CSV pipeline.
        """
        if not self._ay:
            return []
        acc_df = pd.DataFrame({"ay": np.array(self._ay, dtype=float)})
        return getStrokes(acc_df)  # plotting handled in getPeaks via default

    def compute_average(self) -> Optional[Tuple[List[np.ndarray], List[np.ndarray]]]:
        """
        Compute average acceleration and velocity for the collected strokes.

        Returns:
          (averageAcceleration, averageVelocity) where each is a list:
            averageAcceleration = [avg, lower, upper]
            averageVelocity     = [avg, lower, upper]
        Returns None if fewer than two strokes are detected.
        """
        strokes = self.compute_strokes()
        if len(strokes) < 2:
            return None
        return getAverageStroke(strokes, sampling_rate_hz=self.sampling_rate_hz)


if __name__ == "__main__":
    # Simple demo: feed synthetic data and print average sizes
    # Note: segmentation is valley-to-valley, so to compute an
    # average over >=2 strokes, we need at least 3 detected valleys.
    averager = LiveStrokeAverager(sampling_rate_hz=15.0)

    # Create three synthetic strokes (down-up pattern)
    s1 = np.concatenate([np.linspace(0.0, -1.5, 20), np.linspace(-1.5, 0.0, 20)])
    s2 = np.concatenate([np.linspace(0.0, -1.2, 18), np.linspace(-1.2, 0.0, 22)])
    s3 = np.concatenate([np.linspace(0.0, -1.3, 22), np.linspace(-1.3, 0.0, 18)])

    batch = np.concatenate([s1, s2, s3])
    averager.add_ay_batch(batch)

    strokes = averager.compute_strokes()
    print(f"Detected strokes: {len(strokes)}")

    result = averager.compute_average()
    if result is None:
        print("Not enough strokes detected for averaging.")
    else:
        avg_acc, avg_vel = result
        print(f"Average stroke length (acc): {len(avg_acc[0])}")
        print(f"Average velocity length: {len(avg_vel[0])}")