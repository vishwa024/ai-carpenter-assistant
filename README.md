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

- **WhatsApp Web Direct Access (`app/web.py`)**:
  - Built with Python's standard `ThreadingHTTPServer` / `BaseHTTPRequestHandler` (zero external framework dependency required to run).
  - **Direct WhatsApp Web Redirect** (`GET /whatsapp`): Opens `https://web.whatsapp.com` directly in the browser — no Meta Cloud API needed.
  - **wa.me Deep Links** (`GET /whatsapp/chat/<phone>`): Redirects to `https://wa.me/<phone>` to start a chat with any customer instantly.
  - In-Memory Deduplication: Thread-safe message ID deduplication preventing double-replies from retries.
  - Immediate 200 OK: Returns `{"ok": true}` immediately, running AI inference in the background.

- **Outbound WhatsApp Web Bridge (`app/whatsapp.py`)**:
  - `WhatsAppChannel` class providing direct browser access to WhatsApp Web.
  - Generates `wa.me` deep links for starting chats with customers.
  - No Meta API credentials required — just open WhatsApp Web in your browser and chat.

- **Interactive Local Testing UIs**:
  - **WhatsApp Smartphone Simulator (`/simulator`)**: Realistic WhatsApp mobile smartphone UI with preloaded customer personas, one-click inquiry scenarios, typing indicators, and WhatsApp Web access buttons.
  - **Master Carpenter Workshop Dashboard (`/carpenter`)**: Workshop owner control center with live incoming leads, project dossier (dimensions, wood specs, visit slot), multi-turn chat feed, manual reply override, and real-time audit logs.

---

## 📂 Project Structure

```text
ai-carpenter-assistant/
├── app/
│   ├── __init__.py           # Package indicator
│   ├── config.py             # Typed configuration loader (.env support)
│   ├── agent.py              # Master Carpenter AI Brain & multi-turn session store
│   ├── whatsapp.py           # WhatsApp Web bridge (wa.me deep links)
│   ├── web.py                # ThreadingHTTPServer & WhatsApp Web redirect endpoints
│   ├── simulator.html        # Interactive WhatsApp mobile customer simulator
│   └── carpenter.html        # Master Carpenter workshop dashboard & live monitor
├── tests/
│   ├── test_webhook.py       # Unit tests (Deduplication, Persona, Scoping, WhatsApp Web)
│   └── test_server_integration.py # Integration tests (HTTP endpoints & redirects)
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

# WhatsApp Web Direct Access (no Meta API needed)
# The app redirects to https://web.whatsapp.com directly in the browser
# and provides wa.me deep links for starting chats with customers.
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
  [+] HERITAGE WOODWORKS - AI MASTER CARPENTER SERVICE
======================================================================
  * Local Web Simulator   : http://localhost:8000/simulator
  * Workshop Dashboard UI : http://localhost:8000/carpenter
  * WhatsApp Web Access   : http://localhost:8000/whatsapp
  * Server Listening on   : 0.0.0.0:8000
  * Channel Mode          : WEB
  * Gemini Configured     : False (gemini-2.5-flash)
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
- Use the **💬 Open WhatsApp Web** button to open WhatsApp Web directly in a new browser tab.
- Use the **💬 Chat on WhatsApp** button to start a chat with the selected customer via `wa.me` deep link.

### 2. Workshop Console (`http://localhost:8000/carpenter`)
- Open `http://localhost:8000/carpenter`.
- View all active customer leads organized on the left.
- Inspect the automatically extracted project dossier (Project Type, Wood Specs, Dimensions, Site Visit Slot).
- Send manual replies as Master Rajesh to override or close custom deals.
- Click **💬 Open WhatsApp Web** to access WhatsApp Web directly.
- Click **💬 WhatsApp** next to the manual reply box to open a chat with the selected customer.

---

## 💬 Using WhatsApp Web Direct Access

This project does **not** require Meta WhatsApp Cloud API credentials. Instead, it provides direct browser access to WhatsApp Web:

1. **Open WhatsApp Web**: Click the **"Open WhatsApp Web"** button on either the Simulator or Dashboard. This redirects to `https://web.whatsapp.com`.
2. **Scan QR Code**: Scan the QR code with your phone to link your WhatsApp account.
3. **Start a Chat**: Use the **"Chat on WhatsApp"** button to open a `wa.me` deep link for any customer. This opens a chat window with that customer in WhatsApp Web.
4. **Copy Chat Link**: Use the **"Copy Chat Link"** button to copy the `wa.me` link to your clipboard for sharing.

### Available Routes

| Route | Description |
|-------|-------------|
| `/whatsapp` | Redirects to `https://web.whatsapp.com` |
| `/whatsapp/chat/<phone>` | Redirects to `https://wa.me/<phone>` to start a chat |
| `/whatsapp/chat/<phone>?text=<message>` | Same as above, but pre-fills the message box with your text |

### Sending an AI reply to WhatsApp (one click)

1. Chat with Rajesh Ji in the Simulator (`/simulator`).
2. Type the **customer's real number** in the *Customer WhatsApp Number* box (country code, digits only — e.g. `919876543210`). The number is remembered in your browser.
3. Click **💬 Send to WhatsApp** on any AI reply. WhatsApp Web opens with Rajesh's full message already typed in the message box — just press Enter.
4. On the Dashboard (`/carpenter`), the *Send As Rajesh* button also records the reply in the transcript **and** opens WhatsApp with the same text pre-filled.

> Note: the AI reply text is passed via `?text=` on the `wa.me` deep link, which is how WhatsApp's official click-to-chat API works. Nothing is sent automatically — you always confirm by pressing Enter in WhatsApp.

---

## 🧪 Running Automated Tests

Run the full suite of unit and integration tests:

```bash
python -m unittest discover tests
```

Tests cover:
- WhatsApp Web redirect and wa.me deep link generation.
- Deduplication locking preventing double-replies on duplicate message IDs.
- Master Carpenter agent multi-turn dialog, persona verification, and woodcraft entity extraction.
- HTTP server integration and page serving.