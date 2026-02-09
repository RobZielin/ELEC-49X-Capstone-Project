

const int ledPin[3] = { 25, 33, 32 }; // red, green, blue
const int buttPin = 23;
int x = 0;
//pwm values chosen to make leds look same brightness
int pwmg = 250; //default: 250 
int pwmr = 200; //default: 200
int pwmb = 30; //default: 30
const int pwm[3] = {pwmr, pwmg,pwmb};
bool press;

// 9.2 mA, cumulative from led circuit
// 9.2*10^-3 *3600 *3.3= 109 Wh, (s*A*V)

void setup() {

  pinMode(ledPin[0], OUTPUT);
  pinMode(ledPin[1], OUTPUT);
  pinMode(ledPin[2], OUTPUT);
  pinMode(buttPin, INPUT_PULLUP);
  Serial.begin(115200);
}
void loop() {
  // for (int i=0; i<=255;i++){ //test all brightness levels
  // analogWrite(ledPin[x], i);  
  // delay(50);
  // Serial.println(i);
  // }
  //delay(500);                    
  analogWrite(ledPin[x], pwm[x]);   // iterate through each led at specified pwm, makes more sense if you turn them off after delay
  x++;
  x%=3; 
  //delay(500);                     
  press = digitalRead(buttPin);
  Serial.println(press);
  
  delay(100);
}
