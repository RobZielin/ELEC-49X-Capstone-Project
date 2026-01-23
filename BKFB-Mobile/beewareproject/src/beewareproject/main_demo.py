# Demo code to replay collected data with plotting in pseudo real-time
# Reads CSV files from TestScripts/data/ and simulates real-time data reception

import asyncio
import io
import struct
import matplotlib.pyplot as plt
import numpy as np
import pandas
import sys
import os
import time
from matplotlib.backends.backend_agg import FigureCanvasAgg
from scipy import signal

# Import average stroke functions (works both as package and script)
try:
    from .AU.averageStroke import getStrokes, getAverageStroke, readData, getAccelerationData
except Exception:  # fallback when run directly (no package context)
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'AU'))
    from AU.averageStroke import getStrokes, getAverageStroke, readData, getAccelerationData

# Global data storage for plotting
data_points = {"x": [], "y": [], "z": []}  # coord -> [values]
plot_fig = None
plot_ax = None
plot_avg_fig = None
plot_avg_ax = None
point_count = 0
use_window = True 
avg_stroke_update_interval = 50  # Update average every N data points
sequence_num = 0

# Delay between data points in seconds (simulates ~66ms reception intervals at 15Hz sample rate)
DATA_POINT_DELAY = 0.05


def init_plot(interactive=True):
    """Initialize the matplotlib plot for real-time visualization."""
    global plot_fig, plot_ax
    if interactive:
        plt.ion()
    else:
        plt.ioff()
        plt.switch_backend('Agg')
    plot_fig, plot_ax = plt.subplots(figsize=(10, 6))
    if not interactive:
        FigureCanvasAgg(plot_fig)
    plot_ax.set_xlabel('Sequence Number')
    plot_ax.set_ylabel('Measured Value')
    plot_ax.set_title('Real-Time Data Replay from Collected CSV')
    plot_ax.grid(True)
    return plot_fig, plot_ax


def init_avg_stroke_plot(interactive=True):
    """Initialize the matplotlib plot for average stroke visualization."""
    global plot_avg_fig, plot_avg_ax
    plot_avg_fig, plot_avg_ax = plt.subplots(figsize=(10, 6))
    if not interactive:
        FigureCanvasAgg(plot_avg_fig)
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
    plot_ax.set_ylabel('Measured Value (g)')
    plot_ax.set_title('Real-Time Data Replay from Collected CSV')
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


def _render_png(fig):
    """Render a matplotlib figure to PNG bytes for embedding."""
    buf = io.BytesIO()
    canvas = fig.canvas
    if not isinstance(canvas, FigureCanvasAgg):
        canvas = FigureCanvasAgg(fig)
    canvas.draw()
    canvas.print_png(buf)
    return buf.getvalue()


def get_csv_files(data_dir):
    """Get all CSV files from the data directory."""
    if not os.path.exists(data_dir):
        print(f"Data directory not found: {data_dir}")
        return []
    
    csv_files = [f for f in os.listdir(data_dir) if f.endswith('.csv')]
    return sorted(csv_files)


def _normalize_dataframe(csv_path):
    """Load CSV and return a dataframe with numeric Sensor1/2/3 columns if possible."""
    # Try semicolon then comma
    for sep in [';', ',']:
        try:
            df = pandas.read_csv(csv_path, sep=sep)
            break
        except Exception:
            df = None
    if df is None:
        raise ValueError("Unable to read CSV")

    # Normalize column names
    cols = {c.lower(): c for c in df.columns}
    def pick(name):
        for key in cols:
            if key.startswith(name.lower()):
                return cols[key]
        return None

    s1 = pick('sensor1') or pick('x') or pick('accx')
    s2 = pick('sensor2') or pick('y') or pick('accy')
    s3 = pick('sensor3') or pick('z') or pick('accz')

    if not (s1 and s2 and s3):
        # Try first 3 numeric columns
        numeric_cols = [c for c in df.columns if pandas.api.types.is_numeric_dtype(df[c])]
        if len(numeric_cols) >= 3:
            s1, s2, s3 = numeric_cols[:3]
        else:
            return None

    return df[[s1, s2, s3]].rename(columns={s1: 'Sensor1', s2: 'Sensor2', s3: 'Sensor3'})


def process_csv_file(csv_path):
    """Process a CSV file and replay data with delays."""
    global data_points, point_count, sequence_num

    print(f"Processing: {csv_path}")

    try:
        df = _normalize_dataframe(csv_path)
        if df is None:
            print(f"  CSV format not recognized (need 3 numeric columns)")
            return

        for idx, row in df.iterrows():
            x_val = float(str(row['Sensor1']).replace(',', '.'))
            y_val = float(str(row['Sensor2']).replace(',', '.'))
            z_val = float(str(row['Sensor3']).replace(',', '.'))

            data_points['x'].append(x_val)
            data_points['y'].append(y_val)
            data_points['z'].append(z_val)
            point_count += 1
            sequence_num += 1

            update_plot()

            if point_count % avg_stroke_update_interval == 0:
                update_avg_stroke_plot()

            time.sleep(DATA_POINT_DELAY)
    except Exception as e:
        print(f"  Error processing file: {e}")


async def process_csv_file_async(csv_path, on_update=None, stop_event=None):
    """Async version of CSV processing that yields plot images via callback."""
    global data_points, point_count, sequence_num

    print(f"Processing (async): {csv_path}")

    try:
        df = _normalize_dataframe(csv_path)
        if df is None:
            print(f"  CSV format not recognized (need 3 numeric columns)")
            return

        for idx, row in df.iterrows():
            if stop_event and stop_event.is_set():
                return

            x_val = float(str(row['Sensor1']).replace(',', '.'))
            y_val = float(str(row['Sensor2']).replace(',', '.'))
            z_val = float(str(row['Sensor3']).replace(',', '.'))

            data_points['x'].append(x_val)
            data_points['y'].append(y_val)
            data_points['z'].append(z_val)
            point_count += 1
            sequence_num += 1

            update_plot()

            if point_count % avg_stroke_update_interval == 0:
                update_avg_stroke_plot()

            if on_update:
                plot_png = _render_png(plot_fig)
                avg_png = _render_png(plot_avg_fig)
                await on_update(plot_png, avg_png)

            await asyncio.sleep(DATA_POINT_DELAY)

    except Exception as e:
        print(f"  Error processing file: {e}")


async def replay_in_app(on_update, data_dir=None, stop_event=None):
    """Run the data replay headlessly and stream plots via callback for the Toga app."""
    global data_points, point_count, plot_fig, plot_ax, plot_avg_ax, plot_avg_fig

    data_dir = data_dir or os.path.join(os.path.dirname(__file__), 'TestScripts', 'data')

    csv_files = get_csv_files(data_dir)
    if not csv_files:
        print(f"No CSV files found in {data_dir}")
        return

    original_backend = plt.get_backend()

    try:
        init_plot(interactive=False)
        init_avg_stroke_plot(interactive=False)

        for csv_file in csv_files:
            if stop_event and stop_event.is_set():
                break

            csv_path = os.path.join(data_dir, csv_file)
            data_points = {"x": [], "y": [], "z": []}
            point_count = 0

            plot_avg_ax.clear()
            plot_avg_ax.set_xlabel('Sample Index')
            plot_avg_ax.set_ylabel('Acceleration (g)')
            plot_avg_ax.set_title('Average Stroke Analysis')
            plot_avg_ax.grid(True)
            plot_avg_fig.canvas.draw()

            await process_csv_file_async(csv_path, on_update=on_update, stop_event=stop_event)

    finally:
        plt.switch_backend(original_backend)



async def main():
    """Main async function to run the demo."""
    global data_points, plot_fig, plot_ax, plot_avg_ax, plot_avg_fig
    
    # Find data directory
    data_dir = os.path.join(os.path.dirname(__file__), 'TestScripts', 'data')
    
    # Get list of CSV files
    csv_files = get_csv_files(data_dir)
    
    if not csv_files:
        print(f"No CSV files found in {data_dir}")
        return
    
    print(f"\nFound {len(csv_files)} CSV files:")
    for i, f in enumerate(csv_files, 1):
        print(f"  {i}. {f}")
    
    # Process each CSV file
    for csv_file in csv_files:
        csv_path = os.path.join(data_dir, csv_file)
        data_points = {"x": [], "y": [], "z": []}  # Reset for each file
        point_count = 0
        
        # Reset average stroke plot
        plot_avg_ax.clear()
        plot_avg_ax.set_xlabel('Sample Index')
        plot_avg_ax.set_ylabel('Acceleration (g)')
        plot_avg_ax.set_title('Average Stroke Analysis')
        plot_avg_ax.grid(True)
        plot_avg_fig.canvas.draw()
        plot_avg_fig.canvas.flush_events()
        
        process_csv_file(csv_path)
        
        print(f"  Completed: {len(data_points['z'])} points processed\n")


if __name__ == "__main__":
    print("CSV Data Replay Demo")
    print("=" * 50)
    
    # Initialize plots once
    init_plot()
    init_avg_stroke_plot()
    
    # Run demo in a loop that restarts
    try:
        while True:
            asyncio.run(main())
            print("Demo completed! Restarting...\n")
    except KeyboardInterrupt:
        print("Stopped by user")
        plt.close('all')
