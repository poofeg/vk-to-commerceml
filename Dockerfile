FROM python:3.13-alpine as builder

RUN apk add --no-cache build-base libffi-dev
RUN python -m venv /opt/poetry
RUN /opt/poetry/bin/pip install --no-cache-dir -U pip setuptools
RUN /opt/poetry/bin/pip install --no-cache-dir poetry
RUN ln -svT /opt/poetry/bin/poetry /usr/local/bin/poetry
RUN poetry config virtualenvs.in-project true

FROM builder as build
WORKDIR /app

COPY pyproject.toml poetry.lock README.md ./
RUN poetry install --no-cache --no-interaction --no-ansi --no-root --without=dev

COPY vk_to_commerceml vk_to_commerceml
RUN poetry install --no-cache --no-interaction --no-ansi --without=dev

FROM python:3.13-alpine

WORKDIR /app
COPY --from=build /app /app
EXPOSE 8080/tcp
CMD ["/app/.venv/bin/uvicorn", "--log-level=info", "--proxy-headers", "--forwarded-allow-ips=*", \
     "--host", "0.0.0.0", "--port", "8080", \
     "vk_to_commerceml.api.main:app"]
