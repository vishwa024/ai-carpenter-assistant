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

---

