import os
import json
import time
import sys
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv
from google.oauth2 import service_account
from googleapiclient.discovery import build
from google import genai
import requests

RETRY_ATTEMPTS = 5
RETRY_DELAY = 30 * 60

load_dotenv()

TG_BOT_TOKEN = os.environ["TG_BOT_TOKEN"]
TG_GROUP_ID = os.environ["TG_GROUP_ID"]
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
GOOGLE_SA_JSON = json.loads(os.environ["GOOGLE_SA_JSON"])
GOOGLE_ID = os.environ["GOOGLE_ID"]


def fetch_birthdays():
    credentials = service_account.Credentials.from_service_account_info(
        GOOGLE_SA_JSON,
        scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
    )
    service = build("sheets", "v4", credentials=credentials)
    result = service.spreadsheets().values().get(
        spreadsheetId=GOOGLE_ID,
        range="bd!A1:E",
    ).execute()

    values = result.get("values", [])
    df = pd.DataFrame(values[1:], columns=values[0])
    df["day"] = df.birth_date.str[0:2].astype(int)
    df["month"] = df.birth_date.str[3:5].astype(int)

    today = datetime.today()
    df_bd = df.query('day == @today.day and month == @today.month and active == "TRUE"')

    return [
        {"name": r.name, "notes": r.notes, "card": r.card}
        for r in df_bd.itertuples()
    ]


def send_one(gemini_client, person):
    name = person["name"]
    notes = person["notes"]
    card = person["card"]

    response = gemini_client.models.generate_content(
        model="gemini-3-flash-preview",
        contents=f"""Сгенерируй короткое поздравление с днём рождения.

Имя: {name}
Заметки: {notes}

Требования:
- 2–3 предложения
- обращение по имени, на «ты»
- учти заметки (общие интересы, шутки, контекст отношений)
- без клише ("счастья, здоровья, успехов")
- если в заметках есть негативные характеристики человека — обыграй их по-доброму, без сарказма
- максимум 3 эмодзи на всё поздравление (или ни одного)
- можно выделить *курсивом* или жирным **шрифтом** фразу или одно слово-акцент, если уместно
- эмодзи только если он реально к месту (по интересам из заметок), не для "украшения"

Верни только текст поздравления.""",
    )

    greeting = response.text.strip()
    card_line = f"\nДля тех кто хочет поздравить: {card}" if pd.notna(card) else ""
    full_message = f"#birthday\n{greeting}{card_line}"

    r = requests.post(
        f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage",
        json={
            "chat_id": TG_GROUP_ID,
            "text": full_message,
            "parse_mode": "Markdown",
        },
    )
    if not r.ok:
        raise RuntimeError(f"Telegram {r.status_code}: {r.text}")


def main():
    gemini_client = genai.Client(api_key=GEMINI_API_KEY)
    pending = None

    for attempt in range(1, RETRY_ATTEMPTS + 1):
        print(f"Attempt {attempt}/{RETRY_ATTEMPTS}", flush=True)

        if pending is None:
            try:
                pending = fetch_birthdays()
                print(f"Found {len(pending)} birthdays today", flush=True)
            except Exception as e:
                print(f"Fetch failed: {e}", flush=True)
                if attempt == RETRY_ATTEMPTS:
                    print("All retry attempts exhausted", flush=True)
                    return 1
                print(f"Sleeping {RETRY_DELAY}s", flush=True)
                time.sleep(RETRY_DELAY)
                continue

        if not pending:
            print("Nothing to send", flush=True)
            return 0

        still_pending = []
        for person in pending:
            try:
                send_one(gemini_client, person)
                print(f"OK {person['name']}", flush=True)
            except Exception as e:
                print(f"FAIL {person['name']}: {e}", flush=True)
                still_pending.append(person)

        pending = still_pending

        if not pending:
            print("Done", flush=True)
            return 0

        if attempt == RETRY_ATTEMPTS:
            print(f"All retry attempts exhausted, {len(pending)} unsent: "
                  f"{[p['name'] for p in pending]}", flush=True)
            return 1

        print(f"{len(pending)} still pending, sleeping {RETRY_DELAY}s", flush=True)
        time.sleep(RETRY_DELAY)

    return 1


if __name__ == "__main__":
    sys.exit(main())
