# Demo code to replay collected data with plotting in pseudo real-time
# Reads CSV files from TestScripts/data/ and simulates real-time data reception

import asyncio
import matplotlib.pyplot as plt
import numpy as np
import pandas
import sys
import os
import time

# Import average stroke functions
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


def init_plot():
    """Initialize the matplotlib plot for real-time visualization."""
    global plot_fig, plot_ax
    plt.ion()  # Turn on interactive mode
    plot_fig, plot_ax = plt.subplots(figsize=(10, 6))
    plot_ax.set_xlabel('Sequence Number')
    plot_ax.set_ylabel('Measured Value')
    plot_ax.set_title('Real-Time Data Replay from Collected CSV')
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


def get_csv_files(data_dir):
    """Get all CSV files from the data directory."""
    if not os.path.exists(data_dir):
        print(f"Data directory not found: {data_dir}")
        return []
    
    csv_files = [f for f in os.listdir(data_dir) if f.endswith('.csv')]
    return sorted(csv_files)


def process_csv_file(csv_path):
    """Process a CSV file and replay data with delays."""
    global data_points, point_count, sequence_num
    
    print(f"Processing: {csv_path}")
    
    try:
        # Read the CSV file
        df = pandas.read_csv(csv_path, sep=';')
        
        if 'Sensor1' in df.columns and 'Sensor2' in df.columns and 'Sensor3' in df.columns:
            # This is sensor data format
            for idx, row in df.iterrows():
                # Convert sensor values (handle both comma and period as decimal separator)
                x_val = float(str(row['Sensor1']).replace(',', '.'))
                y_val = float(str(row['Sensor2']).replace(',', '.'))
                z_val = float(str(row['Sensor3']).replace(',', '.'))
                
                # Store data
                data_points['x'].append(x_val)
                data_points['y'].append(y_val)
                data_points['z'].append(z_val)
                point_count += 1
                sequence_num += 1
                
                #print(f"Seq: {sequence_num} | X: {x_val:.3f} | Y: {y_val:.3f} | Z: {z_val:.3f}")
                
                # Update live plot
                update_plot()
                
                # Periodically update average stroke plot
                if point_count % avg_stroke_update_interval == 0:
                    update_avg_stroke_plot()
                
                # Simulate real-time delay
                time.sleep(DATA_POINT_DELAY)
        else:
            print(f"  CSV format not recognized (expected Sensor1, Sensor2, Sensor3 columns)")
            
    except Exception as e:
        print(f"  Error processing file: {e}")


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
