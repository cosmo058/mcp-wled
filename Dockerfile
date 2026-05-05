FROM python:3.11-slim

WORKDIR /app

RUN pip install uv

COPY pyproject.toml .
RUN uv pip install --system -e .

COPY server.py wled.py matrix.py ./

CMD ["python", "server.py"]
