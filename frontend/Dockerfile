FROM node:22-slim AS builder

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npx vite build

FROM nginx:alpine

# Copy built assets
COPY --from=builder /app/dist /usr/share/nginx/html

# Copy nginx config as template
COPY nginx.conf /etc/nginx/nginx.conf.template

# Default env vars
ENV PORT=80
ENV BACKEND_URL=http://backend:8080

# Startup: substitute only PORT and BACKEND_URL, then start nginx
CMD sh -c "envsubst '\$PORT \$BACKEND_URL' < /etc/nginx/nginx.conf.template > /etc/nginx/conf.d/default.conf && nginx -g 'daemon off;'"
