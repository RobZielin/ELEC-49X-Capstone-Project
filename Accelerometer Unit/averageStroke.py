# code created by Rebecca Hisley

import tensorflow.keras as k
import numpy
import pandas
import scipy
import os
from scipy import signal
from matplotlib import pyplot as plt

#reads the data from a csv file, returns data as a pandas array of accelerometer data
def readData(filePath):
  rawData = pandas.read_csv(filePath)
  rawData = rawData.sort_values(by='Time',axis=0,ascending=True,ignore_index=True)
  return rawData

#computes acceleration and time for raw data (according to Sean's formulas)
def getAccelerationData(rawData):
  accelerationData = pandas.DataFrame(columns = ['time','ay'])
  time0 = rawData['Time'].iloc[0]
  rawData = rawData.astype('float64')
  for i in range(0,len(rawData.index)):
    originalTime = rawData['Time'][i]
    convertedTime = ((originalTime - time0)/100000000.0)*60.0
    ay = -rawData['Sensor2'][i]/9.81
    accelerationData = accelerationData.append({'time':convertedTime,'ay':ay},ignore_index=True)
  return accelerationData

def getVelocityData(averageStroke):
  v0 = 0
  velocityData = [0]
  for i in range(1,len(averageStroke)):
    vy = v0+averageStroke[i]*(1.0/15.0)*9.81 #1.0/15.0 represents sampling rate
    velocityData.append(vy)
    v0 = vy
  return velocityData

#separates the raw data into individual strokes, returns a list of strokes
def getStrokes(accelerationData):
  peakIndexes = getPeaks(accelerationData)
  strokeAccelerations = []
  for i in range(0,len(peakIndexes)-1):
      accStroke = accelerationData['ay'][peakIndexes[i]:peakIndexes[i+1]]
      accStroke = accStroke.to_numpy()
      strokeAccelerations.append(accStroke)
  return strokeAccelerations

def getPeaks(accelerationData):
  negAy= -1*accelerationData['ay']
  trueAy = accelerationData['ay']
  peaks, properties = signal.find_peaks(negAy, prominence=1,width=0.000001)
  properties["prominences"], properties["widths"]
  (numpy.array([1.495, 2.3  ]), numpy.array([36.93773946, 39.32723577]))
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
  sampleLengthsData = pandas.DataFrame({'NumSamples':sampleLengths,'Count':[1 for i in range(len(sampleLengths))]})
  counts = sampleLengthsData.groupby('NumSamples').count()
  mostCommonNumSamples = counts.idxmax()[0]
  resampleIndexes = sampleLengthsData.loc[sampleLengthsData['NumSamples'] != mostCommonNumSamples].index
  resampleIndexes = resampleIndexes.tolist()
  return (mostCommonNumSamples,resampleIndexes)

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
def getAverageStroke(allStrokes):
  sampleLengths = [x.shape[0] for x in allStrokes]
  mostCommonNumSamples, resampleIndexes = getMostCommonNumSamples(sampleLengths)
  resampledStrokes = ressampleStrokes(allStrokes, resampleIndexes, mostCommonNumSamples)
  averageStroke = numpy.mean(allStrokes,axis=0)
  stdDeviation = numpy.std(allStrokes,axis=0)
  stdDevLower = []
  stdDevUpper = []
  for i in range(0,len(averageStroke)):
    stdDevLower.append(averageStroke[i]-stdDeviation[i])
    stdDevUpper.append(averageStroke[i]+stdDeviation[i])
  averageVelocity = getVelocityData(averageStroke)
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