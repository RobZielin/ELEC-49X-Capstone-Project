# main bkfb app component, connects to esp32 and streams live data into the app for viewing and analysis

import asyncio
import json
import os
import matplotlib.pyplot as plt
import matplotlib
import numpy as np
import sys
from io import BytesIO

# import rebecca's stroke analysis code and bluetooth data writer
from bkfbmobile.AU.averageStroke import getStrokes, getAverageStroke, readData, getAccelerationData

# load address from config
config_path = os.path.join(os.path.dirname(__file__), 'Networking', 'ESP32.cfg')
if os.path.exists(config_path):
    with open(config_path, "r") as f:
        ESP32_ADDR = f.read().strip()
else:
    ESP32_ADDR = None 

# image generation backend
matplotlib.use('Agg')

# data variables
data_points = {"x": [], "y": [], "z": []}  # coord -> [values]
plot_fig = None
plot_ax = None
plot_avg_fig = None
plot_avg_ax = None
point_count = 0
window_size = 100
avg_stroke_update_interval = 50  # how frequently to update the average stroke plot (in points)

# BLE stuff
save_writer = None

def _recent_series(points, size):
    start_idx = max(0, len(points['z']) - size)
    end_idx = len(points['z'])
    x_indices = np.arange(start_idx, end_idx)
    recent = {
        'x': points['x'][start_idx:end_idx] if points['x'] else [],
        'y': points['y'][start_idx:end_idx] if points['y'] else [],
        'z': points['z'][start_idx:end_idx] if points['z'] else [],
    }

    all_recent = []
    for coord in ('x', 'y', 'z'):
        all_recent.extend(recent[coord])

    return start_idx, end_idx, x_indices, recent, all_recent


# creates main live data plot
def _generate_plot_png(data_points):
    try:
        fig, ax = plt.subplots(figsize=(8, 5))
        
        # Define colors for each coordinate
        colors = {"x": "red", "y": "blue", "z": "green"}
        start_idx, end_idx, x_indices, recent, all_recent = _recent_series(data_points, window_size)
        
        # Plot each coordinate
        for coord in ["x", "y", "z"]:
            if recent[coord]:
                ax.plot(x_indices, recent[coord], color=colors[coord], label=coord.upper(), linewidth=2)
        
        ax.set_xlabel('Point Index')
        ax.set_ylabel('Measured Value (g)')
        ax.set_title('Real-Time Data Replay')
        ax.set_xlim(start_idx, end_idx)
        if all_recent:
            ax.set_ylim(min(all_recent) - 0.5, max(all_recent) + 0.5)
        ax.legend()
        ax.grid(True)
        
        # Convert to PNG bytes
        buf = BytesIO()
        fig.savefig(buf, format='png', dpi=80, bbox_inches='tight')
        buf.seek(0)
        png_data = buf.getvalue()
        plt.close(fig)
        
        return png_data
    except Exception as e:
        print(f"Error generating plot PNG: {e}")
        return None

# avereage stroke plot
def _generate_avg_stroke_png(data_points):
    """Generate a PNG image of the average stroke plot."""
    try:
        if len(data_points['z']) < 20:
            return None
        
        # Create temporary CSV for processing
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            temp_csv = f.name
            f.write('Time,Sensor1,Sensor2,Sensor3\n')
            for i in range(len(data_points['z'])):
                x_val = data_points['x'][i] if i < len(data_points['x']) else 0
                y_val = data_points['y'][i] if i < len(data_points['y']) else 0
                z_val = data_points['z'][i]
                f.write(f'{i * 66666666},{x_val},{y_val},{z_val}\n')
        
        # Process using the standard pipeline
        raw = readData(temp_csv)
        acc = getAccelerationData(raw)
        strokes = getStrokes(acc)
        
        os.unlink(temp_csv)
        
        if not strokes:
            return None
        
        # Create plot
        fig, ax = plt.subplots(figsize=(8, 5))
        
        # Plot each detected stroke
        for i, s in enumerate(strokes):
            ax.plot(np.arange(s.shape[0]), s, color='gray', alpha=0.6)
        
        # Plot average stroke
        try:
            avg_acc, avg_vel = getAverageStroke(strokes)
            avg_curve = avg_acc[0]
            ax.plot(np.arange(len(avg_curve)), avg_curve, color='red', linewidth=2, label='Average')
        except Exception as e:
            print(f"Could not compute average: {e}")
        
        ax.set_xlabel('Sample Index')
        ax.set_ylabel('Acceleration (g)')
        ax.set_title(f'Average Stroke ({len(strokes)} strokes detected)')
        ax.legend()
        ax.grid(True)
        
        # Convert to PNG bytes
        buf = BytesIO()
        fig.savefig(buf, format='png', dpi=80, bbox_inches='tight')
        buf.seek(0)
        png_data = buf.getvalue()
        plt.close(fig)
        
        return png_data
    except Exception as e:
        print(f"Error generating average stroke PNG: {e}")
        import traceback
        traceback.print_exc()
        return None

# when reset button is pressed
def _reset_live_data():
    global data_points, point_count, save_writer
    data_points = {"x": [], "y": [], "z": []}
    point_count = 0
    save_writer = None

# when reset button is pressed
def clear_in_app_plots():
    """Clear accumulated live data and return refreshed plot images."""
    _reset_live_data()
    return _generate_plot_png(data_points), None


async def _set_status(on_status, text):
    if on_status:
        await on_status(text)

# needs to be reworked, currently creates a subprocess which is stinky
async def connect_live_in_app(on_update, stop_event=None, on_status=None):
    """Connect to ESP32 over BLE and stream live plots into the app window."""

    if stop_event is None:
        stop_event = asyncio.Event()

    if not ESP32_ADDR:
        await _set_status(on_status, "ESP32 address missing in Networking/ESP32.cfg")
        return

    _reset_live_data()
    await _set_status(on_status, f"Connecting to {ESP32_ADDR}...")

    env = os.environ.copy()
    env["PYTHONDEVMODE"] = "0"
    env["PYTHONMALLOC"] = "malloc"

    worker = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "bkfbmobile.Networking.ble_worker",
        ESP32_ADDR,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )

    try:
        while not stop_event.is_set():
            if worker.stdout is None:
                await _set_status(on_status, "BLE worker failed to start")
                return

            try:
                raw_line = await asyncio.wait_for(worker.stdout.readline(), timeout=0.25)
            except asyncio.TimeoutError:
                if worker.returncode is not None:
                    break
                continue

            if not raw_line:
                if worker.returncode is not None:
                    break
                continue

            try:
                message = json.loads(raw_line.decode("utf-8").strip())
            except Exception:
                continue

            kind = message.get("type")
            if kind == "status":
                await _set_status(on_status, message.get("text", ""))
            elif kind == "sample":
                data_points['x'].append(message["x"])
                data_points['y'].append(message["y"])
                data_points['z'].append(message["z"])

                global point_count
                point_count += 1

                plot_png = _generate_plot_png(data_points)
                avg_png = None
                if point_count % avg_stroke_update_interval == 0:
                    avg_png = _generate_avg_stroke_png(data_points)

                if plot_png:
                    await on_update(plot_png, avg_png)
            elif kind == "error":
                await _set_status(on_status, message.get("text", "Connection error"))
                return
            elif kind == "disconnected":
                await _set_status(on_status, "Disconnected")
                return
    finally:
        if worker.returncode is None:
            worker.terminate()
            try:
                await asyncio.wait_for(worker.wait(), timeout=1.0)
            except asyncio.TimeoutError:
                worker.kill()
                await worker.wait()

    if worker.returncode not in (0, None):
        stderr_text = ""
        if worker.stderr is not None:
            try:
                stderr_text = (await worker.stderr.read()).decode("utf-8", errors="replace").strip()
            except Exception:
                stderr_text = ""
        if stderr_text:
            await _set_status(on_status, f"BLE worker error: {stderr_text.splitlines()[-1]}")
        else:
            await _set_status(on_status, f"BLE worker exited ({worker.returncode})")
        return

    await _set_status(on_status, "Stopped")


if __name__ == "__main__":
    print("pls run with briefcase")