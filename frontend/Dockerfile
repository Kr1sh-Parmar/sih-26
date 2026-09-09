# The officer console. Built, then served as static files.
#
# Not `vite dev`. A dev server in a demo is a machine that recompiles while a
# panel is watching, and `npm run build` is also the only thing that runs
# `tsc -b`, so a type error would otherwise reach the demo table unnoticed.

FROM node:22-alpine AS build

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm ci --no-audit --no-fund || npm install --no-audit --no-fund

COPY . .

# Vite inlines this at build time, so it is a build argument rather than a
# runtime environment variable. Override for a different host:
#   docker compose build --build-arg VITE_API_URL=http://checkpoint-01:8000 console
ARG VITE_API_URL=http://localhost:8000
ENV VITE_API_URL=$VITE_API_URL

RUN npm run build


FROM nginx:alpine AS serve

COPY --from=build /app/dist /usr/share/nginx/html

# The console is a single-page app: every route has to fall through to
# index.html or a reload on /screening/<id> returns a 404 from nginx.
RUN printf 'server {\n\
  listen 80;\n\
  root /usr/share/nginx/html;\n\
  location / { try_files $uri $uri/ /index.html; }\n\
}\n' > /etc/nginx/conf.d/default.conf

EXPOSE 80
