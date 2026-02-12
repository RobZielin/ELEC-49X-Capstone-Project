
const int ledPin[3] = { 25, 33, 32 };  // red, green, blue
const int buttPin = 23;
int pwmg = 250;  //default: 250
int pwmr = 200;  //default: 200
int pwmb = 30;   //default: 30
const int pwm[3] = { pwmr, pwmg, pwmb };
bool LPM = 0;

unsigned long lastISR = 0;
unsigned long buttDelay = 2000; //time to wait before accepting next button press (ms)
size_t emptyBytes;
size_t storage;
//gpio_num_t button =23;

//int testCounter = 0;

//red - error e.g. memory full
//green - power is ON
//blue - record mode
/////////////////////// bluetooth
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <BLE2902.h>

#include <Adafruit_MPU6050.h>
#include <Adafruit_Sensor.h>
#include <Wire.h>

#include "LittleFS.h"

Adafruit_MPU6050 mpu;

BLEServer *pServer = NULL;
BLECharacteristic *pTxCharacteristic;
bool deviceConnected = false;
bool oldDeviceConnected = false;

#define DELAY 50
#define BUFFER_SIZE 32  // Number of records to buffer in RAM before writing to LittleFS

// See the following for generating UUIDs:
// https://www.uuidgenerator.net/
#define SERVICE_UUID "6E400001-B5A3-F393-E0A9-E50E24DCCA9E"  // UART service UUID
#define CHARACTERISTIC_UUID_RX "6E400002-B5A3-F393-E0A9-E50E24DCCA9E"
#define CHARACTERISTIC_UUID_TX "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"

// Binary record structure
struct Record {
  uint32_t seq;  // Sequence number
  float x;       // Accelerometer X
  float y;       // Accelerometer Y
  float z;       // Accelerometer Z
};

// RAM buffer to store multiple records before writing to flash
Record buffer[BUFFER_SIZE];
uint8_t bufferIndex = 0;

class MyServerCallbacks : public BLEServerCallbacks {
  void onConnect(BLEServer *pServer) {
    deviceConnected = true;
    Serial.println("Device connected");
  }

  void onDisconnect(BLEServer *pServer) {
    deviceConnected = false;
    Serial.println("Device disconnected");
  }
};

void sendSavedData();  // prototype

class MyCallbacks : public BLECharacteristicCallbacks {
  void onWrite(BLECharacteristic *pCharacteristic) {
    String rxValue = pCharacteristic->getValue();

    Serial.print("Received Value: ");
    Serial.print(rxValue);
    Serial.println();

    if (rxValue == "GIMMEH DATAH") sendSavedData();
  }
};

#define SEND_CHUNK 4  // number of records to send per loop iteration

File sendFile;             // file handle for sending data
bool sendingData = false;  // flag to indicate we're in the middle of sending

void sendSavedData() {
  sendFile = LittleFS.open("/data.bin", "r");
  if (!sendFile) {
    Serial.println("Failed to open data.bin for reading");
    sendingData = false;
    return;
  }

  sendingData = true;
  Serial.println("Started sending saved data...");
}

void sendDataChunk() {
  if (!sendingData || !sendFile) return;

  Record r;
  char buffer[80];

  for (int i = 0; i < SEND_CHUNK; i++) {
    if (sendFile.read((uint8_t *)&r, sizeof(r)) != sizeof(r)) {
      // Finished sending all records
      sendFile.close();
      sendingData = false;
      Serial.println("Finished sending saved data.");

      // wipe data since it was sent
      if (LittleFS.format()) {
        Serial.println("Data wiped after sending.");
      } else {
        Serial.println("LittleFS format failed!");
      }
      return;
    }

    snprintf(buffer, sizeof(buffer), "[OLD] %lu x %.3f y %.3f z %.3f",
             r.seq, r.x, r.y, r.z);

    pTxCharacteristic->setValue(buffer);
    pTxCharacteristic->notify();
  }

  delay(10);
}

// Function to flush buffered records to LittleFS
void flushBuffer() {
  if (bufferIndex == 0) return;                      // Nothing to flush
  File f = LittleFS.open("/data.bin", FILE_APPEND);  // Open file in append mode
  if (f) {
    f.write((uint8_t *)buffer, sizeof(Record) * bufferIndex);  // Write all buffered records
    f.close();
  }
  bufferIndex = 0;  // Reset buffer index after flush
}





///////////////////////// bluetooth

void IRAM_ATTR isr() {

  if (millis() - lastISR >= buttDelay) {
    Serial.println("moooo");
    LPM = !LPM;
    lastISR = millis();
  }
}


void setup() {
  pinMode(ledPin[0], OUTPUT);
  pinMode(ledPin[1], OUTPUT);
  pinMode(ledPin[2], OUTPUT);
  pinMode(buttPin, INPUT_PULLUP);
  attachInterrupt(buttPin, isr, FALLING);
  Serial.begin(115200);
  analogWrite(ledPin[1], pwmg);
  //////////////////////////memory
  storage = LittleFS.totalBytes()

  /////////////////////////////////////bluetooth
  while (!Serial) {
    delay(10);
  }

  if (!mpu.begin()) {
    Serial.println("Failed to find MPU6050 chip");
    while (1) delay(10);
  }
  mpu.setAccelerometerRange(MPU6050_RANGE_16_G);
  mpu.setGyroRange(MPU6050_RANGE_250_DEG);
  mpu.setFilterBandwidth(MPU6050_BAND_21_HZ);
  Serial.println("");
  delay(10);
  // Create the BLE Device
  BLEDevice::init("BKFB AU");

  // Create the BLE Server
  pServer = BLEDevice::createServer();
  pServer->setCallbacks(new MyServerCallbacks());

  // Create the BLE Service
  BLEService *pService = pServer->createService(SERVICE_UUID);

  // Create BLE TX Characteristic
  pTxCharacteristic = pService->createCharacteristic(CHARACTERISTIC_UUID_TX,
                                                     BLECharacteristic::PROPERTY_NOTIFY);
  // Descriptor 2902 is automatically added when using NimBLE
  pTxCharacteristic->addDescriptor(new BLE2902());

  // Create BLE RX Characteristic
  BLECharacteristic *pRxCharacteristic = pService->createCharacteristic(
    CHARACTERISTIC_UUID_RX,
    BLECharacteristic::PROPERTY_WRITE);
  pRxCharacteristic->setCallbacks(new MyCallbacks());

  // Start the BLE service
  pService->start();

  // Start advertising
  pServer->getAdvertising()->start();
  Serial.println("Waiting a client connection to notify...");

  // Initialize LittleFS and format if first time
  if (!LittleFS.begin(true)) {
    Serial.println("LittleFS Mount Failed");
    return;
  }

  // //overwrite file
  // File file = LittleFS.open("/data.bin", FILE_WRITE);
  // if(!file){
  //   Serial.println("Failed to open file for writing");
  //   return;
  // }
  // file.close();

  // // wipe data
  // if (LittleFS.format()) {
  //   Serial.println("LittleFS formatted successfully!");
  // } else {
  //   Serial.println("LittleFS format failed!");
  // }
  ////////////////////////////////////bluetooth end
}

void loop() {

  if (LPM) {
    analogWrite(ledPin[2], 0);
    // gpio_pullup_en((gpio_num_t)23);
    // gpio_wakeup_enable((gpio_num_t)23, GPIO_INTR_LOW_LEVEL);
    // esp_light_sleep_start();
  } else {
    /////////////////////////////memory check
    emptyBytes = storage  - LittleFS.usedBytes();
    //Serial.println(emptyBytes);
    if(emptyBytes/storage >= 0.9) analogWrite(ledPin[0], pwmr);



    ///////////////////////////////////////////the fuckin thingy
    static uint32_t sequence = 1;  // sequence counter

    sensors_event_t a, g, temp;
    mpu.getEvent(&a, &g, &temp);

    // Build a binary record
    Record r;
    r.seq = sequence;
    r.x = a.acceleration.x;
    r.y = a.acceleration.y;
    r.z = a.acceleration.z;

    // send data in chunks
    if (sendingData) {
      sendDataChunk();
      return;
    }

    // If no BLE device connected, store locally in buffer
    if (!deviceConnected) {
      buffer[bufferIndex++] = r;

      // Flush buffer to LittleFS when full
      if (bufferIndex >= BUFFER_SIZE) {
        flushBuffer();
      }

      // // debug statement
      // Serial.print(sequence);
      // Serial.print(", ");
      // Serial.print(a.acceleration.x); Serial.print(", ");
      // Serial.print(a.acceleration.y); Serial.print(", ");
      // Serial.println(a.acceleration.z);

      sequence++;

    } else {  // Device connected, send data over BLE

      if (!sendingData) {  // only send live data if not sending recorded data
        if (deviceConnected) {
          char bufferStr[64];
          snprintf(bufferStr, sizeof(bufferStr), "%lu x %.3f y %.3f z %.3f",
                   r.seq, r.x, r.y, r.z);

          pTxCharacteristic->setValue(bufferStr);
          pTxCharacteristic->notify();
          delay(DELAY);

          sequence++;
        }
      }
    }

    // Handle BLE reconnecting
    if (!deviceConnected && oldDeviceConnected) {
      delay(500);
      flushBuffer();  // Ensure remaining records are saved
      sequence = 1;   // Reset sequence when disconnected for too long
      pServer->startAdvertising();
      Serial.println("Started advertising again...");
      oldDeviceConnected = false;
    }

    if (deviceConnected && !oldDeviceConnected) {
      oldDeviceConnected = true;
    }


    //////////////////////////////////////////end
    // gpio_wakeup_disable((gpio_num_t)23);
    // pinMode(buttPin, INPUT_PULLUP);
    // attachInterrupt(buttPin, isr, FALLING);
    analogWrite(ledPin[2], pwmb);
  }
}
