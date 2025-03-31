FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Ensure SQLite database directory exists and is writable
RUN mkdir -p /data
RUN chmod 777 /data

# Set environment variable for database path
ENV DATABASE_URL=sqlite:////data/reddit_dashboard.db

# Expose the port
EXPOSE 8080

# Run the application
CMD ["uvicorn", "dashboard:app", "--host", "0.0.0.0", "--port", "8080"] 