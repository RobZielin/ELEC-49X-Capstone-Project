# code created by Rebecca Hisley and modified by Robert Zielinski

# modified to work with live data using a sample rate
# some changes made to avoid deprecated pandas indexing warnings 
# (original likely made with an older version of pandas)

import numpy
import pandas
import os
from scipy import signal
from matplotlib import pyplot as plt

# sample rate for live data
SAMPLE_RATE_HZ = 15.0

#reads the data from a csv file, returns data as a pandas array of accelerometer data
def readData(filePath):
  rawData = pandas.read_csv(filePath)
  rawData = rawData.sort_values(by='Time',axis=0,ascending=True,ignore_index=True)
  return rawData

#computes acceleration and time for raw data (according to Sean's formulas)
def getAccelerationData(rawData):
  time0 = rawData['Time'].iloc[0]
  rawData = rawData.astype('float64')
  times = []
  ay_vals = []
  for i in range(0, len(rawData.index)):
    originalTime = rawData['Time'].iloc[i]
    convertedTime = ((originalTime - time0)/100000000.0)*60.0
    ay = -rawData['Sensor2'].iloc[i]/9.81
    times.append(convertedTime)
    ay_vals.append(ay)
  accelerationData = pandas.DataFrame({'time': times, 'ay': ay_vals})
  return accelerationData

def getVelocityData(averageStroke, sampling_rate_hz=15.0):
  v0 = 0
  velocityData = [0]
  for i in range(1, len(averageStroke)):
    vy = v0 + averageStroke[i] * (1.0 / sampling_rate_hz) * 9.81
    velocityData.append(vy)
    v0 = vy
  return velocityData

#separates the raw data into individual strokes, returns a list of strokes
def getStrokes(accelerationData, plot=False):
  peakIndexes = getPeaks(accelerationData, plot=plot)
  strokeAccelerations = []
  for i in range(0,len(peakIndexes)-1):
      accStroke = accelerationData['ay'].iloc[peakIndexes[i]:peakIndexes[i+1]]
      accStroke = accStroke.to_numpy()
      strokeAccelerations.append(accStroke)
  return strokeAccelerations

def getPeaks(accelerationData, plot=False):
  negAy= -1*accelerationData['ay']
  trueAy = accelerationData['ay']
  peaks, properties = signal.find_peaks(negAy, prominence=1,width=0.000001)
  if plot:
    plt.plot(trueAy)
    plt.title('All Strokes')
    plt.plot(peaks, trueAy[peaks], "x")
    plt.show()
  return peaks

#takes a single stroke and resamples it so that the average can be taken
def ressampleStrokes(allStrokes, resampleIndexes, numSamples):
  for i in resampleIndexes:
    oldStroke = allStrokes[i]
    resampledStroke = signal.resample(oldStroke,numSamples)
    allStrokes[i] = resampledStroke
  allStrokes = numpy.array(allStrokes)
  return allStrokes

#computes the most common number of samples per stroke, minimizes the number of strokes that need to be resampled
def getMostCommonNumSamples(sampleLengths):
  sampleLengthsData = pandas.DataFrame({'NumSamples': sampleLengths, 'Count': [1 for _ in range(len(sampleLengths))]})
  counts = sampleLengthsData.groupby('NumSamples').count()
  # Select the NumSamples value (index) with the max count to avoid positional indexing deprecations
  mostCommonNumSamples = counts['Count'].idxmax()
  resampleIndexes = sampleLengthsData.loc[sampleLengthsData['NumSamples'] != mostCommonNumSamples].index
  resampleIndexes = resampleIndexes.tolist()
  return (mostCommonNumSamples, resampleIndexes)

#Creates a visual plot of the average stroke
def showAveragePlot(acceleration = None,velocity = None):
  legendEntries = []
  if acceleration != None:
    plt.plot(acceleration[0])
    plt.fill_between([i for i in range(0,len(acceleration[0]))],acceleration[1],acceleration[2],alpha=0.2)
    legendEntries.append('Acceleration (g)')
  if velocity != None:
    plt.plot(velocity[0])
    plt.fill_between([i for i in range(0,len(velocity[0]))],velocity[1],velocity[2],alpha=0.2)
    legendEntries.append('Velocity (m/s)')
  plt.legend(legendEntries)
  plt.title('Average Stroke')
  plt.show()

#Computes the average stroke from the resampled strokes
def getAverageStroke(allStrokes, sampling_rate_hz=SAMPLE_RATE_HZ):
  sampleLengths = [x.shape[0] for x in allStrokes]
  mostCommonNumSamples, resampleIndexes = getMostCommonNumSamples(sampleLengths)
  resampledStrokes = ressampleStrokes(allStrokes, resampleIndexes, mostCommonNumSamples)
  averageStroke = numpy.mean(resampledStrokes,axis=0)
  stdDeviation = numpy.std(resampledStrokes,axis=0)
  stdDevLower = []
  stdDevUpper = []
  for i in range(0,len(averageStroke)):
    stdDevLower.append(averageStroke[i]-stdDeviation[i])
    stdDevUpper.append(averageStroke[i]+stdDeviation[i])
  averageVelocity = getVelocityData(averageStroke, sampling_rate_hz=sampling_rate_hz)
  velocityStdDevLower = []
  velocitystdDevUpper = []
  for i in range(0,len(averageVelocity)):
    velocityStdDevLower.append(averageVelocity[i]-stdDeviation[i])
    velocitystdDevUpper.append(averageVelocity[i]+stdDeviation[i])
  return ([averageStroke,stdDevLower,stdDevUpper],[averageVelocity,velocityStdDevLower,velocitystdDevUpper])

#save average stroke data
def saveAverageStroke(filePath, saveFileName, averageAcceleration, averageVelocity):
  avgStroke = pandas.DataFrame({
      'acceleration':averageAcceleration[0],
      'accStdDevLower':averageAcceleration[1],
      'accStdDevUpper':averageAcceleration[2],
      'velocity':averageVelocity[0],
      'velStdDevLower':averageVelocity[1],
      'velStdDevUpper':averageVelocity[2]
  })
  avgStroke.to_csv(os.path.join(filePath,saveFileName))

#load previous average stroke data
def loadAverageStroke(filePath):
  avgStroke = pandas.read_csv(filePath)
  avgAcceleration = [
      avgStroke['acceleration'].to_numpy(),
      avgStroke['accStdDevLower'].to_numpy(),
      avgStroke['accStdDevUpper'].to_numpy()
  ]
  avgVelocity = [
      avgStroke['velocity'].to_numpy(),
      avgStroke['velStdDevLower'].to_numpy(),
      avgStroke['velStdDevUpper'].to_numpy()
  ]
  return avgAcceleration, avgVelocity

if __name__ == "__main__":
  print("Module for computing average stroke; not intended to be run directly.")