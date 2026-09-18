from dotenv import load_dotenv
import os
import json
import logging
import time
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, ValidationError
from google import genai
from google.genai import types
import gspread
from google.oauth2.service_account import Credentials
from telegram import Update
from telegram.ext import Application, ContextTypes, MessageHandler, filters

load_dotenv()

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GOOGLE_SHEET_NAME = "Jimmy's Financial logs"
SERVICE_ACCOUNT_FILE = "service_account.json"

logging.basicConfig(
    level=logging.INFO,
    filename="app.log",
    filemode='a',
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

client = genai.Client(api_key=GEMINI_API_KEY)
MODEL_NAME = "gemini-3.1-flash-lite"


# ===========================================================================
# Pydantic Schemas 
# ===========================================================================

class TransaksiData(BaseModel):
    kategori: str
    nominal: float = Field(gt=0)
    tipe: Literal["pemasukan", "pengeluaran"]
    deskripsi: str = ""

class ReminderData(BaseModel):
    judul: str
    tanggal: str
    deskripsi: str = ""

class RekapParams(BaseModel):
    bulan: Optional[int] = Field(default=None, ge=1, le=12)
    tahun: Optional[int] = Field(default=None, ge=2000, le=2100)


# ===========================================================================
# Function Declarations
# ===========================================================================

SIMPAN_TRANSAKSI_FUNC = {
    "name": "simpan_transaksi",
    "description": (
        "Simpan transaksi keuangan (pemasukan atau pengeluaran) ke pencatatan. "
        "Gunakan ini kalau user cerita soal beli sesuatu, bayar sesuatu, dapat uang, gajian, dst."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "kategori": {
                "type": "string",
                "description": "Kategori transaksi, misal: makanan, transport, gaji, belanja",
            },
            "nominal": {
                "type": "number",
                "description": "Jumlah uang dalam Rupiah, angka positif murni (contoh: '25rb' jadi 25000)",
            },
            "tipe": {
                "type": "string",
                "enum": ["pemasukan", "pengeluaran"],
                "description": "Apakah ini uang masuk atau keluar",
            },
            "deskripsi": {
                "type": "string",
                "description": "Deskripsi singkat transaksi",
            },
        },
        "required": ["kategori", "nominal", "tipe"],
    },
}

BUAT_REMINDER_FUNC = {
    "name": "buat_reminder",
    "description": (
        "Buat pengingat/reminder untuk user. Gunakan ini kalau user minta diingetin "
        "sesuatu di tanggal tertentu, misal bayar tagihan."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "judul": {
                "type": "string",
                "description": "Judul singkat reminder",
            },
            "tanggal": {
                "type": "string",
                "description": (
                    "Tanggal reminder format YYYY-MM-DD. Kalau user sebut relatif "
                    "(besok, minggu depan), hitung tanggal aslinya berdasarkan hari ini."
                ),
            },
            "deskripsi": {
                "type": "string",
                "description": "Detail tambahan reminder",
            },
        },
        "required": ["judul", "tanggal"],
    },
}

REKAP_BULANAN_FUNC = {
    "name": "rekap_bulanan",
    "description": (
        "Tampilkan rekap/ringkasan pemasukan dan pengeluaran bulanan. "
        "Gunakan ini kalau user minta rekap, laporan, atau ringkasan keuangan."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "bulan": {
                "type": "integer",
                "description": "Bulan yang mau direkap (1-12). Kosongkan kalau user tidak sebut.",
            },
            "tahun": {
                "type": "integer",
                "description": "Tahun yang mau direkap. Kosongkan kalau user tidak sebut.",
            },
        },
        "required": [],
    },
}