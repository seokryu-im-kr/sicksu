# Sick - QR Meal Check-in System

A daily meal check-in management system using QR codes.

## Features

- **QR Check-in**: Daily QR code issuance per user with webcam scanning
- **Duplicate Prevention**: One check-in per user per day
- **User Management**: Create, deactivate, and delete users via admin dashboard
- **Role-based Access**: Three-tier permission system (Superadmin / Admin / User)
- **Password Policy**: zxcvbn-based strength validation with forced initial password change

## Tech Stack

- **Backend**: Python, Flask, SQLAlchemy, Gunicorn
- **Frontend**: TypeScript, Tailwind CSS
- **Database**: SQLite

## Installation

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
npm install
```

## Environment Variables

Create a `.env` file in the project root.

```
ADMIN_USERNAME=<superadmin-username>
ADMIN_PASSWORD=<superadmin-password>
DATABASE_URL=sqlite:///sick.db
```

`SECRET_KEY` is auto-generated at runtime if not set.

> **Warning**: Never commit the `.env` file to version control.

## Running

```bash
# Development
source .venv/bin/activate
python app.py

# Production (Gunicorn)
./run.sh start
./run.sh stop
./run.sh restart
```

Default port: `18888`

## Routes

| Path | Description | Access |
|------|-------------|--------|
| `/login` | Login | Public |
| `/today-qr` | Daily QR code | Authenticated |
| `/status` | Personal check-in history | Authenticated |
| `/reader` | QR code scanner | Public |
| `/admin` | Admin dashboard | Admin |
| `/admin/users` | User management | Admin |
| `/admin/records` | Check-in records | Admin |

## Security Notes

- Change the superadmin default password before deployment
- Ensure `.env`, `instance/`, and `*.db` are listed in `.gitignore`
- Do not use `debug=True` in production
