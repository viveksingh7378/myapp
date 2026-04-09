FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app/ ./app/
RUN useradd -m appuser && chown -R appuser /app
USER appuser
EXPOSE 5003
CMD ["python", "-m", "flask", "--app", "app.app", "run", "--host=0.0.0.0", "--port=5003"]
