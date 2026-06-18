FROM node:20-slim

RUN apt-get update --fix-missing && apt-get install -y --fix-missing --no-install-recommends \
    python3 python3-pip \
    supervisor \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip3 install --break-system-packages -r requirements.txt

COPY package.json .
RUN npm install --production

COPY . .

RUN mkdir -p /music /data

EXPOSE 3000

CMD ["/usr/bin/supervisord", "-c", "/app/supervisord.conf", "-n"]
