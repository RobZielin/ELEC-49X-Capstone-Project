import pandas as pd
import matplotlib.pyplot as plt
import glob
import os

data = "TestScripts\data\*.csv"

for file in glob.glob(data):
    df = pd.read_csv(file)

    # rename columns if needed 
    df.columns = df.columns.str.strip()

    # forward acceleration
    accel = df["Sensor1"].values
    
    # plot
    plt.figure(figsize=(8,5))
    plt.plot(accel, linewidth=2)

    plt.title(f"Stroke Acceleration Curve\n{os.path.basename(file)}")
    plt.xlabel("Sample (-)")
    plt.ylabel("Forward Acceleration (g)")

    plt.grid(True)

    # save next to CSV
    outname = file.replace(".csv", "_curve.png")
    plt.savefig(outname, dpi=150, bbox_inches='tight')
    plt.close()

    print(f"Saved plot: {outname}")
