FROM node:20-alpine AS builder

WORKDIR /app
COPY package.json .
RUN npm install

COPY . .
RUN npm run build

FROM node:20-alpine
WORKDIR /app
RUN npm install -g vite
COPY --from=builder /app /app
EXPOSE 5173
CMD ["npm", "run", "dev"]
