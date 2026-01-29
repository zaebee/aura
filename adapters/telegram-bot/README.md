# Aura Telegram Bot Adapter

This microservice provides a Telegram interface for the Aura Platform, allowing users to search for deals and negotiate prices directly via Telegram.

## Setup Instructions

### 1. Get a Telegram Bot Token
To use this bot, you need a token from Telegram's BotFather:
1.  Open Telegram and search for [@BotFather](https://t.me/botfather).
2.  Send the `/newbot` command.
3.  Follow the instructions to choose a name and username for your bot.
4.  BotFather will provide you with an API token. Save this token.

### 2. Configure Environment Variables
Set the following environment variables (e.g., in your `.env` file or `compose.yml`):
- `AURA_TELEGRAM__BOT_TOKEN`: The token you received from BotFather.
- `AURA_TELEGRAM__CORE_GRPC_URL`: The address of the `core-service` (default: `core-service:50051`).

### 3. Run with Docker Compose
From the root directory:
```bash
docker compose up telegram-bot
```

## Features
- `/start`: Welcome message and instructions.
- `/search <query>`: Search for deals using the Aura Core Service.
- **Negotiation**: Click on a search result to start a negotiation session. Enter your bid as a number.
