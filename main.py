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