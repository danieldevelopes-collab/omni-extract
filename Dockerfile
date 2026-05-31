# omni-extract — a self-contained, fully offline text-extraction image.
#
# It bundles the Tesseract OCR engine (which, since v4, IS a trained LSTM
# neural-network model shipped as eng.traineddata) together with the Python
# stack, so `docker run` works on any machine with Docker and needs nothing
# else installed on the host. No network access is required at runtime.

FROM python:3.12-slim

# --- system layer -----------------------------------------------------------
# The Tesseract OCR engine + its English language model, plus the shared
# libraries PyMuPDF and Pillow load at runtime. We drop the apt lists afterward
# to keep the image lean.
RUN apt-get update && apt-get install -y --no-install-recommends \
        tesseract-ocr \
        tesseract-ocr-eng \
        tesseract-ocr-osd \
    && rm -rf /var/lib/apt/lists/*

# --- python layer -----------------------------------------------------------
WORKDIR /app
# Install dependencies first so this layer is cached across code changes.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
# Then the package itself (installs the `omni-extract` console script).
COPY pyproject.toml README.md LICENSE ./
COPY omniextract ./omniextract
RUN pip install --no-cache-dir .

# --- runtime ----------------------------------------------------------------
# Mount the files you want to read at /data:
#   docker run --rm -v "$PWD:/data" omni-extract scan.pdf
# With no arguments it prints which backends are live.
WORKDIR /data
ENTRYPOINT ["omni-extract"]
CMD ["--capabilities"]
