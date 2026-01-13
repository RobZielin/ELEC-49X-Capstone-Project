# code to connect to the ESP32 via bluetooth and send/receive data

import asyncio
import contextlib
import struct
from bleak import BleakClient, BleakError
import matplotlib.pyplot as plt
import numpy as np
import pandas
import sys
import os
from scipy import signal

# Import average stroke functions
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'AU'))
from AU.averageStroke import getStrokes, getAverageStroke, readData, getAccelerationData


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
plot_avg_fig = None
plot_avg_ax = None
point_count = 0
use_window = True 
avg_stroke_update_interval = 50  # Update average every N data points


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


def init_avg_stroke_plot():
    """Initialize the matplotlib plot for average stroke visualization."""
    global plot_avg_fig, plot_avg_ax
    plot_avg_fig, plot_avg_ax = plt.subplots(figsize=(10, 6))
    plot_avg_ax.set_xlabel('Sample Index')
    plot_avg_ax.set_ylabel('Acceleration (g)')
    plot_avg_ax.set_title('Average Stroke Analysis')
    plot_avg_ax.grid(True)
    return plot_avg_fig, plot_avg_ax


def update_plot():
    """Update the plot with current data."""
    global plot_ax, data_points, point_count, use_window
    plot_ax.clear()
    plot_ax.set_xlabel('Point Index')
    plot_ax.set_ylabel('Measured Value')
    plot_ax.set_title('Real-Time Data from ESP32')
    plot_ax.grid(True)
    
    # Define colors for each coordinate
    colors = {"x": "red", "y": "blue", "z": "green"}
    
    # Plot each coordinate as a smooth line
    for coord in ["x", "y", "z"]:
        if data_points[coord]:
            if use_window:
                # Only show the most recent 100 points
                window_size = 100
                recent_data = data_points[coord][-window_size:]
                start_idx = max(0, len(data_points[coord]) - window_size)
                x_indices = range(start_idx, start_idx + len(recent_data))
                plot_ax.plot(x_indices, recent_data, 
                            color=colors[coord], label=coord.upper(), linewidth=2)
            else:
                # Show all data points
                plot_ax.plot(range(len(data_points[coord])), data_points[coord], 
                            color=colors[coord], label=coord.upper(), linewidth=2)
    
    plot_ax.legend()
    plot_fig.canvas.draw()
    plot_fig.canvas.flush_events()


def update_avg_stroke_plot():
    """Update the plot with average stroke data."""
    global plot_avg_ax, plot_avg_fig, data_points
    
    if len(data_points['z']) < 20:
        return  # Not enough data
    
    try:
        # Create a temporary CSV to store the data
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            temp_csv = f.name
            # Write header with comma separator (matching readData() expectation)
            f.write('Time,Sensor1,Sensor2,Sensor3\n')
            # Write data - use cumulative time index and all three sensor values
            for i in range(len(data_points['z'])):
                x_val = data_points['x'][i] if i < len(data_points['x']) else 0
                y_val = data_points['y'][i] if i < len(data_points['y']) else 0
                z_val = data_points['z'][i]
                f.write(f'{i * 66666666},{x_val},{y_val},{z_val}\n')
        
        # Process using the standard pipeline
        raw = readData(temp_csv)
        acc = getAccelerationData(raw)
        strokes = getStrokes(acc)
        
        if not strokes:
            print(f"No strokes detected. Data points: {len(data_points['z'])}")
            os.unlink(temp_csv)
            return
        
        print(f"Detected {len(strokes)} strokes")
        
        # Update plot
        plot_avg_ax.clear()
        plot_avg_ax.set_xlabel('Sample Index')
        plot_avg_ax.set_ylabel('Acceleration (g)')
        plot_avg_ax.set_title('Average Stroke Analysis')
        plot_avg_ax.grid(True)
        
        # Plot each detected stroke (sample-index vs acceleration)
        for i, s in enumerate(strokes):
            plot_avg_ax.plot(np.arange(s.shape[0]), s, color='gray', alpha=0.6)
        
        # Try to compute and plot the average stroke
        try:
            avg_acc, avg_vel = getAverageStroke(strokes)
            # avg_acc is [averageStroke, stdDevLower, stdDevUpper]
            avg_curve = avg_acc[0]
            plot_avg_ax.plot(np.arange(len(avg_curve)), avg_curve, color='red', linewidth=2, label='Average')
        except Exception as e:
            print(f"Could not compute average stroke: {e}")
            import traceback
            traceback.print_exc()
        
        plot_avg_ax.legend()
        plot_avg_fig.canvas.draw()
        plot_avg_fig.canvas.flush_events()
        
        # Clean up temporary file
        os.unlink(temp_csv)
        
    except Exception as e:
        print(f"Error in update_avg_stroke_plot: {e}")
        import traceback
        traceback.print_exc()


async def run_client() -> None:
    # Initialize plots once, outside the connection loop
    global data_points, point_count, plot_fig, plot_ax, plot_avg_fig, plot_avg_ax
    init_plot()
    init_avg_stroke_plot()
    
    def handle_rx(sender, data):
        global data_points, point_count
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
                    
                    # Store data for x, y, z coordinates
                    data_points['x'].append(x_value)
                    data_points['y'].append(y_value)
                    data_points['z'].append(z_value)
                    point_count += 1
                    
                    #print(f"Seq: {seq_num} | X: {x_value} | Y: {y_value} | Z: {z_value}")
                    
                    # Update live plot
                    update_plot()
                    
                    # Periodically update average stroke plot
                    if point_count % avg_stroke_update_interval == 0:
                        update_avg_stroke_plot()
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
                # Reset data and plots on reconnection
                data_points = {"x": [], "y": [], "z": []}
                point_count = 0
                plot_ax.clear()
                plot_ax.set_xlabel('Point Index')
                plot_ax.set_ylabel('Measured Value')
                plot_ax.set_title('Real-Time Data from ESP32')
                plot_ax.grid(True)
                plot_avg_ax.clear()
                plot_avg_ax.set_xlabel('Sample Index')
                plot_avg_ax.set_ylabel('Acceleration (g)')
                plot_avg_ax.set_title('Average Stroke Analysis')
                plot_avg_ax.grid(True)
                plot_fig.canvas.draw()
                plot_avg_fig.canvas.draw()
                
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
