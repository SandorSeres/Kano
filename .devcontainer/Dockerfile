# NVIDIA alapú Python képfájl használata GPU támogatással (CUDA 12.8 és cuDNN)
FROM nvidia/cuda:12.8.0-cudnn-devel-ubuntu22.04

# Frissítések és szükséges csomagok telepítése
RUN apt-get update && apt-get install -y \
    python3 python3-pip python3-dev gcc git curl \
    libgl1-mesa-glx libglib2.0-0 ffmpeg libcudnn8 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# PyTorch telepítése CUDA 12 támogatással
RUN pip install --upgrade pip && pip install \
    torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121

# Faster-Whisper telepítése GPU támogatással
RUN pip install faster-whisper flask pydub

# Munka könyvtár beállítása
WORKDIR /app

# Kód bemásolása a konténerbe
COPY . .

# Fő program futtatása
CMD ["python3", "speech_to_text_api.py"]
