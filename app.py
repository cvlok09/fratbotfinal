
from flask import Flask, request, render_template, jsonify
import os
import gspread
import json
from datetime import datetime
from oauth2client.service_account import ServiceAccountCredentials
from openai import OpenAI

app = Flask(__name__)

# Set up OpenAI client (use OPENAI_API_KEY environment variable in Render)
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Google Sheets setup
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name("fratbot-462503-b6150505e7bc.json", scope)
client_gs = gspread.authorize(creds)

# Target Sheet + Tabs
SHEET_URL = "https://docs.google.com/spreadsheets/d/1_eJMQPOZgto1xU-gQdVdv6BKeWEKozJfpDbj55_eFbE/edit"
SHEET_NAME = "2025-2026 Omicron-Epsilon (USD) Membership Roster"
LOG_SHEET_NAME = "Logs"

sheet = client_gs.open_by_url(SHEET_URL)
roster = sheet.worksheet(SHEET_NAME)
try:
    logs = sheet.worksheet(LOG_SHEET_NAME)
except:
    logs = sheet.add_worksheet(title=LOG_SHEET_NAME, rows="1000", cols="5")
    logs.append_row(["Timestamp", "Action", "Target", "Details"])

# Helpers
def normalize_field(field_name, member):
    lower_field = field_name.strip().lower()
    for key in member:
        if key.lower() == lower_field:
            return key
    return None

def find_member(name):
    name = name.lower().strip()
    rows = roster.get_all_records()
    for i, row in enumerate(rows):
        full = f"{row['First Name']} {row['Last Name']}".lower()
        if name in full:
            return i + 2, row
        if name == row['First Name'].lower().strip():
            return i + 2, row
    return None, None

def update_payment(name, amount):
    idx, member = find_member(name)
    if not member:
        return f"No match found for '{name}'."
    paid_col = list(member.keys()).index("Dues Payed") + 1
    new_paid = float(member["Dues Payed"] or 0) + amount
    roster.update_cell(idx, paid_col, new_paid)
    logs.append_row([datetime.now().isoformat(), "Update Payment", name, f"+${amount} → ${new_paid}"])
    return f"Updated {name.title()}'s payment. Total now: ${new_paid:.2f}."

def set_payment(name, amount):
    idx, member = find_member(name)
    if not member:
        return f"No match found for '{name}'."
    paid_col = list(member.keys()).index("Dues Payed") + 1
    roster.update_cell(idx, paid_col, amount)
    logs.append_row([datetime.now().isoformat(), "Set Payment", name, f"Set to ${amount}"])
    return f"Set {name.title()}'s payment to ${amount:.2f}."

def get_info(name, field):
    _, member = find_member(name)
    if not member:
        return f"No match found for '{name}'."
    match = normalize_field(field, member)
    if not match:
        return f"Field '{field}' not found. Available fields: {', '.join(member.keys())}"
    return f"{name.title()}'s {match} is {member.get(match, 'Not found')}"

def set_field(name, field, value):
    idx, member = find_member(name)
    if not member:
        return f"Couldn't find '{name}'."
    match = normalize_field(field, member)
    if not match:
        return f"Field '{field}' doesn’t exist. Available fields: {', '.join(member.keys())}"
    col_index = list(member.keys()).index(match) + 1
    roster.update_cell(idx, col_index, value)
    logs.append_row([datetime.now().isoformat(), "Set Field", name, f"{match} = {value}"])
    return f"{match} for {name.title()} updated to: {value}"

def count_fully_paid():
    members = roster.get_all_records()
    count = sum(1 for m in members if float(m['Dues Payed']) >= float(m['Dues Owed']))
    return f"✅ {count} members have paid in full."

def current_dues_amount():
    members = roster.get_all_records()
    return f"📌 Current dues: ${float(members[0]['Dues Owed']):.2f}" if members else "No data found."

def count_with_email():
    members = roster.get_all_records()
    count = sum(1 for m in members if m['Email'].strip())
    return f"📧 {count} members have provided emails."

def list_unpaid():
    members = roster.get_all_records()
    lines = ["🧾 Unpaid Members:"]
    for m in sorted(members, key=lambda x: (x['Last Name'], x['First Name'])):
        owed, paid = float(m['Dues Owed']), float(m['Dues Payed'])
        if paid < owed:
            lines.append(f"- {m['First Name']} {m['Last Name']} | Paid: ${paid:.2f} | Owes: ${owed - paid:.2f}")
    return "\n".join(lines) if len(lines) > 1 else "🎉 All dues are paid."

def list_with_balances():
    members = roster.get_all_records()
    lines = ["📋 Payment Breakdown:", "Name                          | Paid     | Owes", "------------------------------|----------|---------"]
    for m in sorted(members, key=lambda x: (x['Last Name'], x['First Name'])):
        owed, paid = float(m['Dues Owed']), float(m['Dues Payed'])
        if paid < owed:
            name = f"{m['First Name']} {m['Last Name']:<26}"
            lines.append(f"{name[:30]:<30} | ${paid:7.2f} | ${(owed - paid):6.2f}")
    return "\n".join(lines) if len(lines) > 3 else "🎉 Everyone has paid in full."

def check_paid_in_full(name):
    _, member = find_member(name)
    if not member:
        return f"No match found for '{name}'."
    owed, paid = float(member['Dues Owed']), float(member['Dues Payed'])
    if paid >= owed:
        return f"✅ {name.title()} has paid in full (${paid:.2f})."
    else:
        return f"❌ {name.title()} still owes ${owed - paid:.2f} (${paid:.2f} paid)."

def get_payment_amount(name):
    _, member = find_member(name)
    if not member:
        return f"No match found for '{name}'."
    paid = float(member['Dues Payed'])
    return f"{name.title()} has paid ${paid:.2f}."

def get_total_collected():
    members = roster.get_all_records()
    total = sum(float(m['Dues Payed']) for m in members)
    return f"💰 Total collected: ${total:.2f}"

def get_total_outstanding():
    members = roster.get_all_records()
    total = sum(float(m['Dues Owed']) - float(m['Dues Payed']) for m in members)
    return f"📉 Total outstanding: ${total:.2f}"

def get_total_expected():
    members = roster.get_all_records()
    total = sum(float(m['Dues Owed']) for m in members)
    return f"📈 Total expected if all dues are paid: ${total:.2f}"

def handle_input(user_input):
    try:
        prompt = f'''
You are a fraternity assistant bot for dues, payments, contact info, and reporting.
Supported actions:
- check_paid
- get_payment_amount
- add_payment
- set_payment
- lookup
- set_field
- count_fully_paid
- current_dues_amount
- count_with_email
- list_unpaid
- list_with_balances
- get_total_collected
- get_total_outstanding
- get_total_expected

Respond only in JSON like:
{{ "action": "check_paid", "name": "Chris" }}

Input: {user_input}
'''
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
        )
        data = json.loads(response.choices[0].message.content)
        action = data.get("action")
        name = data.get("name", "")
        amount = data.get("amount", 0)
        field = data.get("field", "")
        value = data.get("value", "")

        if action in ["check_paid", "check_if_paid"]:
            return check_paid_in_full(name)
        elif action == "get_payment_amount":
            return get_payment_amount(name)
        elif action == "add_payment":
            return update_payment(name, float(amount))
        elif action == "set_payment":
            return set_payment(name, float(amount))
        elif action == "lookup":
            return get_info(name, field)
        elif action == "set_field":
            return set_field(name, field, value)
        elif action == "count_fully_paid":
            return count_fully_paid()
        elif action == "current_dues_amount":
            return current_dues_amount()
        elif action == "count_with_email":
            return count_with_email()
        elif action == "list_unpaid":
            return list_unpaid()
        elif action == "list_with_balances":
            return list_with_balances()
        elif action == "get_total_collected":
            return get_total_collected()
        elif action == "get_total_outstanding":
            return get_total_outstanding()
        elif action == "get_total_expected":
            return get_total_expected()
        else:
            return "❓ Sorry, I couldn't understand what to do."
    except Exception as e:
        return f"⚠️ Error: {e}"

@app.route("/", methods=["GET", "POST"])
def index():
    response = ""
    if request.method == "POST":
        user_input = request.form.get("query")
        response = handle_input(user_input)
    return render_template("index.html", response=response)

@app.route("/ask", methods=["POST"])
def ask():
    try:
        user_input = request.json.get("input")
        response = handle_input(user_input)
        return response
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
