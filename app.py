from flask import Flask, request, redirect, url_for, flash, get_flashed_messages, render_template_string
import serial
import threading
import time
from datetime import datetime
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'  # Replace with a strong secret key

# === Configure Your Serial Ports ===
try:
    arduino_port = '/dev/tty.usbmodem1423201'  # Update with your Arduino port
    esp32_port = '/dev/tty.usbserial-14210'    # Update with your ESP32 port
    arduino = serial.Serial(arduino_port, 9600, timeout=1)
    esp32 = serial.Serial(esp32_port, 115200, timeout=1)
except Exception as e:
    print("Error opening serial ports:", e)
    arduino = None
    esp32 = None

# Global list to store registered users (each a dict with registration details)
registered_users = []
# Global dictionary to store dosage status for each user.
# Key: username; Value: a list of three booleans for the three scheduled times.
taken_status = {}
# Last dispensed time and user - to track which button was most recently pressed
last_dispensed = {"user": None, "time_index": None, "timestamp": None}

# === Email Configuration ===
EMAIL_ENABLED = True  # Set to False to disable email notifications during testing
EMAIL_SENDER = "medication.dispenser@gmail.com"  # Update with your sender email
EMAIL_PASSWORD = "eqym bmbm cqzb nqfx"  # Update with your email password
EMAIL_RECIPIENT = "da.roof928@gmail.com"  # Update with caregiver's email
SMTP_SERVER = "smtp.example.com"  # Update with your SMTP server
SMTP_PORT = 587  # Update with your SMTP port (typically 587 for TLS)


def send_email_notification(patient_name, medication_time, pill_a_count, pill_b_count):
    """
    Send an email notification to the caregiver about a dispensed medication.

    Args:
        patient_name: Name of the patient who received medication
        medication_time: Time period (Morning, Afternoon, Evening)
        pill_a_count: Number of Pill A dispensed
        pill_b_count: Number of Pill B dispensed
    """
    if not EMAIL_ENABLED:
        print("Email notifications disabled.")
        return

    try:
        # Create email message
        msg = MIMEMultipart()
        msg['From'] = EMAIL_SENDER
        msg['To'] = EMAIL_RECIPIENT
        msg['Subject'] = f"Medication Alert: {patient_name} - {medication_time} Dose"

        # Format timestamp
        current_time = datetime.now().strftime("%A, %B %d, %Y at %I:%M %p")

        # Email body
        email_body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6;">
            <h2>Medication Dispenser Notification</h2>
            <p>This is an automated notification from the Medication Dispenser System.</p>
            
            <div style="background-color: #f0f0f0; padding: 15px; border-radius: 5px; margin: 15px 0;">
                <p><strong>Patient:</strong> {patient_name}</p>
                <p><strong>Medication Time:</strong> {medication_time}</p>
                <p><strong>Dispensed:</strong> {current_time}</p>
                <p><strong>Medication Dispensed:</strong></p>
                <ul>
                    <li>Pill A: {pill_a_count}</li>
                    <li>Pill B: {pill_b_count}</li>
                </ul>
            </div>
            
            <p>Please contact the patient to ensure medication was taken as prescribed.</p>
            <p>This is an automated message. Please do not reply.</p>
        </body>
        </html>
        """

        msg.attach(MIMEText(email_body, 'html'))

        # Connect to SMTP server and send email
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()  # Encrypt the connection
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
            server.send_message(msg)

        print(
            f"Email notification sent for {patient_name}'s {medication_time} medication")

    except Exception as e:
        print(f"Failed to send email notification: {e}")


def calculate_commands_for_choice(record, time_choice):
    """
    Given a registration record and a chosen time index (0, 1, or 2), compute the command strings.
    The Arduino command uses the pill values for the chosen time.
    The ESP32 command sends the full schedule.
    """
    user_name = record['user_name']
    time1 = record['time1']
    time2 = record['time2']
    time3 = record['time3']
    pill_a_values = [record['pill_a1'], record['pill_a2'], record['pill_a3']]
    pill_b_values = [record['pill_b1'], record['pill_b2'], record['pill_b3']]

    selected_a = pill_a_values[time_choice]
    selected_b = pill_b_values[time_choice]
    # Arduino command: dispense:[user]:[Pill A #]:[Pill B #]
    arduino_command = f"dispense:{user_name}:{selected_a}:{selected_b}"
    # ESP32 command (full schedule):
    esp32_command = (
        f"NAME:{user_name};"
        f"TIME1:{time1};TIME2:{time2};TIME3:{time3};"
        f"PILL1:[{record['pill_a1']},{record['pill_a2']},{record['pill_a3']}];"
        f"PILL2:[{record['pill_b1']},{record['pill_b2']},{record['pill_b3']}]"
    )
    return arduino_command, esp32_command


# HTML Template
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Medication Dispenser System</title>
    <style>
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f7f9fc;
        }
        h1, h2, h3, h4 {
            color: #2c3e50;
        }
        h1 {
            text-align: center;
            margin-bottom: 30px;
            color: #3498db;
            border-bottom: 2px solid #3498db;
            padding-bottom: 10px;
        }
        .container {
            display: flex;
            flex-wrap: wrap;
            gap: 30px;
        }
        .section {
            background: white;
            border-radius: 8px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.1);
            padding: 25px;
            margin-bottom: 25px;
        }
        .registration-form {
            flex: 1;
            min-width: 300px;
        }
        .users-list {
            flex: 2;
            min-width: 500px;
        }
        .form-group {
            margin-bottom: 15px;
        }
        .form-row {
            display: flex;
            justify-content: space-between;
            margin-bottom: 10px;
        }
        label {
            display: block;
            margin-bottom: 5px;
            color: #555;
            font-weight: 500;
        }
        input[type="text"], input[type="email"] {
            width: 100%;
            padding: 10px;
            border: 1px solid #ddd;
            border-radius: 4px;
            font-size: 14px;
        }
        input[type="submit"], button {
            background: #3498db;
            color: white;
            border: none;
            padding: 10px 15px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 14px;
            transition: background 0.3s;
        }
        input[type="submit"]:hover, button:hover {
            background: #2980b9;
        }
        .pill-group {
            background: #f8f9fa;
            padding: 15px;
            border-radius: 6px;
            margin-bottom: 15px;
        }
        .pill-group h4 {
            margin-top: 0;
            color: #3498db;
            border-bottom: 1px solid #eee;
            padding-bottom: 10px;
        }
        .pill-time {
            display: flex;
            align-items: center;
            gap: 15px;
        }
        .pill-time label {
            width: 120px;
        }
        .user-card {
            background: #fff;
            border-radius: 6px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            padding: 20px;
            margin-bottom: 20px;
            border-left: 5px solid #3498db;
        }
        .user-info {
            margin-bottom: 15px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .user-title {
            font-size: 20px;
            color: #3498db;
            margin-bottom: 8px;
        }
        .user-schedule {
            display: flex;
            justify-content: space-between;
            background: #f8f9fa;
            padding: 12px;
            border-radius: 6px;
            margin-bottom: 15px;
        }
        .time-slot {
            text-align: center;
            padding: 10px;
            background: white;
            border-radius: 4px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            flex: 1;
            margin: 0 5px;
        }
        .time-label {
            font-weight: bold;
            margin-bottom: 5px;
            color: #555;
        }
        .status-circle {
            display: inline-block;
            width: 20px;
            height: 20px;
            border-radius: 50%;
            margin-right: 10px;
            vertical-align: middle;
        }
        .dispense-buttons {
            display: flex;
            justify-content: space-between;
            gap: 10px;
        }
        .dispense-btn {
            flex: 1;
            text-align: center;
        }
        .pill-counts {
            font-size: 14px;
            color: #777;
            margin-top: 5px;
        }
        .reset-section {
            text-align: center;
            margin-top: 20px;
        }
        .patient-reset-btn {
            background: #f39c12;
            margin-top: 10px;
        }
        .patient-reset-btn:hover {
            background: #e67e22;
        }
        .disabled-btn {
            background: #bdc3c7;
            cursor: not-allowed;
        }
        .disabled-btn:hover {
            background: #bdc3c7;
        }
        .flash-messages {
            background-color: #d4edda;
            color: #155724;
            padding: 15px;
            margin-bottom: 20px;
            border-radius: 4px;
            border-left: 4px solid #28a745;
        }
        .highlighted {
            animation: highlight 2s ease-in-out;
        }
        .email-config {
            margin-top: 20px;
            background: #f8f9fa;
            padding: 15px;
            border-radius: 6px;
        }
        @keyframes highlight {
            0% { background-color: #fff; }
            50% { background-color: #fffacd; }
            100% { background-color: #fff; }
        }
    </style>
    <script>
    function updateStatus() {
        // This function will be called periodically to refresh the page
        location.reload();
    }
    
    // Refresh the page every 30 seconds to show updated status
    setInterval(updateStatus, 30000);
    </script>
</head>
<body>
    <h1>Medication Dispenser System</h1>
    
    {% if get_flashed_messages() %}
    <div class="flash-messages">
        {% for message in get_flashed_messages() %}
            <div>{{ message }}</div>
        {% endfor %}
    </div>
    {% endif %}
    
    <div class="container">
        <div class="section registration-form">
            <h2>Register New Patient</h2>
            <form action="/register" method="post">
                <div class="form-group">
                    <label for="name">Patient Name:</label>
                    <input type="text" id="name" name="name" required>
                </div>
                
                <div class="pill-group">
                    <h4>Daily Schedule</h4>
                    <div class="form-group">
                        <label for="time1">Morning Time:</label>
                        <input type="text" id="time1" name="time1" value="8:00 AM" required>
                    </div>
                    <div class="form-group">
                        <label for="time2">Afternoon Time:</label>
                        <input type="text" id="time2" name="time2" value="1:00 PM" required>
                    </div>
                    <div class="form-group">
                        <label for="time3">Evening Time:</label>
                        <input type="text" id="time3" name="time3" value="8:00 PM" required>
                    </div>
                </div>
                
                <div class="pill-group">
                    <h4>Pill A Dosage</h4>
                    <div class="pill-time">
                        <label for="pill_a1">Morning:</label>
                        <input type="text" id="pill_a1" name="pill_a1" value="2" required>
                    </div>
                    <div class="pill-time">
                        <label for="pill_a2">Afternoon:</label>
                        <input type="text" id="pill_a2" name="pill_a2" value="1" required>
                    </div>
                    <div class="pill-time">
                        <label for="pill_a3">Evening:</label>
                        <input type="text" id="pill_a3" name="pill_a3" value="2" required>
                    </div>
                </div>
                
                <div class="pill-group">
                    <h4>Pill B Dosage</h4>
                    <div class="pill-time">
                        <label for="pill_b1">Morning:</label>
                        <input type="text" id="pill_b1" name="pill_b1" value="1" required>
                    </div>
                    <div class="pill-time">
                        <label for="pill_b2">Afternoon:</label>
                        <input type="text" id="pill_b2" name="pill_b2" value="0" required>
                    </div>
                    <div class="pill-time">
                        <label for="pill_b3">Evening:</label>
                        <input type="text" id="pill_b3" name="pill_b3" value="1" required>
                    </div>
                </div>
                
                <div class="form-group">
                    <input type="submit" value="Register Patient">
                </div>
            </form>
            
            <div class="email-config">
                <h3>Email Notification Settings</h3>
                <form action="/update_email" method="post">
                    <div class="form-group">
                        <label for="caregiver_email">Caregiver Email:</label>
                        <input type="email" id="caregiver_email" name="caregiver_email" value="{{ caregiver_email }}" required>
                    </div>
                    <div class="form-group">
                        <input type="submit" value="Update Email Settings">
                    </div>
                </form>
            </div>
        </div>
        
        <div class="section users-list">
            <h2>Registered Patients</h2>
            
            {% if registered_users %}
                {% for i, user in registered_users %}
                <div class="user-card {% if last_dispensed.user == user.user_name %}highlighted{% endif %}">
                    <div class="user-info">
                        <div>
                            <div class="user-title">{{ user.user_name }}</div>
                        </div>
                    </div>
                    
                    <div class="user-schedule">
                        <div class="time-slot {% if last_dispensed.user == user.user_name and last_dispensed.time_index == 0 %}highlighted{% endif %}">
                            <div class="time-label">Morning</div>
                            <div>{{ user.time1 }}</div>
                            <div>
                                <span class="status-circle" style="background-color: {% if taken_status[user.user_name][0] %}green{% else %}red{% endif %};"></span>
                                {% if taken_status[user.user_name][0] %}Taken{% else %}Pending{% endif %}
                            </div>
                            <div class="pill-counts">Pill A: {{ user.pill_a1 }}, Pill B: {{ user.pill_b1 }}</div>
                        </div>
                        
                        <div class="time-slot {% if last_dispensed.user == user.user_name and last_dispensed.time_index == 1 %}highlighted{% endif %}">
                            <div class="time-label">Afternoon</div>
                            <div>{{ user.time2 }}</div>
                            <div>
                                <span class="status-circle" style="background-color: {% if taken_status[user.user_name][1] %}green{% else %}red{% endif %};"></span>
                                {% if taken_status[user.user_name][1] %}Taken{% else %}Pending{% endif %}
                            </div>
                            <div class="pill-counts">Pill A: {{ user.pill_a2 }}, Pill B: {{ user.pill_b2 }}</div>
                        </div>
                        
                        <div class="time-slot {% if last_dispensed.user == user.user_name and last_dispensed.time_index == 2 %}highlighted{% endif %}">
                            <div class="time-label">Evening</div>
                            <div>{{ user.time3 }}</div>
                            <div>
                                <span class="status-circle" style="background-color: {% if taken_status[user.user_name][2] %}green{% else %}red{% endif %};"></span>
                                {% if taken_status[user.user_name][2] %}Taken{% else %}Pending{% endif %}
                            </div>
                            <div class="pill-counts">Pill A: {{ user.pill_a3 }}, Pill B: {{ user.pill_b3 }}</div>
                        </div>
                    </div>
                    
                    <div class="dispense-buttons">
                        <div class="dispense-btn">
                            <form action="/send/{{ i }}/0" method="post" onsubmit="return confirm('Dispense morning medication for {{ user.user_name }}?')">
                                <input type="submit" value="Dispense Morning Dose" 
                                    {% if taken_status[user.user_name][0] %}disabled class="disabled-btn"{% endif %}>
                            </form>
                        </div>
                        
                        <div class="dispense-btn">
                            <form action="/send/{{ i }}/1" method="post" onsubmit="return confirm('Dispense afternoon medication for {{ user.user_name }}?')">
                                <input type="submit" value="Dispense Afternoon Dose"
                                    {% if taken_status[user.user_name][1] %}disabled class="disabled-btn"{% endif %}>
                            </form>
                        </div>
                        
                        <div class="dispense-btn">
                            <form action="/send/{{ i }}/2" method="post" onsubmit="return confirm('Dispense evening medication for {{ user.user_name }}?')">
                                <input type="submit" value="Dispense Evening Dose"
                                    {% if taken_status[user.user_name][2] %}disabled class="disabled-btn"{% endif %}>
                            </form>
                        </div>
                    </div>
                    
                    <div class="reset-section">
                        <form action="/reset_patient/{{ i }}" method="post" onsubmit="return confirm('Reset medication status for {{ user.user_name }}?')">
                            <input type="submit" value="Reset Patient Status" class="patient-reset-btn">
                        </form>
                    </div>
                </div>
                {% endfor %}
            {% else %}
                <p>No patients registered yet.</p>
            {% endif %}
        </div>
    </div>
</body>
</html>
'''

# Home page: displays registration form, registered users (with simplified info and status circles), and reset button.


@app.route('/', methods=['GET'])
def home():
    return render_template_string(
        HTML_TEMPLATE,
        registered_users=enumerate(registered_users),
        taken_status=taken_status,
        last_dispensed=last_dispensed,
        caregiver_email=EMAIL_RECIPIENT
    )

# Registration route: add a new user.


@app.route('/register', methods=['POST'])
def register():
    user_name = request.form.get('name')
    time1 = request.form.get('time1')
    time2 = request.form.get('time2')
    time3 = request.form.get('time3')
    pill_a1 = request.form.get('pill_a1')
    pill_a2 = request.form.get('pill_a2')
    pill_a3 = request.form.get('pill_a3')
    pill_b1 = request.form.get('pill_b1')
    pill_b2 = request.form.get('pill_b2')
    pill_b3 = request.form.get('pill_b3')
    record = {
        'user_name': user_name,
        'time1': time1,
        'time2': time2,
        'time3': time3,
        'pill_a1': pill_a1,
        'pill_a2': pill_a2,
        'pill_a3': pill_a3,
        'pill_b1': pill_b1,
        'pill_b2': pill_b2,
        'pill_b3': pill_b3
    }
    registered_users.append(record)
    # Initialize the taken status for the new user.
    taken_status[user_name] = [False, False, False]
    flash(f"Patient {user_name} registered successfully.")
    return redirect(url_for('home'))

# Route to update caregiver email


@app.route('/update_email', methods=['POST'])
def update_email():
    global EMAIL_RECIPIENT
    email = request.form.get('caregiver_email')
    if email:
        EMAIL_RECIPIENT = email
        flash(f"Caregiver email updated to {email}")
    return redirect(url_for('home'))

# Send route: send dosage for a given user and chosen time.


@app.route('/send/<int:index>/<int:time_choice>', methods=['POST'])
def send(index, time_choice):
    if 0 <= index < len(registered_users) and 0 <= time_choice < 3:
        record = registered_users[index]
        user_name = record['user_name']

        # Check if this dose has already been taken
        if taken_status[user_name][time_choice]:
            flash(f"This dose has already been dispensed for {user_name}.")
            return redirect(url_for('home'))

        arduino_command, esp32_command = calculate_commands_for_choice(
            record, time_choice)

        # Update the last dispensed info to track which button was pressed
        last_dispensed["user"] = user_name
        last_dispensed["time_index"] = time_choice
        last_dispensed["timestamp"] = datetime.now()

        # Mark the dose as taken immediately (no need to wait for serial confirmation)
        taken_status[user_name][time_choice] = True

        if arduino:
            arduino.write((arduino_command + "\n").encode())
            print("Sent to Arduino:", arduino_command)
        else:
            print("Arduino serial not available.")
        if esp32:
            esp32.write((esp32_command + "\n").encode())
            print("Sent to ESP32:", esp32_command)
        else:
            print("ESP32 serial not available.")

        # Get the time period name and pill counts
        time_periods = ["Morning", "Afternoon", "Evening"]
        time_period = time_periods[time_choice]
        pill_a_count = record[f'pill_a{time_choice+1}']
        pill_b_count = record[f'pill_b{time_choice+1}']

        # Send email notification
        send_email_notification(user_name, time_period,
                                pill_a_count, pill_b_count)

        flash(
            f"Dispensing medication for {user_name} at Time {time_choice+1}. Email notification sent.")
        return redirect(url_for('home'))
    else:
        flash("Invalid patient or time selection.")
        return redirect(url_for('home'))

# Reset single patient route


@app.route('/reset_patient/<int:index>', methods=['POST'])
def reset_patient(index):
    if 0 <= index < len(registered_users):
        user = registered_users[index]
        user_name = user['user_name']
        taken_status[user_name] = [False, False, False]
        flash(f"Medication status for {user_name} has been reset.")
    return redirect(url_for('home'))


if __name__ == '__main__':
    # Start with simplified functionality - no need for serial listener thread
    app.run(debug=True, host='0.0.0.0', port=5001, use_reloader=False)
