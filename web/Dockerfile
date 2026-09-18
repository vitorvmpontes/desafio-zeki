# Etapa 1: build da SPA (Vite injeta VITE_API_URL em tempo de BUILD, nao de
# execucao -- e por isso que e um ARG aqui, nao uma variavel de ambiente do
# container final).
FROM node:22-slim AS build
WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

ARG VITE_API_URL=http://localhost:8000
ENV VITE_API_URL=$VITE_API_URL
RUN npm run build

# Etapa 2: serve os arquivos estaticos com nginx
FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
