# Node 24 LTS - same major as local dev (the package-lock.json is written by its npm 11);
# vitest/vite require Node >= 22. Only the build stage uses Node, the image serves via nginx.
FROM node:24-alpine AS build
WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# /api - w kontenerze frontend rozmawia z backendem przez nginx (patrz nginx.conf),
# wiec nie trzeba wiedziec z jakiego adresu/hosta appka bedzie dostepna.
ARG VITE_API_URL=/api
ENV VITE_API_URL=$VITE_API_URL
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
