"""SQLite Database Layer for AI Master Carpenter Assistant.

Provides thread-safe persistence for:
- Customers & CRM profiles
- Multi-turn conversation histories
- Quotations with reproducible calculation breakdowns
- Appointments & site visits
- Material and hardware catalogue
- System audit logs and event history
- Database backups
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import shutil
import sqlite3
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("carpenter.database")

DB_DIR = Path(__file__).resolve().parent.parent / "data"
DB_PATH = DB_DIR / "carpenter.db"
BACKUP_DIR = DB_DIR / "backups"


class Database:
    """Thread-safe SQLite Database Manager."""

    def __init__(self, db_path: Optional[Path] = None) -> None:
        self.db_path = db_path or DB_PATH
        self._local = threading.local()
        self._lock = threading.Lock()
        self._ensure_directories()
        self._init_schema()
        self._seed_default_catalogue()

    def _ensure_directories(self) -> None:
        """Ensure data and backup directories exist."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    def get_connection(self) -> sqlite3.Connection:
        """Get a thread-local SQLite connection with WAL mode enabled."""
        if not hasattr(self._local, "conn") or self._local.conn is None:
            conn = sqlite3.connect(
                str(self.db_path),
                timeout=30.0,
                check_same_thread=False,
            )
            conn.row_factory = sqlite3.Row
            # Enable WAL mode for high concurrency between reader threads & background writer
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            conn.execute("PRAGMA foreign_keys=ON;")
            self._local.conn = conn
        return self._local.conn

    def _init_schema(self) -> None:
        """Create database tables if they do not exist."""
        with self._lock:
            conn = self.get_connection()
            with conn:
                conn.executescript("""
                -- Customers & CRM Table
                CREATE TABLE IF NOT EXISTS customers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    phone TEXT UNIQUE NOT NULL,
                    name TEXT,
                    language TEXT DEFAULT 'en',
                    locality TEXT,
                    lead_source TEXT DEFAULT 'WhatsApp',
                    lead_status TEXT DEFAULT 'NEW_ENQUIRY',
                    budget INTEGER,
                    human_handover INTEGER DEFAULT 0,
                    project_type TEXT,
                    dimensions TEXT,
                    preferred_materials TEXT,
                    consultation_mode TEXT DEFAULT 'in_person',
                    follow_up_date TEXT,
                    notes TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_customers_phone ON customers(phone);
                CREATE INDEX IF NOT EXISTS idx_customers_status ON customers(lead_status);
                CREATE INDEX IF NOT EXISTS idx_customers_locality ON customers(locality);

                -- Conversations & Messages Table
                CREATE TABLE IF NOT EXISTS conversations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    phone TEXT NOT NULL,
                    message_id TEXT,
                    role TEXT NOT NULL, -- 'user', 'model', 'carpenter_override'
                    text TEXT NOT NULL,
                    media_json TEXT,
                    stage TEXT,
                    source TEXT,
                    latency_ms INTEGER DEFAULT 0,
                    timestamp REAL NOT NULL,
                    FOREIGN KEY (phone) REFERENCES customers(phone) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_conv_phone ON conversations(phone);
                CREATE INDEX IF NOT EXISTS idx_conv_timestamp ON conversations(timestamp);

                -- Quotations with full reproducible calculation breakdown
                CREATE TABLE IF NOT EXISTS quotations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    quotation_id TEXT UNIQUE NOT NULL,
                    phone TEXT NOT NULL,
                    level TEXT NOT NULL, -- 'preliminary', 'detailed', 'final_approved'
                    project_type TEXT NOT NULL,
                    dimensions TEXT,
                    sqft REAL,
                    breakdown_json TEXT NOT NULL,
                    total_amount INTEGER NOT NULL,
                    status TEXT DEFAULT 'pending', -- 'pending', 'approved', 'sent', 'rejected'
                    approved_by TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    FOREIGN KEY (phone) REFERENCES customers(phone) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_quotations_phone ON quotations(phone);
                CREATE INDEX IF NOT EXISTS idx_quotations_level ON quotations(level);

                -- Appointments Table
                CREATE TABLE IF NOT EXISTS appointments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    phone TEXT NOT NULL,
                    status TEXT NOT NULL, -- 'requested', 'confirmed', 'rescheduled', 'cancelled'
                    slot_time TEXT NOT NULL,
                    address TEXT,
                    locality TEXT,
                    project_scope TEXT,
                    notes TEXT,
                    approved_by_carpenter INTEGER DEFAULT 1,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    FOREIGN KEY (phone) REFERENCES customers(phone) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_appointments_phone ON appointments(phone);
                CREATE INDEX IF NOT EXISTS idx_appointments_status ON appointments(status);

                -- Editable Material & Hardware Catalogue
                CREATE TABLE IF NOT EXISTS catalogue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    item_id TEXT UNIQUE NOT NULL,
                    name TEXT NOT NULL,
                    category TEXT NOT NULL, -- 'board', 'timber', 'finish', 'hardware', 'service'
                    unit TEXT NOT NULL,     -- 'sq.ft', 'running_ft', 'piece', 'set', 'unit'
                    rate REAL NOT NULL,
                    effective_date TEXT NOT NULL,
                    source TEXT NOT NULL,
                    is_verified INTEGER DEFAULT 1,
                    description TEXT,
                    created_at REAL NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_catalogue_category ON catalogue(category);

                -- Audit Logs Table
                CREATE TABLE IF NOT EXISTS audit_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category TEXT NOT NULL,
                    message TEXT NOT NULL,
                    details_json TEXT,
                    timestamp REAL NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_audit_time ON audit_logs(timestamp);
                """)
            logger.info(f"Database schema initialized at {self.db_path}")

    def _seed_default_catalogue(self) -> None:
        """Seed default verified workshop catalogue items if table is empty."""
        conn = self.get_connection()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM catalogue")
        count = cur.fetchone()[0]
        if count > 0:
            return

        now_str = time.strftime("%Y-%m-%d")
        default_items = [
            ("mat_bwp_marine_18", "18mm IS 710 BWP Waterproof Marine Plywood", "board", "sq.ft", 115.0, now_str, "Workshop Supplier Invoice", 1, "Boiling Waterproof 100% calibrated marine ply for kitchen and wardrobes"),
            ("mat_mdf_18", "18mm HDHMR / Exterior Grade MDF", "board", "sq.ft", 82.0, now_str, "Standard Supplier Rate", 1, "High Density High Moisture Resistance board for dry area panelling"),
            ("mat_comm_ply_18", "18mm Commercial MR Grade Plywood", "board", "sq.ft", 68.0, now_str, "Market Benchmark", 1, "Moisture resistant commercial ply for dry storage"),
            ("mat_cp_teak", "Seasoned CP Teak (Sagwan) Solid Timber", "timber", "cu.ft", 3800.0, now_str, "Timber Yard Ahmedabad", 1, "First grade Central Province natural teak, seasoned against warping"),
            ("mat_sheesham", "Solid Indian Rosewood (Sheesham)", "timber", "cu.ft", 2400.0, now_str, "Timber Yard Ahmedabad", 1, "Heavy solid hardwood for dining tables and sturdy beds"),
            ("fin_laminate_1mm", "1mm Anti-Scratch Decorative Laminate", "finish", "sq.ft", 55.0, now_str, "Catalogue Benchmark", 1, "Premium 1mm matte anti-scratch laminate with edge banding"),
            ("fin_pu_polish_4coat", "Italian 4-Coat Polyurethane (PU) Polish", "finish", "sq.ft", 280.0, now_str, "Workshop Fabrication Rate", 1, "4-coat spray PU system with sealers and UV protective topcoat"),
            ("fin_acrylic_gloss", "High-Gloss Acrylic Finish Sheet", "finish", "sq.ft", 120.0, now_str, "Supplier Catalog", 1, "Seamless high-gloss modern kitchen shutter finish"),
            ("fin_natural_melamine", "Natural Melamine Polish (Teak/Sheesham)", "finish", "sq.ft", 110.0, now_str, "Workshop Polish Team", 1, "Wood-grain protective semi-gloss coat"),
            ("hard_hettich_hinges", "Hettich German Soft-Close Concealed Hinges", "hardware", "pair", 340.0, now_str, "Hardware Distributor", 1, "Tested for 80,000 opening cycles with soft damping"),
            ("hard_tandem_box", "Soft-Close Kitchen Tandem Drawer Channels", "hardware", "set", 2150.0, now_str, "Hardware Distributor", 1, "Full-extension 45kg load-rated tandem drawer systems"),
            ("hard_bed_hydraulic", "Heavy-Duty Hydraulic Bed Storage Lift Mechanism", "hardware", "set", 4800.0, now_str, "Hardware Distributor", 1, "Gas spring hydraulic lifts for King/Queen storage beds"),
            ("srv_carpentry_labour", "Master Workshop Joinery & Fabrication Labour", "service", "sq.ft", 480.0, now_str, "Heritage Workshop Costing", 1, "Precision joinery, edge bending, carcass assembly"),
            ("srv_site_fitting", "On-Site Leveling & Final Installation", "service", "sq.ft", 160.0, now_str, "Heritage Fitting Team", 1, "Laser alignment, wall fixing, trim fitting"),
            ("srv_local_transport", "Ahmedabad Local Workshop Transport & Packaging", "service", "unit", 1800.0, now_str, "Workshop Logistics", 1, "Protective foam wrap and direct doorstep delivery")
        ]

        with self._lock:
            with conn:
                conn.executemany("""
                INSERT OR IGNORE INTO catalogue (item_id, name, category, unit, rate, effective_date, source, is_verified, description, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, [(item[0], item[1], item[2], item[3], item[4], item[5], item[6], item[7], item[8], time.time()) for item in default_items])
        logger.info(f"Seeded {len(default_items)} default catalogue items.")

    def backup(self) -> Path:
        """Create a point-in-time snapshot backup of the database."""
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        backup_path = BACKUP_DIR / f"carpenter_backup_{timestamp}.db"
        with self._lock:
            # Checkpoint WAL before copying to guarantee data integrity
            conn = self.get_connection()
            conn.execute("PRAGMA wal_checkpoint(FULL);")
            shutil.copy2(str(self.db_path), str(backup_path))
        logger.info(f"Database backed up successfully to {backup_path}")
        return backup_path

    def get_catalogue(self, category: Optional[str] = None) -> List[Dict[str, Any]]:
        """Fetch verified catalogue items, optionally filtered by category."""
        conn = self.get_connection()
        cur = conn.cursor()
        if category:
            cur.execute("SELECT * FROM catalogue WHERE category = ? ORDER BY category, name", (category,))
        else:
            cur.execute("SELECT * FROM catalogue ORDER BY category, name")
        return [dict(r) for r in cur.fetchall()]

    def update_catalogue_rate(self, item_id: str, new_rate: float, source: Optional[str] = None) -> bool:
        """Update market benchmark rate for a catalogue material or service."""
        conn = self.get_connection()
        now_str = time.strftime("%Y-%m-%d")
        with conn:
            if source:
                cur = conn.execute(
                    "UPDATE catalogue SET rate = ?, effective_date = ?, source = ? WHERE item_id = ?",
                    (float(new_rate), now_str, source, item_id),
                )
            else:
                cur = conn.execute(
                    "UPDATE catalogue SET rate = ?, effective_date = ? WHERE item_id = ?",
                    (float(new_rate), now_str, item_id),
                )
            return cur.rowcount > 0

    def add_catalogue_item(
        self,
        item_id: str,
        name: str,
        category: str,
        unit: str,
        rate: float,
        source: str = "Workshop Quote",
        description: str = "",
    ) -> bool:
        """Add a new material or hardware specification to the catalogue."""
        conn = self.get_connection()
        now = time.time()
        now_str = time.strftime("%Y-%m-%d")
        with conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO catalogue (
                    item_id, name, category, unit, rate, effective_date, source, is_verified, description, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                """,
                (item_id, name, category, unit, float(rate), now_str, source, description, now),
            )
            return True


# Global Database singleton
db = Database()
