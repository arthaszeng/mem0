FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
ARG PIP_INDEX_URL=https://pypi.org/simple/
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -i ${PIP_INDEX_URL} -r requirements.txt

COPY . .

EXPOSE 8760
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8760"]
