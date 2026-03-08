# main bkfb app component, connects to esp32 and streams live data into the app for viewing and analysis

import asyncio
import atexit
import json
import os
import signal
import matplotlib.pyplot as plt
import matplotlib
import numpy as np
import sys
from io import BytesIO

# Stroke analysis (pandas/scipy) is imported lazily when needed
# This allows the app to start on Android where these packages aren't available
from bkfbmobile.Networking import ble_runtime

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
show_individual_strokes = False  # toggle to show/hide individual stroke previews in average plot
stroke_padding_samples = 5  # padding samples before/after each stroke to show troughs

# BLE stuff
save_writer = None
_active_worker = None
_active_worker_pid = None
_shutdown_hooks_registered = False

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
        ax.set_ylabel('Measured Value (m/s^2)')
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
        
        # Lazy import stroke analysis - check if available on this platform
        try:
            from bkfbmobile.AU.averageStroke import getStrokes, getAverageStroke, readData, getAccelerationData
        except ImportError as e:
            # pandas/scipy not available (e.g., on Android)
            print(f"Stroke analysis not available: {e}")
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
        strokes = getStrokes(acc, padding_samples=stroke_padding_samples)
        
        os.unlink(temp_csv)
        
        if not strokes:
            return None
        
        # Create plot
        fig, ax = plt.subplots(figsize=(8, 5))
        
        # Plot each detected stroke (optional preview)
        if show_individual_strokes:
            for i, s in enumerate(strokes):
                ax.plot(np.arange(s.shape[0]), s, color='gray', alpha=0.6)
        
        # Plot average stroke
        try:
            avg_acc, avg_vel = getAverageStroke(strokes)
            avg_acc_curve = avg_acc[0]
            avg_vel_curve = avg_vel[0]
            
            # Plot average acceleration on primary y-axis
            ax.plot(np.arange(len(avg_acc_curve)), avg_acc_curve, color='red', linewidth=2, label='Average Acceleration')
            ax.set_ylabel('Acceleration (g)', color='red')
            ax.tick_params(axis='y', labelcolor='red')
            
            # Create secondary y-axis for velocity
            ax2 = ax.twinx()
            ax2.plot(np.arange(len(avg_vel_curve)), avg_vel_curve, color='blue', linewidth=2, label='Average Velocity')
            ax2.set_ylabel('Velocity (m/s)', color='blue')
            ax2.tick_params(axis='y', labelcolor='blue')
            
            # Combine legends from both axes
            lines1, labels1 = ax.get_legend_handles_labels()
            lines2, labels2 = ax2.get_legend_handles_labels()
            ax.legend(lines1 + lines2, labels1 + labels2, loc='upper right')
        except Exception as e:
            print(f"Could not compute average: {e}")
        
        ax.set_xlabel('Sample Index')
        ax.set_title(f'Average Stroke ({len(strokes)} strokes detected)')
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


def _register_shutdown_hooks():
    global _shutdown_hooks_registered
    if _shutdown_hooks_registered:
        return

    atexit.register(force_stop_worker_sync)

    # kill
    for sig_name in ("SIGINT", "SIGTERM"):
        sig = getattr(signal, sig_name, None)
        if sig is None:
            continue
        try:
            signal.signal(sig, _handle_shutdown_signal)
        except (ValueError, RuntimeError):
            continue

    _shutdown_hooks_registered = True


def _handle_shutdown_signal(signum, _frame):
    force_stop_worker_sync()
    raise SystemExit(128 + int(signum))


def force_stop_worker_sync():
    """Best-effort immediate stop for any active BLE worker process."""
    global _active_worker, _active_worker_pid

    worker = _active_worker
    worker_pid = _active_worker_pid

    if worker is not None:
        try:
            if worker.returncode is None:
                worker.terminate()
        except Exception:
            pass

    if worker_pid is not None:
        try:
            if os.name == "posix":
                os.killpg(worker_pid, signal.SIGTERM)
            else:
                os.kill(worker_pid, signal.SIGTERM)
        except Exception:
            pass


async def shutdown_live_stream(stop_event=None):
    """Application-level shutdown hook for BLE resources."""
    if stop_event is not None:
        stop_event.set()

    force_stop_worker_sync()


def _is_mobile_platform() -> bool:
    if sys.platform in {"android", "ios"}:
        return True
    # Some Android runtime variants expose linux platform with Android env vars.
    return any(
        key in os.environ
        for key in ["ANDROID_ARGUMENT", "ANDROID_BOOTLOGO", "ANDROID_STORAGE", "IOS_ARGUMENT"]
    )


def _enqueue_sample(loop, queue, x_value, y_value, z_value):
    loop.call_soon_threadsafe(queue.put_nowait, (x_value, y_value, z_value))


async def _run_worker_stream(on_update, stop_event, on_status):
    global _active_worker, _active_worker_pid

    env = os.environ.copy()
    env["PYTHONDEVMODE"] = "0"
    env["PYTHONMALLOC"] = "malloc"
    env["PYTHONASYNCIODEBUG"] = "0"

    _register_shutdown_hooks()

    spawn_kwargs = {}
    if os.name == "posix":
        # Dedicated process group enables reliable kill of child on shutdown.
        spawn_kwargs["start_new_session"] = True

    worker = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "bkfbmobile.Networking.ble_worker",
        ESP32_ADDR,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
        **spawn_kwargs,
    )

    _active_worker = worker
    _active_worker_pid = worker.pid

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
        _active_worker = None
        _active_worker_pid = None

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


async def _run_in_process_stream(on_update, stop_event, on_status):
    sample_queue: asyncio.Queue[tuple[float, float, float]] = asyncio.Queue()
    stream_done = asyncio.Event()

    loop = asyncio.get_running_loop()
    
    # Wrapper to properly await status updates
    async def status_wrapper(text: str) -> None:
        await _set_status(on_status, text)

    async def consume_samples():
        global point_count
        last_rendered_point_count = 0

        while not stream_done.is_set() or not sample_queue.empty():
            try:
                x_value, y_value, z_value = await asyncio.wait_for(
                    sample_queue.get(), timeout=0.1
                )
                # Append the first sample we awaited.
                data_points['x'].append(x_value)
                data_points['y'].append(y_value)
                data_points['z'].append(z_value)
                point_count += 1

                # Drain any queued samples to keep up with BLE bursts.
                while not sample_queue.empty():
                    x_value, y_value, z_value = sample_queue.get_nowait()
                    data_points['x'].append(x_value)
                    data_points['y'].append(y_value)
                    data_points['z'].append(z_value)
                    point_count += 1
            except asyncio.TimeoutError:
                pass

            if point_count == last_rendered_point_count:
                continue

            plot_png = _generate_plot_png(data_points)
            avg_png = None
            if point_count % avg_stroke_update_interval == 0:
                avg_png = _generate_avg_stroke_png(data_points)

            if plot_png:
                await on_update(plot_png, avg_png)
                last_rendered_point_count = point_count

    consume_task = asyncio.create_task(consume_samples())

    try:
        await ble_runtime.stream_samples(
            ESP32_ADDR,
            on_sample=lambda x, y, z: _enqueue_sample(loop, sample_queue, x, y, z),
            stop_event=stop_event,
            on_status=status_wrapper,
        )
    except Exception as exc:
        await _set_status(on_status, f"BLE stream error: {exc}")
        print(f"BLE stream exception: {exc}")
        import traceback
        traceback.print_exc()
        return
    finally:
        stream_done.set()
        await consume_task

    if stop_event.is_set():
        await _set_status(on_status, "Stopped")

async def connect_live_in_app(on_update, stop_event=None, on_status=None):
    """Connect to ESP32 over BLE and stream live plots into the app window."""

    if stop_event is None:
        stop_event = asyncio.Event()

    if not ESP32_ADDR:
        await _set_status(on_status, "ESP32 address missing in Networking/ESP32.cfg")
        return

    _reset_live_data()
    await _set_status(on_status, f"Connecting to {ESP32_ADDR}...")

    if _is_mobile_platform():
        await _run_in_process_stream(on_update, stop_event, on_status)
    else:
        await _run_worker_stream(on_update, stop_event, on_status)


if __name__ == "__main__":
    print("pls run with briefcase")