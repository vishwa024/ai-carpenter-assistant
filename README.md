# 🪵 AI Carpenter Assistant (Heritage Woodworks)

A full-stack, local-first Python AI Carpenter Assistant service that connects customer inquiries from WhatsApp directly to an automated master carpenter AI agent powered by Google Gemini.

---

## 🌟 Key Features

- **Master Carpenter AI Brain (`app/agent.py`)**:
  - Persona: **Rajesh Sharma ("Ustad Ji")**, a polite, seasoned master craftsman with 25+ years in bespoke joinery.
  - Interactive clarification: Wardrobes (sliding/hinged), Modular Kitchens (BWP Marine Ply + acrylic), Solid Wood Dining Tables (Teak/Sheesham), Wooden Entrance Doors, and Custom Beds.
  - Wood & Material Guidance: Burma/CP Teak (Sagwan), Indian Rosewood (Sheesham), IS 710 Boiling Water Proof (BWP) Marine Plywood, 1mm Laminates, Natural Veneers, and PU Polish.
  - Measurement Booking: Proactively suggests site visits with laser tape measurements or workshop visits.
  - Native Google Gemini 2.5 Flash SDK integration (`google-genai`) with an intelligent domain fallback engine for offline testing.
  - Multi-turn conversation context tracked per customer phone number with project scope extraction.

- **Meta WhatsApp Cloud API Webhook (`app/web.py`)**:
  - Built with Python's standard `ThreadingHTTPServer` / `BaseHTTPRequestHandler` (zero external framework dependency required to run).
  - Handshake Verification (`GET /webhook/whatsapp`): Validates `hub.mode == "subscribe"` and `hub.verify_token`, returning `hub.challenge`.
  - HMAC SHA-256 Signature Verification (`POST /webhook/whatsapp`): Validates incoming payload authenticity against `WHATSAPP_APP_SECRET` from the `X-Hub-Signature-256` header.
  - In-Memory Deduplication: Thread-safe message ID deduplication preventing double-replies from Meta retries.
  - Immediate 200 OK: Returns `{"ok": true}` immediately, running AI inference and outbound dispatch in the background.

- **Outbound WhatsApp Bridge (`app/whatsapp.py`)**:
  - `WhatsAppChannel` class implementing standard HTTP POST requests to Meta's WhatsApp Cloud API (`https://graph.facebook.com/v20.0/{PHONE_NUMBER_ID}/messages`).
  - Seamless local simulation mode when running without live Meta credentials.

- **Interactive Local Testing UIs**:
  - **WhatsApp Smartphone Simulator (`/simulator`)**: Realistic WhatsApp mobile smartphone UI with preloaded customer personas, one-click inquiry scenarios, typing indicators, and webhook test suite.
  - **Master Carpenter Workshop Dashboard (`/carpenter`)**: Workshop owner control center with live incoming leads, project dossier (dimensions, wood specs, visit slot), multi-turn chat feed, manual reply override, and real-time audit logs.

---

## 📂 Project Structure

```text
ai-carpenter-assistant/
├── app/
│   ├── __init__.py           # Package indicator
│   ├── config.py             # Typed configuration loader (.env support)
│   ├── agent.py              # Master Carpenter AI Brain & multi-turn session store
│   ├── whatsapp.py           # Outbound WhatsApp Cloud API bridge
│   ├── web.py                # ThreadingHTTPServer & Meta webhook endpoints
│   ├── simulator.html        # Interactive WhatsApp mobile customer simulator
│   └── carpenter.html        # Master Carpenter workshop dashboard & live monitor
├── tests/
│   ├── test_webhook.py       # Unit tests (HMAC, Deduplication, Persona, Scoping)
│   └── test_server_integration.py # Integration tests (HTTP endpoints & Handshake)
├── .env.example              # Environment variables template
├── .env                      # Local configuration file
├── requirements.txt          # Python dependencies
└── README.md                 # Complete documentation
```

---

## 🚀 Quickstart Guide

### 1. Requirements

- Python 3.9+
- (Optional) `google-genai` for Gemini API calls:
  ```bash
  pip install -r requirements.txt
  ```

### 2. Configure Environment

Copy `.env.example` to `.env` (already created with sensible defaults):

```ini
CHANNEL=web                     # 'web' for local simulator or 'whatsapp' for production
PORT=8000
HOST=0.0.0.0

# Optional: Add your Gemini API key for live AI generation
GEMINI_API_KEY=your_gemini_api_key
GEMINI_MODEL=gemini-2.5-flash

# Meta WhatsApp Cloud API credentials (required only for live WhatsApp)
WHATSAPP_TOKEN=your_meta_system_user_token
WHATSAPP_PHONE_NUMBER_ID=your_meta_phone_number_id
WHATSAPP_VERIFY_TOKEN=carpenter_secret_verify_2026
WHATSAPP_APP_SECRET=your_meta_app_secret
```

*(Note: If `GEMINI_API_KEY` is not provided, the service runs using its intelligent built-in Master Carpenter domain engine, so everything is 100% interactive out of the box!)*

### 3. Run the Service

Run from the project root:

```bash
python -m app.web
```

Output:
```text
======================================================================
  🪵  HERITAGE WOODWORKS - AI MASTER CARPENTER SERVICE  🪵
======================================================================
  • Server running on     : http://0.0.0.0:8000
  • WhatsApp Webhook      : http://0.0.0.0:8000/webhook/whatsapp
  • Customer Simulator UI : http://localhost:8000/simulator
  • Workshop Dashboard UI : http://localhost:8000/carpenter
  • Channel Mode          : WEB
  • Gemini Configured     : False (gemini-2.5-flash)
  • WhatsApp API Live     : False
  • Webhook Verify Token  : carpenter_secret_verify_2026
  • App Secret HMAC Valid : False
======================================================================
```

---

## 📱 Testing with the Web UIs

### 1. Customer WhatsApp Simulator (`http://localhost:8000/simulator`)
- Open `http://localhost:8000/simulator` in any browser.
- Select a customer persona (e.g., *Priya Sharma*, *Vikram Malhotra*).
- Click quick scenario chips or type your own carpentry question:
  - *"We need an L-shaped modular kitchen (10x8 ft) in BWP Marine Ply with Acrylic finish."*
  - *"Looking for an 8-seater handcrafted dining table in genuine Teak wood."*
  - *"Can someone visit our site this Saturday at 11:30 AM for laser measurements?"*
- Observe Rajesh Ji's response, formatting, and WhatsApp double ticks.
- Use the **Test Webhook Handshake** and **Test Deduplication** buttons for instant QA.

### 2. Workshop Console (`http://localhost:8000/carpenter`)
- Open `http://localhost:8000/carpenter`.
- View all active customer leads organized on the left.
- Inspect the automatically extracted project dossier (Project Type, Wood Specs, Dimensions, Site Visit Slot).
- Send manual replies as Master Rajesh to override or close custom deals.
- Monitor real-time webhook audits, HMAC verification, and agent latency in the terminal stream.

---

## 🔗 Connecting to Live Meta WhatsApp Cloud API

When ready to connect to production WhatsApp:

1. **Expose your local port** using a tunnel tool (such as ngrok or cloudflared):
   ```bash
   ngrok http 8000
   ```
   Copy the HTTPS forwarding URL (e.g., `https://abc-123.ngrok-free.app`).

2. **Configure Webhook in Meta Developer Portal**:
   - Go to [Meta for Developers](https://developers.facebook.com/) > Your App > **WhatsApp** > **Configuration**.
   - In **Webhook**:
     - **Callback URL**: `https://abc-123.ngrok-free.app/webhook/whatsapp`
     - **Verify token**: `carpenter_secret_verify_2026` (matching your `.env`)
   - Click **Verify and Save**. Meta will execute the GET handshake verification automatically.
   - Under **Webhook fields**, click **Manage** and subscribe to **`messages`**.

3. **Configure App Secret & Token**:
   - Copy your **App Secret** from **App Settings > Basic** into `WHATSAPP_APP_SECRET`.
   - Copy your **System User Token** into `WHATSAPP_TOKEN`.
   - Copy your **Phone Number ID** into `WHATSAPP_PHONE_NUMBER_ID`.
   - Set `CHANNEL=whatsapp` in `.env`.
   - Restart the server: `python -m app.web`.

Incoming customer messages to your WhatsApp business number will now route directly to Rajesh Sharma, and replies will be delivered back to the customer's WhatsApp chat in real time!

---

## 🧪 Running Automated Tests

Run the full suite of unit and integration tests:

```bash
python -m unittest discover tests
```

Tests cover:
- Meta webhook handshake verification with valid and invalid tokens.
- HMAC SHA-256 payload validation and tamper detection.
- Deduplication locking preventing double-replies on duplicate webhook message IDs.
- Master Carpenter agent multi-turn dialog, persona verification, and woodcraft entity extraction.
- HTTP server integration and page serving.
