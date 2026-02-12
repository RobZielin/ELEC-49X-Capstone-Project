
const int ledPin[3] = { 25, 33, 32 };  // red, green, blue
const int buttPin = 23;
int pwmg = 250;  //default: 250
int pwmr = 200;  //default: 200
int pwmb = 30;   //default: 30
const int pwm[3] = { pwmr, pwmg, pwmb };
bool LPM = 0;

unsigned long lastISR = 0;
unsigned long buttDelay = 2000;
//gpio_num_t button =23;

int testCounter = 0;

//red - error e.g. memory full
//green - power is ON
//blue - record mode

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
}

void loop() {

  if (LPM) {
    analogWrite(ledPin[2], 0);
    // gpio_pullup_en((gpio_num_t)23);
    // gpio_wakeup_enable((gpio_num_t)23, GPIO_INTR_LOW_LEVEL);
    // esp_light_sleep_start();
  } else {
    // gpio_wakeup_disable((gpio_num_t)23);
    // pinMode(buttPin, INPUT_PULLUP);
    // attachInterrupt(buttPin, isr, FALLING);
    analogWrite(ledPin[2], pwmb);
  }
}
