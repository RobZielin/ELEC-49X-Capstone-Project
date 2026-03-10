import csv
import re
import time
from pathlib import Path
from typing import Optional, Tuple

LINE_RE = re.compile(
    r"^\s*(\d+)\s+x\s+([+-]?(?:\d+\.?\d*|\d*\.\d+))\s+"
    r"y\s+([+-]?(?:\d+\.?\d*|\d*\.\d+))\s+"
    r"z\s+([+-]?(?:\d+\.?\d*|\d*\.\d+))\s*$"
)


def parse_line(line: str) -> Optional[Tuple[int, float, float, float]]:
    match = LINE_RE.match(line)
    if not match:
        return None
    seq = int(match.group(1))
    x = float(match.group(2))
    y = float(match.group(3))
    z = float(match.group(4))
    return seq, x, y, z


class ReceivedDataWriter:
    def __init__(self, output_dir: Path = Path(".")) -> None:
        timestamp = int(time.time())
        self.path = output_dir / f"recievedData{timestamp}.csv"
        self._file = self.path.open("w", newline="", encoding="utf-8")
        self._writer = csv.writer(self._file)
        self._writer.writerow(["seq", "x", "y", "z"])

    def handle_line(self, line: str) -> bool:
        parsed = parse_line(line)
        if not parsed:
            return False
        self._writer.writerow(parsed)
        self._file.flush()
        return True

    def close(self) -> None:
        self._file.close()


if __name__ == "__main__":
    writer = ReceivedDataWriter()
    try:
        while True:
            try:
                line = input()
            except EOFError:
                break
            if line.strip() == "":
                continue
            writer.handle_line(line)
    finally:
        writer.close()
        print(f"Saved CSV to {writer.path}")
