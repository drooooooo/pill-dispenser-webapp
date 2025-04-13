from flask import Flask, request, redirect, url_for, flash, get_flashed_messages, render_template_string
import serial
import threading
import time
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'  # Replace with a strong secret key

# === Configure Your Serial Ports ===
try:
    arduino_port = '/dev/tty.usbmodem142401'  # Update with your Arduino port
    esp32_port = '/dev/tty.usbserial-14210'    # Update with your ESP32 port
    arduino = serial.Serial(arduino_port, 9600, timeout=1)
    esp32 = serial.Serial(esp32_port, 115200, timeout=1)
except Exception as e:
    print("Error opening serial ports:", e)
    arduino = None
    esp32 = None

# Global list to store registered users (each a dict with registration details)
registered_users = []
# Global dictionary to store dosage notification status for each user.
# Key: username; Value: a list of three booleans for the three scheduled times.
taken_status = {}
# Last dispensed time and user - to track which button was most recently pressed
last_dispensed = {"user": None, "time_index": None, "timestamp": None}
# Email configuration
email_config = {
    "enabled": True,
    "smtp_server": "smtp.gmail.com",
    "smtp_port": 587,
    "sender_email": "da.roof928@gmail.com",  # Replace with your email
    "sender_password": "your_app_password",  # Replace with your app password
    "caregiver_email": "da.roof928@gmail@example.com"  # Replace with caregiver's email
}


def send_email(recipient, subject, message):
    """Send an email to the specified recipient."""
    if not email_config["enabled"]:
        print(f"Email would be sent to {recipient} with subject: {subject}")
        return

    try:
        msg = MIMEMultipart()
        msg['From'] = email_config["sender_email"]
        msg['To'] = recipient
        msg['Subject'] = subject

        msg.attach(MIMEText(message, 'plain'))

        server = smtplib.SMTP(
            email_config["smtp_server"], email_config["smtp_port"])
        server.starttls()
        server.login(email_config["sender_email"],
                     email_config["sender_password"])
        server.send_message(msg)
        server.quit()

        print(f"Email sent to {recipient}: {subject}")
    except Exception as e:
        print(f"Failed to send email: {e}")


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


def parse_time(time_str):
    """Parse time string like '8:00 AM' into a datetime.time object."""
    try:
        return datetime.strptime(time_str, "%I:%M %p").time()
    except ValueError:
        try:
            return datetime.strptime(time_str, "%H:%M").time()
        except ValueError:
            return None


def check_upcoming_medications():
    """Check if any medications are due in the next 5 minutes and send reminder emails."""
    while True:
        current_time = datetime.now().time()

        for record in registered_users:
            user_name = record['user_name']
            patient_email = record.get('email')
            if not patient_email:
                continue

            # Check each medication time
            time_slots = [record['time1'], record['time2'], record['time3']]
            time_names = ["Morning", "Afternoon", "Evening"]

            for i, time_slot in enumerate(time_slots):
                slot_time = parse_time(time_slot)
                if not slot_time:
                    continue

                # Calculate reminder time (5 minutes before medication time)
                slot_datetime = datetime.combine(datetime.today(), slot_time)
                reminder_datetime = slot_datetime - timedelta(minutes=5)
                reminder_time = reminder_datetime.time()

                # Check if current time is within 30 seconds of the reminder time
                current_datetime = datetime.combine(
                    datetime.today(), current_time)
                time_diff = abs(
                    (current_datetime - reminder_datetime).total_seconds())

                if time_diff <= 30 and not taken_status[user_name][i]:
                    # Send reminder email
                    subject = f"Medication Reminder: {time_names[i]} Dose"
                    message = f"Hello {user_name},\n\nThis is a reminder that your {time_names[i]} medication is due in 5 minutes (at {time_slot}).\n\n"
                    message += f"Your medication for this time is:\n- Pill A: {record[f'pill_a{i+1}']} pills\n- Pill B: {
                        record[f'pill_b{i+1}']} pills\n\n"
                    message += "Please take your medication on time.\n\nThank you,\nYour Medication Dispenser System"

                    send_email(patient_email, subject, message)

        # Check every 30 seconds
        time.sleep(30)


# Background thread to listen for incoming serial messages (from the Arduino)
def serial_listener():
    while True:
        if arduino is not None and arduino.in_waiting:
            try:
                # Expect messages like "pills_taken:Dhruv:1"
                line = arduino.readline().decode(errors='ignore').strip()
                print("Received serial message:", line)  # Debug output

                if line.startswith("pills_taken:"):
                    parts = line.split(":")
                    if len(parts) >= 3:
                        username = parts[1]
                        try:
                            time_index = int(parts[2])
                        except ValueError:
                            continue

                        # Ensure the user exists and update the status
                        if username in taken_status and 0 <= time_index < 3:
                            taken_status[username][time_index] = True
                            flash(
                                f"Notification: {username}'s pills for Time {time_index+1} have been taken.")

                            # Check if this matches the last dispensed medication
                            if (last_dispensed["user"] == username and
                                    last_dispensed["time_index"] == time_index):
                                print(
                                    f"Status updated for last dispensed medication: {username}, Time {time_index+1}")

                            # Send confirmation email to caregiver
                            time_names = ["Morning", "Afternoon", "Evening"]
                            subject = f"Medication Taken: {username} - {time_names[time_index]} Dose"
                            message = f"{username} has taken their {time_names[time_index]} medication at {datetime.now().strftime('%I:%M %p')}.\n\n"
                            # Find the record for this user to include medication details
                            for record in registered_users:
                                if record['user_name'] == username:
                                    message += f"Medication details:\n- Pill A: {record[f'pill_a{time_index+1}']} pills\n- Pill B: {
                                        record[f'pill_b{time_index+1}']} pills\n\n"
                                    break

                            send_email(
                                email_config["caregiver_email"], subject, message)
            except Exception as e:
                print("Error reading from serial:", e)
        time.sleep(0.1)


# Start the background threads
listener_thread = threading.Thread(target=serial_listener, daemon=True)
listener_thread.start()

# Start the medication reminder checker thread
reminder_thread = threading.Thread(
    target=check_upcoming_medications, daemon=True)
reminder_thread.start()

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
        .user-email {
            color: #777;
            font-style: italic;
            font-size: 14px;
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
            margin-top: 30px;
        }
        .reset-btn {
            background: #e74c3c;
        }
        .reset-btn:hover {
            background: #c0392b;
        }
        .flash-messages {
            background-color: #d4edda;
            color: #155724;
            padding: 15px;
            margin-bottom: 20px;
            border-radius: 4px;
            border-left: 4px solid #28a745;
        }
        .settings-section {
            margin-top: 30px;
            padding-top: 20px;
            border-top: 1px solid #ddd;
        }
        .settings-title {
            margin-bottom: 15px;
            color: #555;
        }
        .highlighted {
            animation: highlight 2s ease-in-out;
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
    
    {% if messages %}
    <div class="flash-messages">
        {% for message in messages %}
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
                
                <div class="form-group">
                    <label for="email">Patient Email (for reminders):</label>
                    <input type="email" id="email" name="email" required>
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
            
            <div class="settings-section">
                <h3 class="settings-title">Email Notification Settings</h3>
                <form action="/email_settings" method="post">
                    <div class="form-group">
                        <label for="caregiver_email">Caregiver Email:</label>
                        <input type="email" id="caregiver_email" name="caregiver_email" 
                               value="{{ email_config.caregiver_email }}" required>
                    </div>
                    <div class="form-group">
                        <label>
                            <input type="checkbox" name="email_enabled" {% if email_config.enabled %}checked{% endif %}>
                            Enable Email Notifications
                        </label>
                    </div>
                    <div class="form-group">
                        <input type="submit" value="Save Settings">
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
                            <div class="user-email">{{ user.email }}</div>
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
                                <input type="submit" value="Dispense Morning Dose">
                            </form>
                        </div>
                        
                        <div class="dispense-btn">
                            <form action="/send/{{ i }}/1" method="post" onsubmit="return confirm('Dispense afternoon medication for {{ user.user_name }}?')">
                                <input type="submit" value="Dispense Afternoon Dose">
                            </form>
                        </div>
                        
                        <div class="dispense-btn">
                            <form action="/send/{{ i }}/2" method="post" onsubmit="return confirm('Dispense evening medication for {{ user.user_name }}?')">
                                <input type="submit" value="Dispense Evening Dose">
                            </form>
                        </div>
                    </div>
                </div>
                {% endfor %}
            {% else %}
                <p>No patients registered yet.</p>
            {% endif %}
            
            <div class="reset-section">
                <form action="/reset" method="post" onsubmit="return confirm('Reset all medication status indicators?')">
                    <input type="submit" value="Reset All Status Indicators" class="reset-btn">
                </form>
            </div>
        </div>
    </div>
</body>
</html>
'''

# Home page: displays registration form, registered users (with simplified info and status circles), and reset button.


@app.route('/', methods=['GET'])
def home():
    messages = get_flashed_messages()
    return render_template_string(
        HTML_TEMPLATE,
        messages=messages,
        registered_users=enumerate(registered_users),
        taken_status=taken_status,
        last_dispensed=last_dispensed,
        email_config=email_config
    )

# Registration route: add a new user.


@app.route('/register', methods=['POST'])
def register():
    user_name = request.form.get('name')
    email = request.form.get('email')
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
        'email': email,
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

# Send route: send dosage for a given user and chosen time.


@app.route('/send/<int:index>/<int:time_choice>', methods=['POST'])
def send(index, time_choice):
    if 0 <= index < len(registered_users) and 0 <= time_choice < 3:
        record = registered_users[index]
        arduino_command, esp32_command = calculate_commands_for_choice(
            record, time_choice)

        # Update the last dispensed info to track which button was pressed
        last_dispensed["user"] = record['user_name']
        last_dispensed["time_index"] = time_choice
        last_dispensed["timestamp"] = datetime.now()

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

        # Note: Status update now happens only when "pills_taken" message is received
        flash(
            f"Dispensing medication for {record['user_name']} at Time {time_choice+1}.")

        # If it's been 15 minutes since dispensing and status hasn't changed, notify caregiver
        def check_medication_taken():
            time.sleep(15 * 60)  # Wait 15 minutes
            if (last_dispensed["user"] == record['user_name'] and
                last_dispensed["time_index"] == time_choice and
                    not taken_status[record['user_name']][time_choice]):
                # Medication wasn't taken after 15 minutes
                time_names = ["Morning", "Afternoon", "Evening"]
                subject = f"ALERT: Missed Medication - {record['user_name']} - {time_names[time_choice]} Dose"
                message = f"ATTENTION: {record['user_name']} has not taken their {time_names[time_choice]} medication.\n\n"
                message += f"The medication was dispensed at {last_dispensed['timestamp'].strftime('%I:%M %p')}, but has not been taken.\n\n"
                message += f"Medication details:\n- Pill A: {record[f'pill_a{time_choice+1}']} pills\n- Pill B: {
                    record[f'pill_b{time_choice+1}']} pills\n\n"
                message += "Please check on the patient."

                send_email(email_config["caregiver_email"], subject, message)
                print(f"Sent medication reminder for {record['user_name']}")

        # Start a thread to check if medication was taken
        reminder_thread = threading.Thread(target=check_medication_taken)
        reminder_thread.daemon = True
        reminder_thread.start()

        return redirect(url_for('home'))
    else:
        flash("Invalid patient or time selection.")
        return redirect(url_for('home'))

# Email settings route


@app.route('/email_settings', methods=['POST'])
def email_settings():
    email_config["caregiver_email"] = request.form.get('caregiver_email')
    email_config["enabled"] = 'email_enabled' in request.form

    flash("Email notification settings updated successfully.")
    return redirect(url_for('home'))

# Reset route: resets all notifications.


@app.route('/reset', methods=['POST'])
def reset():
    for user in registered_users:
        taken_status[user['user_name']] = [False, False, False]
    flash("All medication status indicators have been reset.")
    return redirect(url_for('home'))


if __name__ == '__main__':
    # Avoid the reloader to prevent duplicate background threads.
    app.run(debug=True, host='0.0.0.0', port=5001, use_reloader=False)
