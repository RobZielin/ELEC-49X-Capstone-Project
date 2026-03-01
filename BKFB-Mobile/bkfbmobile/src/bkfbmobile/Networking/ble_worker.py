# this is the BLE backbone of hte project

import asyncio
import contextlib
import json
import struct
import sys

from bleak import BleakClient

UART_TX = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"
UART_RX = "6E400002-B5A3-F393-E0A9-E50E24DCCA9E"


def emit(payload):
    print(json.dumps(payload), flush=True)


def decode_to_float(data: bytes):
    try:
        text = data.decode("utf-8").strip()
        if " " in text:
            return text
        return float(text)
    except (UnicodeDecodeError, ValueError):
        if len(data) == 4:
            return struct.unpack("<f", data)[0]
        if len(data) == 2:
            return float(struct.unpack("<h", data)[0])
        if len(data) == 1:
            return float(data[0])
        if len(data) % 4 == 0:
            return [struct.unpack("<f", data[i : i + 4])[0] for i in range(0, len(data), 4)]
        return data

# heartbeat function because bluetooth likes to die when left idle :(
async def keep_alive(client: BleakClient, interval: float = 8.0) -> None:
    while True:
        try:
            await client.write_gatt_char(UART_RX, b"batman")
        except Exception:
            return
        await asyncio.sleep(interval)


async def run(address: str):
    disconnect_event = asyncio.Event()

    def on_disconnect(_client):
        disconnect_event.set()

    def on_rx(_sender, data):
        decoded = decode_to_float(bytes(data))
        if not isinstance(decoded, str):
            return

        parts = decoded.strip().split()
        if len(parts) != 7 or parts[1] != "x" or parts[3] != "y" or parts[5] != "z":
            return

        try:
            x_value = float(parts[2])
            y_value = float(parts[4])
            z_value = float(parts[6])
        except ValueError:
            return

        emit({"type": "sample", "x": x_value, "y": y_value, "z": z_value})

    emit({"type": "status", "text": "Connecting..."})
    async with BleakClient(address, disconnected_callback=on_disconnect) as client:
        emit({"type": "status", "text": "Connected"})
        await client.start_notify(UART_TX, on_rx)
        await client.write_gatt_char(UART_RX, b"batman")

        keep_task = asyncio.create_task(keep_alive(client))
        try:
            while not disconnect_event.is_set():
                await asyncio.sleep(0.05)
        finally:
            keep_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await keep_task

    emit({"type": "disconnected"})


def main():
    if len(sys.argv) < 2:
        emit({"type": "error", "text": "Missing BLE address"})
        raise SystemExit(2)

    address = sys.argv[1].strip()
    if not address:
        emit({"type": "error", "text": "Empty BLE address"})
        raise SystemExit(2)

    try:
        asyncio.run(run(address))
    except Exception as exc:
        emit({"type": "error", "text": str(exc)})
        raise SystemExit(1)


if __name__ == "__main__":
    main()
