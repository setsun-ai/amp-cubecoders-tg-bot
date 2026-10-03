import os
import sys

# bot czyta konfiguracje przy imporcie: zadnego prawdziwego Telegrama w testach
os.environ.update(TG_TOKEN="", TG_CHAT_ID="1", TG_ADMINS="1")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
