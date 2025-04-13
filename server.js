// server.js - Updated for Raspberry Pi Integration

const express = require('express');
const fs = require('fs');
const path = require('path');
const app = express();
const port = 3000;

// Create data directory if it doesn't exist
const dataDir = path.join(__dirname, 'data');
if (!fs.existsSync(dataDir)) {
    fs.mkdirSync(dataDir, { recursive: true });
}

// Create models directory for face-api.js models
const modelsDir = path.join(__dirname, 'public', 'models');
if (!fs.existsSync(modelsDir)) {
    fs.mkdirSync(modelsDir, { recursive: true });
}

// Middleware to parse JSON and serve static files
app.use(express.static('public'));
app.use(express.json({ limit: '50mb' })); // Increased limit for face descriptors
app.use(express.urlencoded({ extended: true }));

// Serve index.html from the public directory
app.get('/', (req, res) => {
    res.sendFile(path.join(__dirname, 'public', 'index.html'));
});

// POST /register — Save user data to /data folder and send to Raspberry Pi if configured
app.post('/register', (req, res) => {
    try {
        const userData = req.body;

        console.log(`✅ Received registration data for: ${userData.name}`);
        console.log(`📋 Schedule contains ${userData.schedules.length} medication times`);

        // Create a sanitized filename from the user's name
        const sanitizedName = userData.name.replace(/[^a-z0-9]/gi, '_').toLowerCase();
        const filename = `data/${sanitizedName}.json`;

        // Format data specifically for Raspberry Pi if needed
        const raspberryPiData = {
            user: {
                name: userData.name,
                age: userData.age
            },
            schedules: userData.schedules.map(schedule => ({
                time: schedule.time,
                pillA: schedule.pillA,
                pillB: schedule.pillB
            })),
            faceDescriptors: userData.faceDescriptors
        };

        // Write the user data to a file
        fs.writeFileSync(filename, JSON.stringify(raspberryPiData, null, 2));

        // Here you would add code to send data to the Raspberry Pi
        // This could be via HTTP, MQTT, WebSockets, or other protocols
        console.log(`✅ Data saved locally to ${filename}`);
        console.log(`🍓 Ready to send to Raspberry Pi`);

        // Send a success response
        res.json({ status: 'success', savedTo: filename });
    } catch (error) {
        console.error('❌ Error saving registration:', error);
        res.status(500).json({ status: 'error', message: error.message });
    }
});

// Start the server
app.listen(port, () => {
    console.log(`✅ Web server running at http://localhost:${port}`);
    console.log(`💊 Pill Dispenser registration app ready`);
});