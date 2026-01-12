# code to connect to the ESP32 via bluetooth and send/receive data

import asyncio
import contextlib
import struct
from bleak import BleakClient, BleakError


# from micropython documentation
UART_SERVICE = "6E400001-B5A3-F393-E0A9-E50E24DCCA9E"
UART_TX = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"  # receiving
UART_RX = "6E400002-B5A3-F393-E0A9-E50E24DCCA9E"  # transmitting

# read ESP32 address from config file
with open("Networking/ESP32.cfg", "r") as f:
    ESP32_ADDR = f.read().strip()


def decode_to_float(data: bytes):
    # Try to decode as text first (for semicolon-separated values)
    try:
        text = data.decode('utf-8').strip()
        if ' ' in text:
            return text
        # Otherwise try to parse as a single float
        return float(text)
    except (UnicodeDecodeError, ValueError):
        # Fall back to binary formats if text decoding fails
        if len(data) == 4:
            return struct.unpack("<f", data)[0]
        if len(data) == 2:
            return float(struct.unpack("<h", data)[0])
        if len(data) == 1:
            return float(data[0])
        if len(data) % 4 == 0:
            return [struct.unpack("<f", data[i : i + 4])[0] for i in range(0, len(data), 4)]
        return data


async def keep_alive(client: BleakClient, interval: float = 8.0) -> None:
    """Send small pings to keep the link active."""
    while True:
        try:
            await client.write_gatt_char(UART_RX, b"ping")
        except Exception:
            return
        await asyncio.sleep(interval)


async def run_client() -> None:
    def handle_rx(sender, data):
        decoded = decode_to_float(data)
        
        # Parse format: "<sequence> x <X> y <Y> z <Z>"
        if isinstance(decoded, str):
            try:
                parts = decoded.split()
                if len(parts) == 7 and parts[1] == 'x' and parts[3] == 'y' and parts[5] == 'z':
                    seq_num = parts[0]
                    x_value = float(parts[2])
                    y_value = float(parts[4])
                    z_value = float(parts[6])
                    
                    print(f"Seq: {seq_num} | X: {x_value} | Y: {y_value} | Z: {z_value}")
                else:
                    print("ESP32 -> PC:", decoded)
            except Exception as e:
                print("ESP32 -> PC:", decoded)
        else:
            print("ESP32 -> PC:", decoded)


    while True:
        disconnect_event = asyncio.Event()

        def handle_disconnect(_client):
            print("Disconnected, will retry...")
            disconnect_event.set()

        try:
            async with BleakClient(ESP32_ADDR, disconnected_callback=handle_disconnect) as client:
                print("Connected:", client.is_connected)
                await client.start_notify(UART_TX, handle_rx)

                # send initial message and keep the link alive
                await client.write_gatt_char(UART_RX, b"batman")
                keep_task = asyncio.create_task(keep_alive(client))

                # wait until the client drops; the context manager will close cleanly
                await disconnect_event.wait()
                # ensure the keep-alive task stops when the link is gone
                keep_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await keep_task
        except BleakError as exc:
            print(f"Connection error: {exc}")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            print(f"Unexpected error: {exc}")

        # back off briefly before reconnecting
        await asyncio.sleep(3)


async def main() -> None:
    try:
        await run_client()
    except KeyboardInterrupt:
        print("Stopping on user request")


if __name__ == "__main__":
    asyncio.run(main())
