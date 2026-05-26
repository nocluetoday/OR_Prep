# Dev image for the Vite + React frontend.
# Code is mounted at runtime via compose; node_modules lives in a named volume.
# Multi-stage production image (Node build → nginx static serve) lands in chunk 11.

FROM node:24-alpine

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "5173"]
