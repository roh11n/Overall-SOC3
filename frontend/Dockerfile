# ---------- Stage 1: build the React app ----------
FROM node:20-alpine AS build

WORKDIR /app/frontend
ENV NODE_OPTIONS=--max-old-space-size=2048

# Same-origin by default: Nginx proxies /api to the backend, so the app calls
# a relative "/api" path. Override at build time if you serve the API elsewhere.
ARG REACT_APP_BACKEND_URL=""
ENV REACT_APP_BACKEND_URL=$REACT_APP_BACKEND_URL

COPY package.json ./
RUN yarn install --network-timeout 600000

COPY . .
RUN yarn build

# ---------- Stage 2: serve static files via Nginx ----------
FROM nginx:alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/frontend/build /usr/share/nginx/html

EXPOSE 80
