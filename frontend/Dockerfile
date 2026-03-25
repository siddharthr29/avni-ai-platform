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

# Startup: read system DNS (handle IPv6), substitute env vars, start nginx
CMD sh -c "\
  NAMESERVER=\$(awk '/^nameserver/ {print \$2}' /etc/resolv.conf | head -1) && \
  case \"\$NAMESERVER\" in *:*) NAMESERVER=\"[\$NAMESERVER]\";; esac && \
  [ -z \"\$NAMESERVER\" ] && NAMESERVER='8.8.8.8' ; \
  export NAMESERVER && \
  envsubst '\$PORT \$BACKEND_URL \$NAMESERVER' < /etc/nginx/nginx.conf.template > /etc/nginx/conf.d/default.conf && \
  nginx -g 'daemon off;'"
