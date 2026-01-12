# code to connect to the ESP32 via bluetooth and send/receive data

import asyncio
import contextlib
import struct
from bleak import BleakClient, BleakError
import matplotlib.pyplot as plt


# from micropython documentation
UART_SERVICE = "6E400001-B5A3-F393-E0A9-E50E24DCCA9E"
UART_TX = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"  # receiving
UART_RX = "6E400002-B5A3-F393-E0A9-E50E24DCCA9E"  # transmitting

# read ESP32 address from config file
with open("Networking/ESP32.cfg", "r") as f:
    ESP32_ADDR = f.read().strip()

# Global data storage for plotting
data_points = {"x": [], "y": [], "z": []}  # coord -> [values]
plot_fig = None
plot_ax = None
point_count = 0


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


def init_plot():
    """Initialize the matplotlib plot for real-time visualization."""
    global plot_fig, plot_ax
    plt.ion()  # Turn on interactive mode
    plot_fig, plot_ax = plt.subplots(figsize=(10, 6))
    plot_ax.set_xlabel('Sequence Number')
    plot_ax.set_ylabel('Measured Value')
    plot_ax.set_title('Real-Time Data from ESP32')
    plot_ax.grid(True)
    return plot_fig, plot_ax


def update_plot():
    """Update the plot with current data."""
    global plot_ax, data_points, point_count
    plot_ax.clear()
    plot_ax.set_xlabel('Point Index')
    plot_ax.set_ylabel('Measured Value')
    plot_ax.set_title('Real-Time Data from ESP32')
    plot_ax.grid(True)
    
    # Define colors for each coordinate
    colors = {"x": "red", "y": "blue", "z": "green"}
    
    # Plot each coordinate as a line
    for coord in ["x", "y", "z"]:
        if data_points[coord]:
            plot_ax.plot(range(len(data_points[coord])), data_points[coord], 
                        color=colors[coord], label=coord.upper(), linewidth=2, marker='o', markersize=3)
    
    plot_ax.legend()
    plot_fig.canvas.draw()
    plot_fig.canvas.flush_events()


async def run_client() -> None:
    def handle_rx(sender, data):
        global data_points, point_count
        decoded = decode_to_float(data)
        
        # Parse format: "1 x 1.000" (sequence_number coordinate measured_value)
        if isinstance(decoded, str):
            try:
                parts = decoded.split()
                if len(parts) == 3:
                    seq_num = parts[0]
                    coord_type = parts[1]  # "x", "y", or "z"
                    measured_value = float(parts[2])
                    
                    # Store data for x, y, z coordinates
                    if coord_type in ["x", "y", "z"]:
                        data_points[coord_type].append(measured_value)
                        point_count += 1
                        
                        print(f"Seq: {seq_num} | Coord: {coord_type} | Value: {measured_value}")
                        
                        # Update plot
                        update_plot()
                    else:
                        print("ESP32 -> PC:", decoded)
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
                init_plot()  # Initialize the plot
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
