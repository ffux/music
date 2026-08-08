FROM node:20-slim

RUN set -eu; \
    for attempt in 1 2 3; do \
      rm -rf /var/lib/apt/lists/* /var/cache/apt/archives/*; \
      if apt-get -o Acquire::http::No-Cache=true update \
        && apt-get -o Acquire::http::No-Cache=true install -y --no-install-recommends \
          python3 python3-pip supervisor ffmpeg; then \
        break; \
      fi; \
      if [ "$attempt" -eq 3 ]; then exit 1; fi; \
      sleep 3; \
    done; \
    rm -rf /var/lib/apt/lists/* /var/cache/apt/archives/*

WORKDIR /app

COPY requirements.txt .
RUN pip3 install --break-system-packages -r requirements.txt

COPY package.json package-lock.json ./
RUN npm ci --omit=dev

COPY . .

RUN mkdir -p /music /data

EXPOSE 3000

CMD ["/usr/bin/supervisord", "-c", "/app/supervisord.conf", "-n"]
