# Build using the prepared Railway preview context.
FROM python:3.11-slim
WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends fonts-liberation2 fonts-dejavu-core \
    && if [ ! -d /usr/share/fonts/truetype/liberation2 ]; then \
         ln -s liberation /usr/share/fonts/truetype/liberation2; \
       fi \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt backend/requirements.txt
RUN pip install --disable-pip-version-check --no-cache-dir -r backend/requirements.txt
COPY backend backend
COPY railway_preview.py seed_preview.py start-preview.sh ./
COPY delivery_identity.json ./

RUN python - <<'PY'
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from backend.app.services.booklets import _register_booklet_serif

regular, bold = _register_booklet_serif(pdfmetrics, TTFont)
assert (regular, bold) == ("BookletSerif", "BookletSerifBold")
russian_letters = set(range(0x410, 0x450)) | {0x401, 0x451}
for name in (regular, bold):
    glyphs = pdfmetrics.getFont(name).face.charToGlyph
    assert russian_letters.issubset(glyphs), f"Missing Russian glyphs in {name}"
print("Railway Cyrillic PDF font coverage PASS")
PY

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
CMD ["sh", "/app/start-preview.sh"]
