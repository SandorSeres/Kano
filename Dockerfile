# Használjuk a tiangolo/uvicorn-gunicorn-fastapi alapképet, amely optimalizált FastAPI alkalmazásokhoz.
FROM tiangolo/uvicorn-gunicorn-fastapi:python3.9

# Állítsuk be a munkakönyvtárat
WORKDIR /app
ENV PORT=8080
EXPOSE 8080

# Másoljuk be a requirements.txt fájlt
COPY requirements.txt .

# Telepítsük a szükséges csomagokat
RUN pip install --no-cache-dir -r requirements.txt

# Másoljuk be a konfigurációs, statikus és sablon fájlokat
COPY ./config /app/config
COPY ./static /app/static
COPY ./templates /app/templates

# Másoljuk be a main.py fájlt a gyökérbe
COPY ./main.py /app/main.py

# Az alapképet általában úgy tervezték, hogy a FastAPI alkalmazást automatikusan indítsa.
# Ha szükséges, itt megadhatod a CMD-t, de győződj meg róla, hogy helyes elérési utat adsz.
CMD ["python", "/app/main.py"]
