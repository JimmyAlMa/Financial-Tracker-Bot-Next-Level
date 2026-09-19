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

PESAN_TIDAK_DIKENALI_FUNC = {
    "name": "pesan_tidak_dikenali",
    "description": (
        "Gunakan ini kalau pesan user TIDAK berkaitan dengan pencatatan transaksi, "
        "reminder, atau permintaan rekap keuangan."
    ),
    "parameters": {"type": "object", "properties": {}, "required": []},
}

FINANCE_TOOL = types.Tool(
    function_declarations=[
        SIMPAN_TRANSAKSI_FUNC,
        BUAT_REMINDER_FUNC,
        REKAP_BULANAN_FUNC,
        PESAN_TIDAK_DIKENALI_FUNC,
    ]
)

def build_system_prompt() -> str:
    today = datetime.now().strftime("%Y-%m-%d (%A)")
    return (
        "Kamu adalah asisten pencatat keuangan pribadi di Telegram.\n"
        "Setiap pesan user WAJIB direspons dengan memanggil SALAH SATU function yang tersedia:\n"
        "- simpan_transaksi: user cerita soal pengeluaran atau pemasukan uang\n"
        "- buat_reminder: user minta diingetin sesuatu\n"
        "- rekap_bulanan: user minta ringkasan/laporan keuangan\n"
        "- pesan_tidak_dikenali: pesan tidak berkaitan dengan ketiga hal di atas\n\n"
        "Untuk nominal uang, selalu ubah ke angka murni (contoh: '25rb' -> 25000, '1jt' -> 1000000).\n"
        f"Hari ini tanggal: {today}. Gunakan ini untuk menghitung tanggal reminder relatif "
        "(besok, minggu depan, dst)."
    )

def call_gemini(message_text: str, maximal_attempt: int = 3) -> tuple[str, dict]:
    config = types.GenerateContentConfig(
        system_instruction=build_system_prompt(),
        tools=FINANCE_TOOL,
        tool_config=types.ToolConfig(
            function_calling_config=types.FunctionCallingConfig(mode="ANY")
        )
    )

    for attempt in range(1, maximal_attempt + 1):
        try:
            response = client.models.generate_content(
                model=MODEL_NAME,
                contents=message_text,
                config=config
            )

            part = response.candidates[0].content.parts[0]
            if not part.function_call:
                raise ValueError("Gemini tidak memanggil function apapun")

            return part.function_call.name, dict(part.function_call.args)
        except Exception as e:
            if "503" in str(e) and attempt < maximal_attempt:
                logger.warning(f"Gemini sedang sibuk, coba lagi ({attempt}/{maximal_attempt})...")
                time.sleep(2 * maximal_attempt)
                continue
            raise


# ===========================================================================
# Google Sheets Helper
# ===========================================================================

def get_sheet(worksheet_name: str):
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive.readonly",
    ]

    creds_json_str = os.environ.get("GOOGLE_CREDS_JSON")
    if creds_json_str:
        creds_dict = json.loads(creds_json_str)
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    else:
        creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=scopes)
    gs_client = gspread.authorize(creds)
    return gs_client.open(GOOGLE_SHEET_NAME).worksheet(worksheet_name)

def save_transaksi(data: TransaksiData):
    sheet = get_sheet("Sheet1")
    sheet.append_row([
        datetime.now().strftime("%Y-%m-%d %H:%M"),
            data.tipe,
            data.kategori,
            data.nominal,
            data.deskripsi,
    ])

def save_remider(data: ReminderData):
    sheet = get_sheet("Reminders")
    sheet.append_row([
        datetime.now().strftime("%Y-%m-%d %H:%M"),
            data.tanggal,
            data.judul,
            data.deskripsi,
    ])