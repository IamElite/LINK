# Telegram Link Bot

A Telegram bot for generating and managing shareable links with MongoDB storage.

## Features
- Generate protected shareable links
- Track link access statistics
- Manage users and channels
- Detailed usage statistics

## Deployment

### Heroku
[![Deploy](https://www.herokucdn.com/deploy/button.svg)](https://heroku.com/deploy?template=https://github.com/yourusername/your-repo-name)

1. Click the "Deploy to Heroku" button above
2. Fill in the required environment variables:
   - `API_ID`: Your Telegram API ID from [my.telegram.org](https://my.telegram.org)
   - `API_HASH`: Your Telegram API hash from [my.telegram.org](https://my.telegram.org)
   - `BOT_TOKEN`: Your bot token from [@BotFather](https://t.me/BotFather)
   - `OWNER_ID`: Your Telegram user ID
   - `MONGO_URL`: MongoDB connection URI
   - `LOGGER_ID` (optional): Channel ID for logging
3. Click "Deploy app"

### Koyeb
[![Deploy to Koyeb](https://www.koyeb.com/static/images/deploy/button.svg)](https://app.koyeb.com/deploy?type=git&repository=https://github.com/yourusername/your-repo-name&branch=main&name=telegram-link-bot)

1. Click the "Deploy to Koyeb" button above
2. Create a Koyeb account if needed
3. In the Environment Variables section, add:
   - API_ID
   - API_HASH
   - BOT_TOKEN
   - OWNER_ID
   - MONGO_URL
   - LOGGER_ID (optional)
4. Click "Deploy"

## Running Locally

### Without Docker
1. Clone the repository:
```bash
git clone https://github.com/yourusername/your-repo-name.git
cd your-repo-name
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Create a `.env` file with your environment variables:
```env
API_ID=your_api_id
API_HASH=your_api_hash
BOT_TOKEN=your_bot_token
OWNER_ID=your_user_id
MONGO_URL=your_mongodb_uri
LOGGER_ID=your_logger_channel_id
```

4. Run the bot:
```bash
python bot.py
```

### With Docker
1. Clone the repository:
```bash
git clone https://github.com/yourusername/your-repo-name.git
cd your-repo-name
```

2. Create a `.env` file with your environment variables (same as above)

3. Build the Docker image:
```bash
docker build -t telegram-link-bot .
```

4. Run the Docker container:
```bash
docker run -d --name link-bot --env-file .env telegram-link-bot
```

## Configuration
- Replace `yourusername/your-repo-name` in the deployment buttons with your actual GitHub repository
- Make sure your MongoDB instance is accessible from the deployment platform
- For Koyeb, you may need to configure the port if running other services
