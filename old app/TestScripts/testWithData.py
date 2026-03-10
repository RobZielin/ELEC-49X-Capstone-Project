import os
import glob
import numpy as np
from matplotlib import pyplot as plt

from averageStroke import readData, getAccelerationData, getStrokes, getAverageStroke

def process_file(csv_path):
	raw = readData(csv_path)
	acc = getAccelerationData(raw)
	strokes = getStrokes(acc)

	if not strokes:
		print(f"No strokes found in {os.path.basename(csv_path)}")
		return

	# Plot each detected stroke (sample-index vs acceleration)
	plt.figure(figsize=(9, 4))
	for i, s in enumerate(strokes):
		plt.plot(np.arange(s.shape[0]), s, color='gray', alpha=0.6)

	# Try to compute and plot the average stroke (if possible)
	try:
		avg_acc, _ = getAverageStroke(strokes)
		# avg_acc is [averageStroke, lower, upper]
		avg_curve = avg_acc[0]
		plt.plot(np.arange(len(avg_curve)), avg_curve, color='red', linewidth=2, label='Average')
	except Exception as e:
		print(f"Could not compute average stroke for {os.path.basename(csv_path)}: {e}")

	plt.title(os.path.basename(csv_path))
	plt.xlabel('Sample index')
	plt.ylabel('Acceleration (g)')
	plt.legend()
	plt.tight_layout()
	plt.show()


def main():
	base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
	data_dir = os.path.join(base_dir, 'TestScripts', 'data')

	if not os.path.isdir(data_dir):
		print(f"Data directory not found: {data_dir}")
		return

	csv_files = sorted(glob.glob(os.path.join(data_dir, '*.csv')))
	if not csv_files:
		print(f"No CSV files found in {data_dir}")
		return

	for csv_path in csv_files:
		print(f"Processing: {os.path.basename(csv_path)}")
		process_file(csv_path)


if __name__ == '__main__':
	main()
