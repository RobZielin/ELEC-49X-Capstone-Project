

const int ledPin[3] = { 25, 33, 32 };
const int buttPin = 23;
int x = 0;
int pwmg = 250; //250
int pwmr = 200; //200
int pwmb = 30; //30
const int pwm[3] = {pwmr, pwmg,pwmb};
bool press;

// 9.2 mA
// 9.2*10^-3 *3600 *3.3= 109 Wh

void setup() {

  pinMode(ledPin[0], OUTPUT);
  pinMode(ledPin[1], OUTPUT);
  pinMode(ledPin[2], OUTPUT);
  pinMode(buttPin, INPUT_PULLUP);
  Serial.begin(115200);
}
void loop() {
  // for (int i=0; i<=255;i++){
  // analogWrite(ledPin[x], i);  // turn on the LED
  // delay(50);
  // Serial.println(i);
  // }
  //delay(500);                     // wait for half a second or 500 milliseconds
  analogWrite(ledPin[x], pwm[x]);   // turn off the LED
  //delay(500);                     // wait for half a second or 500 milliseconds
  // Serial.println(x);
  // Serial.println(ledPin[x]);
  press = digitalRead(buttPin);
  Serial.println(press);
  x++;
  x%=3;
  delay(100);
}