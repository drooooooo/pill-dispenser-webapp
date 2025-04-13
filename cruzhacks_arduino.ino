#include <Servo.h>

// === Pin Definitions ===
#define SERVO_A_PIN 5
#define SERVO_B_PIN 6
#define TRIG1 7
#define ECHO1 8
#define TRIG2 9
#define ECHO2 10
#define RED_LED 13
#define GREEN_LED 12 // Not used (faulty)
#define BLUE_LED 11
#define BUZZER 4

Servo servoA, servoB;

// === State Flags ===
bool waitingForUser = true;
bool awaitingResponse = false;
bool hasDispensed = false;

String inputBuffer = "";

void setup() {
  Serial.begin(9600); // USB serial to Raspberry Pi

  // Pin setup
  pinMode(TRIG1, OUTPUT);
  pinMode(ECHO1, INPUT);
  pinMode(TRIG2, OUTPUT);
  pinMode(ECHO2, INPUT);
  pinMode(RED_LED, OUTPUT);
  pinMode(GREEN_LED, OUTPUT);
  pinMode(BLUE_LED, OUTPUT);
  pinMode(BUZZER, OUTPUT);

  servoA.attach(SERVO_A_PIN);
  servoB.attach(SERVO_B_PIN);

  // Make sure servos are stopped and LED is off
  servoA.write(90);
  servoB.write(90);
  setLEDColor(0, 0, 0);
}

void loop() {
  if (waitingForUser) {
    checkUltrasonic1();
  }

  // Receive UART commands from Raspberry Pi
  if (Serial.available()) {
    char c = Serial.read();
    if (c == '\n') {
      processCommand(inputBuffer);
      inputBuffer = "";
    } else {
      inputBuffer += c;
    }
  }

  // Check if pills were picked up
  if (hasDispensed) {
    checkUltrasonic2();
  }
}

// === Sensor Functions ===
long getDistance(int trigPin, int echoPin) {
  digitalWrite(trigPin, LOW);
  delayMicroseconds(2);
  digitalWrite(trigPin, HIGH);
  delayMicroseconds(10);
  digitalWrite(trigPin, LOW);

  long duration = pulseIn(echoPin, HIGH, 20000); // Timeout at ~20ms
  if (duration == 0) return -1; // No echo
  return duration * 0.034 / 2;
}

void checkUltrasonic1() {
  long dist = getDistance(TRIG1, ECHO1);
  if (dist > 0 && dist < 30) {
    Serial.println("wake");
    waitingForUser = false;
    awaitingResponse = true;
    delay(3000); // Prevent spamming
  }
}

void checkUltrasonic2() {
  long dist = getDistance(TRIG2, ECHO2);
  if (dist > 0 && dist < 10) {
    setLEDColor(255, 0, 255); // PURPLE (Red + Blue)
    Serial.println("pills_taken:userA");

    playPickupTone(); // Cool sci-fi sound!
    
    delay(2000); // Show LED and let tone finish
    setLEDColor(0, 0, 0); // Turn off LED

    hasDispensed = false;
    waitingForUser = true;
    awaitingResponse = false;
  }
}

// === Serial Command Parser ===
void processCommand(String cmd) {
  if (!awaitingResponse) return; // Ignore unless wake was sent

  if (cmd.startsWith("dispense:")) {
    // Format: dispense:userA:2:1
    int idx1 = cmd.indexOf(':');
    int idx2 = cmd.indexOf(':', idx1 + 1);
    int idx3 = cmd.indexOf(':', idx2 + 1);

    String user = cmd.substring(idx1 + 1, idx2);
    int pillsA = cmd.substring(idx2 + 1, idx3).toInt();
    int pillsB = cmd.substring(idx3 + 1).toInt();

    dispense(pillsA, pillsB);
    hasDispensed = true;

  } else if (cmd == "no_user_detected") {
    setLEDColor(255, 0, 0); // RED
    playNegativeTone();     // Simple rejected tone
    delay(2000);            
    setLEDColor(0, 0, 0);   // Turn off LED

    waitingForUser = true;
    awaitingResponse = false;
  }
}

// === Dispense Pills with Servo Sweeps ===
void dispense(int pillsA, int pillsB) {
  setLEDColor(0, 0, 255); // BLUE
  playPositiveTone();     // Simple success tone

  for (int i = 0; i < pillsA; i++) {
    rotateServoOnce(servoA);
    delay(500);
  }

  for (int i = 0; i < pillsB; i++) {
    rotateServoOnce(servoB);
    delay(500);
  }

  servoA.write(90);
  servoB.write(90);

  delay(1000);
  setLEDColor(0, 0, 0); // Turn off LED
}

// === Rotate Servo CW, Pause, and CCW per pill ===
void rotateServoOnce(Servo& s) {
  s.write(180);  // Clockwise (dispense)
  delay(400);

  s.write(90);   // Pause
  delay(1000);   // Let pill drop

  s.write(0);    // Counterclockwise (reset)
  delay(400);

  s.write(90);   // Stop
}

// === LED Control ===
void setLEDColor(int r, int g, int b) {
  analogWrite(RED_LED, r);
  analogWrite(GREEN_LED, g); // Not used
  analogWrite(BLUE_LED, b);
}

// === Sound Effects ===
void playPositiveTone() {
  tone(BUZZER, 1000, 200);
  delay(250);
  tone(BUZZER, 1200, 200);
  delay(250);
  noTone(BUZZER);
}

void playNegativeTone() {
  tone(BUZZER, 400, 500);
  delay(500);
  noTone(BUZZER);
}

void playPickupTone() {
  for (int freq = 800; freq <= 1600; freq += 100) {
    tone(BUZZER, freq, 50);
    delay(60);
  }
  for (int freq = 1600; freq >= 600; freq -= 200) {
    tone(BUZZER, freq, 30);
    delay(40);
  }
  noTone(BUZZER);
}
