FROM node:22-slim AS builder

WORKDIR /app

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ .
RUN npx vite build

FROM nginx:alpine

COPY --from=builder /app/dist /usr/share/nginx/html
COPY frontend/nginx.conf /etc/nginx/nginx.conf.template

ENV PORT=80
ENV BACKEND_URL=http://backend:8080

# Startup: read system DNS resolver, substitute all env vars, start nginx
CMD sh -c "\
  export NAMESERVER=\$(grep nameserver /etc/resolv.conf | head -1 | awk '{print \$2}') && \
  [ -z \"\$NAMESERVER\" ] && export NAMESERVER='8.8.8.8' ; \
  envsubst '\$PORT \$BACKEND_URL \$NAMESERVER' < /etc/nginx/nginx.conf.template > /etc/nginx/conf.d/default.conf && \
  nginx -g 'daemon off;'"
