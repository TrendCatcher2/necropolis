FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py .
COPY static ./static
RUN useradd --create-home demo && chown -R demo /app
USER demo
# DEMO_FRONTEND: v1 first (archive it), then v2. NECROPOLIS_VERIFICATION_TOKEN: optional file proof.
ENV DEMO_FRONTEND=v1 PORT=8080
EXPOSE 8080
CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT} --proxy-headers"]
