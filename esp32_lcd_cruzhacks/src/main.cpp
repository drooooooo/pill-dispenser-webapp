/*******************************************************************
    ESP32 Cheap Yellow Display - User Greeting Display with Medication Schedule

    Displays "SCAN HERE:" and shows a personalized greeting when
    receiving a user name via serial. Includes a button to view medication schedule.
    Automatically returns to scan screen after 7 seconds.
 *******************************************************************/

#include <SPI.h>
#include <XPT2046_Touchscreen.h>
#include <TFT_eSPI.h>

// Touch Screen pins
#define XPT2046_IRQ 36
#define XPT2046_MOSI 32
#define XPT2046_MISO 39
#define XPT2046_CLK 25
#define XPT2046_CS 33

// Border properties
#define BORDER_WIDTH 10
#define BORDER_COLOR TFT_BLUE
#define BACKGROUND_COLOR TFT_WHITE
#define TEXT_COLOR TFT_BLACK
#define GREETING_COLOR TFT_RED
#define BUTTON_COLOR TFT_GREEN
#define BUTTON_TEXT_COLOR TFT_WHITE
#define MEDICATION_TIME_COLOR TFT_BLUE
#define MEDICATION_PILL_COLOR TFT_DARKGREY

// Serial communication
#define SERIAL_TIMEOUT 100
#define MAX_NAME_LENGTH 32 // Maximum length for user name

// Screen modes
#define MODE_SCAN 0
#define MODE_GREETING 1
#define MODE_SCHEDULE 2

SPIClass touchSpi = SPIClass(VSPI);
XPT2046_Touchscreen ts(XPT2046_CS, XPT2046_IRQ);

TFT_eSPI tft = TFT_eSPI();

// Forward declarations
void drawBorder();
void displayScanText();
void displayGreeting(const String &userName);
void displayMedicationSchedule(const String &userName);
void checkSerialForUserData();
void checkForTouchEvents();
void drawPillIcon(int x, int y, uint16_t color, String letter);
bool isTouchInsideButton(int x, int y);
void checkInactivityTimer();

// State management
int currentMode = MODE_SCAN;
String currentUserName = "";
unsigned long greetingStartTime = 0;
unsigned long lastUserActionTime = 0;
const unsigned long GREETING_DURATION = 5000;    // Show greeting for 5 seconds
const unsigned long MAX_INACTIVITY_TIME = 10000; // Return to scan after 7 seconds

// Button coordinates (will be set in displayGreeting)
int buttonX, buttonY, buttonW, buttonH;

void setup()
{
  Serial.begin(115200);
  delay(1000); // Short delay to allow serial to initialize fully

  Serial.println("\n\n*** ESP32 Display with User Greeting and Medication Schedule ***");
  Serial.println("Test by sending 'NAME:YourName' in the Serial Monitor");

  // Start the SPI for the touch screen and init the TS library
  touchSpi.begin(XPT2046_CLK, XPT2046_MISO, XPT2046_MOSI, XPT2046_CS);
  ts.begin(touchSpi);
  ts.setRotation(0);

  // Start the TFT display
  tft.init();
  tft.setRotation(0); // Portrait mode

  // Fill the screen with white color
  tft.fillScreen(BACKGROUND_COLOR);

  // Draw a decorative border
  drawBorder();

  // Display "SCAN HERE:" text with a cool font
  displayScanText();

  Serial.println("Display initialized. Waiting for user data...");
  Serial.setTimeout(SERIAL_TIMEOUT);
}

void drawBorder()
{
  // Top border
  tft.fillRect(0, 0, tft.width(), BORDER_WIDTH, BORDER_COLOR);

  // Bottom border
  tft.fillRect(0, tft.height() - BORDER_WIDTH, tft.width(), BORDER_WIDTH, BORDER_COLOR);

  // Left border
  tft.fillRect(0, 0, BORDER_WIDTH, tft.height(), BORDER_COLOR);

  // Right border
  tft.fillRect(tft.width() - BORDER_WIDTH, 0, BORDER_WIDTH, tft.height(), BORDER_COLOR);

  // Add some corner decorations - rounded inner corners
  int cornerSize = BORDER_WIDTH * 2;

  // Inner corners with a different color for decoration
  tft.fillCircle(BORDER_WIDTH * 2, BORDER_WIDTH * 2, BORDER_WIDTH, TFT_RED);
  tft.fillCircle(tft.width() - BORDER_WIDTH * 2, BORDER_WIDTH * 2, BORDER_WIDTH, TFT_RED);
  tft.fillCircle(BORDER_WIDTH * 2, tft.height() - BORDER_WIDTH * 2, BORDER_WIDTH, TFT_RED);
  tft.fillCircle(tft.width() - BORDER_WIDTH * 2, tft.height() - BORDER_WIDTH * 2, BORDER_WIDTH, TFT_RED);
}

void displayScanText()
{
  // Clear the middle part of the screen (not the border)
  tft.fillRect(BORDER_WIDTH, BORDER_WIDTH,
               tft.width() - (BORDER_WIDTH * 2),
               tft.height() - (BORDER_WIDTH * 2),
               BACKGROUND_COLOR);

  currentMode = MODE_SCAN;

  // Using the large font
  tft.setTextColor(TEXT_COLOR);

  // First display using Font 4 (a large font available in TFT_eSPI)
  tft.setTextSize(2);
  tft.setTextFont(4); // Use font 4

  int x = tft.width() / 2;
  int y = tft.height() / 3;

  tft.setTextDatum(MC_DATUM); // Middle center
  tft.drawString("SCAN", x, y);

  y += 60; // Move down for the next line
  tft.drawString("HERE:", x, y);

  // Draw an arrow pointing down
  int arrowY = y + 70;
  int arrowWidth = 40;
  int arrowHeight = 50;

  // Arrow shaft
  tft.fillRect(x - 5, arrowY, 10, arrowHeight, TFT_RED);

  // Arrow head
  for (int i = 0; i < arrowWidth / 2; i++)
  {
    tft.drawLine(x - i, arrowY + arrowHeight - 2 * i, x + i, arrowY + arrowHeight - 2 * i, TFT_RED);
  }

  Serial.println("Scan screen displayed. Ready for new input.");
}

void drawScheduleButton()
{
  // Define button size and position
  buttonW = 160;
  buttonH = 40;
  buttonX = (tft.width() - buttonW) / 2;
  buttonY = tft.height() - BORDER_WIDTH - buttonH - 40;

  // Draw button
  tft.fillRoundRect(buttonX, buttonY, buttonW, buttonH, 8, BUTTON_COLOR);
  tft.drawRoundRect(buttonX, buttonY, buttonW, buttonH, 8, TFT_DARKGREY);

  // Add text to button - CHANGED: Text from "MEDICATION" to "SCHEDULE"
  tft.setTextColor(BUTTON_TEXT_COLOR);
  tft.setTextSize(1);
  tft.setTextFont(4);
  tft.setTextDatum(MC_DATUM);
  tft.drawString("SCHEDULE", buttonX + buttonW / 2, buttonY + buttonH / 2);
}

void displayGreeting(const String &userName)
{
  // Clear the middle part of the screen (not the border)
  tft.fillRect(BORDER_WIDTH, BORDER_WIDTH,
               tft.width() - (BORDER_WIDTH * 2),
               tft.height() - (BORDER_WIDTH * 2),
               BACKGROUND_COLOR);

  currentMode = MODE_GREETING;
  currentUserName = userName;
  greetingStartTime = millis();
  lastUserActionTime = millis(); // Reset inactivity timer

  // Set text properties
  tft.setTextColor(GREETING_COLOR);
  tft.setTextSize(2);
  tft.setTextFont(4);
  tft.setTextDatum(MC_DATUM); // Middle center

  int x = tft.width() / 2;

  // MODIFIED: Moved everything up to avoid overlap with button
  int y = tft.height() / 4; // Changed from tft.height() / 3 to tft.height() / 4

  // Display greeting
  tft.drawString("Hello,", x, y);

  // Handle long names by reducing text size if needed
  String displayName = userName;
  if (displayName.length() > 10)
  {
    tft.setTextSize(1);
  }

  y += 50; // Reduced from 60 to 50 to compact layout
  tft.drawString(displayName, x, y);

  // Add a happy smiley face - moved up
  int faceY = y + 60; // Reduced from 70 to 60
  int faceRadius = 30;

  // Draw face circle
  tft.fillCircle(x, faceY, faceRadius, TFT_YELLOW);
  tft.drawCircle(x, faceY, faceRadius, TFT_BLACK);

  // Draw eyes
  int eyeOffset = 12;
  tft.fillCircle(x - eyeOffset, faceY - 8, 6, TFT_BLACK);
  tft.fillCircle(x + eyeOffset, faceY - 8, 6, TFT_BLACK);

  // Draw happy smile - proper smile curve going upward
  for (int i = -15; i <= 15; i++)
  {
    // Create a smile curve using a simple quadratic function (inverted from previous)
    int smileY = faceY + 10 - (i * i) / 20;
    tft.drawPixel(x + i, smileY, TFT_BLACK);
    tft.drawPixel(x + i, smileY + 1, TFT_BLACK);
  }

  // Draw the schedule button
  drawScheduleButton();

  Serial.print("Greeting displayed for user: ");
  Serial.println(userName);
  Serial.println("Will return to scan screen in 5 seconds if no button is pressed...");
  Serial.println("Will return to scan screen after 7 seconds of inactivity...");
}

void displayMedicationSchedule(const String &userName)
{
  // Clear the middle part of the screen (not the border)
  tft.fillRect(BORDER_WIDTH, BORDER_WIDTH,
               tft.width() - (BORDER_WIDTH * 2),
               tft.height() - (BORDER_WIDTH * 2),
               BACKGROUND_COLOR);

  currentMode = MODE_SCHEDULE;
  lastUserActionTime = millis(); // Reset inactivity timer

  // Set title text properties - MODIFIED: Adaptive text size based on name length
  tft.setTextColor(TFT_BLUE);
  tft.setTextSize(1);
  tft.setTextFont(4);
  tft.setTextDatum(TC_DATUM); // Top center

  int x = tft.width() / 2;
  int y = BORDER_WIDTH + 5; // MODIFIED: Reduced top margin from 10 to 5

  // Display title with adaptive text size
  String title = userName + "'s Medication";

  // If the name is too long, use a smaller font
  if (title.length() > 18)
  {
    tft.setTextFont(2); // Smaller font for long names
  }

  tft.drawString(title, x, y);

  // Determine line position based on font used
  int lineY = (title.length() > 18) ? y + 20 : y + 30;

  // Draw a line under the title
  tft.drawLine(BORDER_WIDTH + 20, lineY,
               tft.width() - BORDER_WIDTH - 20, lineY,
               TFT_DARKGREY);

  // MODIFIED: Move medication schedule up - adjust y position
  y = lineY + 10; // Position closer to the line
  int leftMargin = BORDER_WIDTH + 15;
  int lineHeight = 20; // MODIFIED: Further reduced from 22 to 20 to make things more compact

  // Time headers - larger and in blue
  tft.setTextColor(MEDICATION_TIME_COLOR);
  tft.setTextFont(4);
  tft.setTextSize(1);
  tft.setTextDatum(TL_DATUM); // Top left

  // Morning medication
  tft.drawString("8:00 AM", leftMargin, y);
  y += 25; // MODIFIED: Reduced from 26 to 25

  // Pill details
  tft.setTextColor(MEDICATION_PILL_COLOR);
  tft.setTextFont(2);
  tft.drawString("Pill A: 2 tablets", leftMargin + 10, y);
  y += lineHeight;
  tft.drawString("Pill B: 1 tablet", leftMargin + 10, y);
  y += lineHeight + 5; // MODIFIED: Kept at reduced spacing of 5

  // Afternoon medication
  tft.setTextColor(MEDICATION_TIME_COLOR);
  tft.setTextFont(4);
  tft.drawString("1:00 PM", leftMargin, y);
  y += 25; // MODIFIED: Reduced from 26 to 25

  // Pill details
  tft.setTextColor(MEDICATION_PILL_COLOR);
  tft.setTextFont(2);
  tft.drawString("Pill A: 1 tablet", leftMargin + 10, y);
  y += lineHeight;
  tft.drawString("Pill B: 0 tablets", leftMargin + 10, y);
  y += lineHeight + 5; // MODIFIED: Kept at reduced spacing of 5

  // Evening medication
  tft.setTextColor(MEDICATION_TIME_COLOR);
  tft.setTextFont(4);
  tft.drawString("8:00 PM", leftMargin, y);
  y += 25; // MODIFIED: Reduced from 26 to 25

  // Pill details
  tft.setTextColor(MEDICATION_PILL_COLOR);
  tft.setTextFont(2);
  tft.drawString("Pill A: 2 tablets", leftMargin + 10, y);
  y += lineHeight;
  tft.drawString("Pill B: 1 tablet", leftMargin + 10, y);

  // MODIFIED: Adjusted pill icon positions to align better with the new layout
  drawPillIcon(tft.width() - 50, 100, TFT_RED, "A");
  drawPillIcon(tft.width() - 50, 185, TFT_BLUE, "B");

  // Add back button at bottom - MODIFIED: More space above border
  buttonW = 120;
  buttonH = 35;
  buttonX = (tft.width() - buttonW) / 2;
  buttonY = tft.height() - BORDER_WIDTH - buttonH - 10; // MODIFIED: Less space from bottom

  tft.fillRoundRect(buttonX, buttonY, buttonW, buttonH, 8, TFT_RED);
  tft.drawRoundRect(buttonX, buttonY, buttonW, buttonH, 8, TFT_DARKGREY);

  tft.setTextColor(TFT_WHITE);
  tft.setTextFont(2);
  tft.setTextDatum(MC_DATUM);
  tft.drawString("BACK", buttonX + buttonW / 2, buttonY + buttonH / 2);

  Serial.println("Medication schedule displayed for user: " + userName);
  Serial.println("Will return to scan screen after 7 seconds of inactivity...");
}

// Draw a capsule-shaped pill icon with a letter inside
void drawPillIcon(int x, int y, uint16_t color, String letter)
{
  int pillWidth = 30;
  int pillHeight = 15;

  // Draw pill shape (capsule)
  tft.fillRoundRect(x - pillWidth / 2, y - pillHeight / 2, pillWidth, pillHeight, pillHeight / 2, color);
  tft.drawRoundRect(x - pillWidth / 2, y - pillHeight / 2, pillWidth, pillHeight, pillHeight / 2, TFT_BLACK);

  // Add letter label
  tft.setTextColor(TFT_WHITE);
  tft.setTextFont(2);
  tft.setTextDatum(MC_DATUM);
  tft.drawString(letter, x, y);
}

void checkSerialForUserData()
{
  if (Serial.available() > 0)
  {
    // Read the incoming data
    String incomingData = Serial.readStringUntil('\n');
    incomingData.trim();

    // Check if the incoming data is not empty
    if (incomingData.length() > 0)
    {
      Serial.print("Received input: ");
      Serial.println(incomingData);

      // Extract user name - check for "NAME:" format or use as direct name
      String userName;
      if (incomingData.startsWith("NAME:"))
      {
        userName = incomingData.substring(5); // Remove "NAME:" prefix
        userName.trim();
      }
      else
      {
        // If not in NAME: format, assume the whole string is the name
        userName = incomingData;
      }

      if (userName.length() > 0)
      {
        displayGreeting(userName);
      }
      else
      {
        Serial.println("Error: Empty name received. Try 'NAME:John' or just 'John'");
      }
    }
  }
}

bool isTouchInsideButton(int x, int y)
{
  return (x >= buttonX && x <= (buttonX + buttonW) &&
          y >= buttonY && y <= (buttonY + buttonH));
}

void checkForTouchEvents()
{
  if (ts.tirqTouched() && ts.touched())
  {
    TS_Point p = ts.getPoint();

    // FIXED: Corrected touch coordinate mapping
    // The XPT2046 touch controller orientation might need different mapping
    // depending on the display orientation and touchscreen mounting

    // Debug original values
    Serial.print("Raw touch values - x: ");
    Serial.print(p.x);
    Serial.print(", y: ");
    Serial.println(p.y);

    // Try a different mapping approach
    int x = map(p.x, 0, 4095, 0, tft.width());
    int y = map(p.y, 0, 4095, 0, tft.height());

    Serial.print("Mapped touch at x=");
    Serial.print(x);
    Serial.print(", y=");
    Serial.println(y);

    // Check if touch is inside button
    if (isTouchInsideButton(x, y))
    {
      Serial.println("Button pressed!");
      lastUserActionTime = millis(); // Reset inactivity timer

      if (currentMode == MODE_GREETING)
      {
        displayMedicationSchedule(currentUserName);
      }
      else if (currentMode == MODE_SCHEDULE)
      {
        displayGreeting(currentUserName);
      }
      delay(300); // Debounce
    }
  }
}

// ADDED: Function to check and handle inactivity timer
void checkInactivityTimer()
{
  // If we're in greeting or schedule mode and it's been too long since last interaction
  if ((currentMode == MODE_GREETING || currentMode == MODE_SCHEDULE) &&
      (millis() - lastUserActionTime > MAX_INACTIVITY_TIME))
  {
    Serial.println("Inactivity timeout reached. Returning to scan screen.");
    displayScanText();
  }
}

void loop()
{
  // Check if we received user data from Serial
  checkSerialForUserData();

  // Check for touch events
  checkForTouchEvents();

  // If we're showing a greeting and the time has expired, go back to scan screen
  if (currentMode == MODE_GREETING && (millis() - greetingStartTime > GREETING_DURATION))
  {
    displayGreeting(currentUserName); // Reset the greeting timer by redisplaying
  }

  // Check for inactivity timeout (7 seconds)
  checkInactivityTimer();

  delay(100); // Short delay to avoid hogging the CPU
}