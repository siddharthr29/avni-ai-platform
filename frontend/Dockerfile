FROM node:22-slim AS builder

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

FROM nginx:alpine

COPY nginx.conf /etc/nginx/templates/default.conf.template
COPY --from=builder /app/dist /usr/share/nginx/html

ENV PORT=80
ENV BACKEND_URL=http://backend:8080

EXPOSE ${PORT}

CMD ["nginx", "-g", "daemon off;"]
