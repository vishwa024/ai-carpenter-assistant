/**
 * WhatsApp Web Bridge (Non-Meta / 100% Direct WhatsApp Web QR).
 * 
 * Uses @whiskeysockets/baileys to connect directly via WhatsApp Web protocol.
 * - Zero Meta Developer Account needed.
 * - Zero Meta Cloud API / App tokens needed.
 * - Runs 100% locally on your laptop.
 * - Scans QR code with your mobile WhatsApp (Linked Devices).
 * - Forwards incoming customer messages to the Python AI Master Carpenter (http://localhost:8000/api/simulate).
 * - Automatically sends Rajesh Sharma's response back to the customer on real WhatsApp!
 */

const { default: makeWASocket, DisconnectReason, useMultiFileAuthState } = require('@whiskeysockets/baileys');
const pino = require('pino');
const qrcodeTerminal = require('qrcode-terminal');
const QRCode = require('qrcode');
const http = require('http');
const path = require('path');
const fs = require('fs');

const PYTHON_API_URL = process.env.PYTHON_API_URL || 'http://localhost:8000/api/simulate';
const PORT = process.env.BRIDGE_PORT || 3000;
const AUTH_DIR = path.join(__dirname, 'auth_info');

let currentQR = null;
let connectionStatus = 'initializing';
let connectedNumber = null;

// Start a lightweight local HTTP server for viewing QR code in the browser
const server = http.createServer(async (req, res) => {
    if (req.url === '/' || req.url === '/qr') {
        res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
        
        if (connectionStatus === 'open') {
            res.end(`
                <!DOCTYPE html>
                <html>
                <head>
                    <title>WhatsApp Connected — Heritage Woodworks</title>
                    <meta name="viewport" content="width=device-width, initial-scale=1">
                    <style>
                        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0b141a; color: #e9edef; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; }
                        .card { background: #111b21; padding: 36px; border-radius: 16px; text-align: center; max-width: 460px; box-shadow: 0 8px 24px rgba(0,0,0,0.4); border: 1px solid #222e35; }
                        .badge { display: inline-block; background: #00a884; color: #111b21; font-weight: bold; padding: 6px 14px; border-radius: 20px; font-size: 14px; margin-bottom: 16px; }
                        h2 { margin: 0 0 10px 0; color: #e9edef; }
                        p { color: #8696a0; line-height: 1.5; font-size: 15px; margin-bottom: 20px; }
                        .phone { font-size: 18px; color: #25d366; font-weight: bold; }
                        .footer { font-size: 13px; color: #667781; margin-top: 24px; border-top: 1px solid #222e35; padding-top: 16px; }
                    </style>
                </head>
                <body>
                    <div class="card">
                        <div class="badge">LIVE AUTOMATION ACTIVE</div>
                        <h2>WhatsApp Connected!</h2>
                        <p>Linked to WhatsApp account: <span class="phone">${connectedNumber || 'Your Mobile Phone'}</span></p>
                        <p>Whenever a customer messages your WhatsApp, <b>Rajesh Sharma (AI Master Carpenter)</b> will automatically craft and send the response in real-time!</p>
                        <div class="footer">Heritage Woodworks & Joinery • Zero Meta API Required</div>
                    </div>
                </body>
                </html>
            `);
            return;
        }

        if (currentQR) {
            try {
                const qrImage = await QRCode.toDataURL(currentQR, { width: 320, margin: 2 });
                res.end(`
                    <!DOCTYPE html>
                    <html>
                    <head>
                        <title>Scan WhatsApp QR Code — Heritage Woodworks</title>
                        <meta name="viewport" content="width=device-width, initial-scale=1">
                        <meta http-equiv="refresh" content="20">
                        <style>
                            body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0b141a; color: #e9edef; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; }
                            .card { background: #111b21; padding: 32px; border-radius: 16px; text-align: center; max-width: 440px; box-shadow: 0 8px 24px rgba(0,0,0,0.4); border: 1px solid #222e35; }
                            h2 { margin: 0 0 12px 0; color: #00a884; font-size: 22px; }
                            .instructions { color: #8696a0; text-align: left; font-size: 14px; line-height: 1.7; margin: 16px 0; background: #202c33; padding: 14px 18px; border-radius: 10px; }
                            .instructions ol { margin: 0; padding-left: 20px; }
                            .qr-wrap { background: #ffffff; padding: 14px; border-radius: 12px; display: inline-block; margin: 14px 0; }
                            .qr-wrap img { display: block; }
                            .status { font-size: 13px; color: #ffd279; }
                        </style>
                    </head>
                    <body>
                        <div class="card">
                            <h2>🪵 Link Your Real WhatsApp</h2>
                            <div class="instructions">
                                <ol>
                                    <li>Open <b>WhatsApp</b> on your mobile phone</li>
                                    <li>Tap <b>Menu (⋮)</b> or <b>Settings</b> > <b>Linked Devices</b></li>
                                    <li>Tap <b>Link a Device</b> and point your phone at this screen</li>
                                </ol>
                            </div>
                            <div class="qr-wrap">
                                <img src="${qrImage}" alt="Scan QR Code" />
                            </div>
                            <div class="status">⚡ Scan with your phone's WhatsApp to link instantly! (No Meta account required)</div>
                        </div>
                    </body>
                    </html>
                `);
                return;
            } catch (err) {
                res.end(`Error generating QR: ${err.message}`);
                return;
            }
        }

        res.end(`
            <!DOCTYPE html>
            <html>
            <body style="background:#0b141a;color:#e9edef;font-family:sans-serif;text-align:center;padding:50px;">
                <h3>Initializing WhatsApp Web Connection...</h3>
                <p>Generating QR code, please wait 3 seconds and refresh.</p>
                <script>setTimeout(() => location.reload(), 2000);</script>
            </body>
            </html>
        `);
        return;
    }

    if (req.url === '/status') {
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ status: connectionStatus, connectedNumber }));
        return;
    }

    res.writeHead(404);
    res.end('Not Found');
});

server.listen(PORT, () => {
    console.log(`[QR Web Server] View QR Code in your browser at: http://localhost:${PORT}`);
});

async function startWhatsApp() {
    console.log('[WHATSAPP] Initializing WhatsApp Web client...');
    const { state, saveCreds } = await useMultiFileAuthState(AUTH_DIR);

    const sock = makeWASocket({
        auth: state,
        logger: pino({ level: 'silent' }),
        printQRInTerminal: false,
    });

    sock.ev.on('creds.update', saveCreds);

    sock.ev.on('connection.update', (update) => {
        const { connection, lastDisconnect, qr } = update;

        if (qr) {
            currentQR = qr;
            connectionStatus = 'scan_qr';
            console.log('\n============================================================');
            console.log('  SCAN THIS QR CODE WITH YOUR PHONE WHATSAPP');
            console.log('  Settings > Linked Devices > Link a device');
            console.log(`  Or view in browser: http://localhost:${PORT}`);
            console.log('============================================================\n');
            qrcodeTerminal.generate(qr, { small: true });
        }

        if (connection === 'close') {
            const statusCode = (lastDisconnect?.error)?.output?.statusCode;
            const isLoggedOut = statusCode === DisconnectReason.loggedOut || statusCode === 401;
            console.log('[WHATSAPP] Connection closed. StatusCode:', statusCode, 'LoggedOut:', isLoggedOut);
            connectionStatus = 'closed';
            currentQR = null;
            if (isLoggedOut) {
                console.log('[WHATSAPP] Session ended or logged out. Resetting auth state for fresh QR scan...');
                try {
                    fs.rmSync(AUTH_DIR, { recursive: true, force: true });
                } catch (e) {}
                setTimeout(startWhatsApp, 2000);
            } else {
                console.log('[WHATSAPP] Reconnecting in 3 seconds...');
                setTimeout(startWhatsApp, 3000);
            }
        } else if (connection === 'open') {
            connectionStatus = 'open';
            currentQR = null;
            connectedNumber = sock.user?.id ? sock.user.id.split(':')[0] : 'Linked Phone';
            try {
                sock.sendPresenceUpdate('available');
            } catch (e) {}
            console.log('\n============================================================');
            console.log(`  [+] WHATSAPP CONNECTED SUCCESSFULLY!`);
            console.log(`  * Account: +${connectedNumber}`);
            console.log(`  * AI Engine: ${PYTHON_API_URL}`);
            console.log(`  * Status: Live automated replies active on real WhatsApp!`);
            console.log('============================================================\n');
        }
    });

    // Listen for incoming customer messages
    sock.ev.on('messages.upsert', async (m) => {
        if (m.type !== 'notify') return;

        for (const msg of m.messages) {
            // Ignore messages sent by self or empty messages
            if (msg.key.fromMe) continue;
            if (!msg.message) continue;

            const remoteJid = msg.key.remoteJid;
            // Ignore group chats and status broadcasts
            if (remoteJid.endsWith('@g.us') || remoteJid === 'status@broadcast') continue;

            const senderPhone = remoteJid.replace('@s.whatsapp.net', '');
            let customerName = (msg.pushName || '').trim();
            const invalidProfileNames = ['others', 'other', 'customer', 'client', 'user', 'admin', 'contact', 'unknown', 'test', 'demo', 'none', 'null', 'undefined'];
            if (invalidProfileNames.includes(customerName.toLowerCase())) {
                customerName = '';
            }

            // Extract text body
            const textBody = msg.message.conversation ||
                             msg.message.extendedTextMessage?.text ||
                             msg.message.imageMessage?.caption ||
                             '';

            if (!textBody.trim()) continue;

            console.log(`\n[INCOMING WHATSAPP] From: +${senderPhone} (${customerName || 'Customer'}) | Text: "${textBody}"`);

            // 1. Mark incoming message as read
            try {
                await sock.readMessages([msg.key]);
            } catch (e) {}

            // 2. Start "typing..." (3 dots) presence update on customer's phone
            // WhatsApp mobile clients require presenceSubscribe + continuous pulse every 800ms
            try {
                await sock.sendPresenceUpdate('available');
                await sock.presenceSubscribe(remoteJid);
                await sock.sendPresenceUpdate('composing', remoteJid);
            } catch (e) {}

            // Continuously pulse the 'composing' presence every 800ms so the 3 dots stay visible
            const typingInterval = setInterval(async () => {
                try {
                    await sock.sendPresenceUpdate('composing', remoteJid);
                } catch (e) {}
            }, 800);

            const startComposing = Date.now();

            // 3. Call Python AI Master Carpenter Backend
            let replyText = null;
            try {
                const response = await fetch(PYTHON_API_URL, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        phone: senderPhone,
                        text: textBody,
                        name: customerName,
                        id: msg.key.id,
                    }),
                });

                if (response.ok) {
                    const data = await response.json();
                    replyText = data.reply || data.response_text;
                } else {
                    console.error(`[AI ERROR] Python server returned ${response.status}`);
                }
            } catch (err) {
                console.error(`[ERROR] Failed to forward message to AI backend: ${err.message}`);
                console.log(`Tip: Make sure the Python server is running on port 8000!`);
            }

            // 4. Natural human typing delay (3.5 seconds) so customer sees the "typing..." 3 dots
            const minTypingDelayMs = 3500;
            const elapsed = Date.now() - startComposing;
            if (elapsed < minTypingDelayMs) {
                await new Promise(r => setTimeout(r, minTypingDelayMs - elapsed));
            }
            clearInterval(typingInterval);

            // 5. Deliver response and pause typing presence
            if (replyText) {
                console.log(`[OUTBOUND REPLY] Sending automatic reply to +${senderPhone}...\n`);
                try {
                    await sock.sendMessage(remoteJid, { text: replyText });
                    console.log(`[SUCCESS] Automated reply delivered on real WhatsApp!`);
                } catch (sendErr) {
                    console.error(`[SEND ERROR] Failed to send message: ${sendErr.message}`);
                }
            }
            try {
                await sock.sendPresenceUpdate('paused', remoteJid);
            } catch (e) {}
        }
    });
}

process.on('uncaughtException', (err) => {
    console.error('[UNCAUGHT EXCEPTION]', err?.message || err);
});
process.on('unhandledRejection', (err) => {
    console.error('[UNHANDLED REJECTION]', err?.message || err);
});

startWhatsApp();
