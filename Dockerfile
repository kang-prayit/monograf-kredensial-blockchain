FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV DATA_DIR=/data
EXPOSE 8000
CMD ["sh", "-c", "cd analytics && ([ -f out/metrics.json ] || python train_oulad.py) && cd ../backend && uvicorn app:app --host 0.0.0.0 --port 8000"]
