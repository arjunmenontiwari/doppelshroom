# Image for Hugging Face Spaces (also runs anywhere Docker does).
FROM python:3.13-slim

# Spaces run the app as user 1000; the app needs to write its cache/ folder, so it owns the files.
RUN useradd -m -u 1000 user
USER user
ENV PATH="/home/user/.local/bin:$PATH" PYTHONUNBUFFERED=1
WORKDIR /home/user/app

COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=user . .

EXPOSE 7860
# One worker: the rate limits are counted per process. --proxy-headers makes those limits see each visitor's
# address instead of the Spaces proxy's.
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "7860", "--workers", "1", "--proxy-headers", "--forwarded-allow-ips", "*"]
