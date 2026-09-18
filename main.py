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