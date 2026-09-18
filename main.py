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