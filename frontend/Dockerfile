FROM node:22-alpine

WORKDIR /app

# Instalar dependencias primero (capa cacheada)
COPY package*.json ./
RUN npm ci

# El código fuente se monta como volumen en dev,
# así que no se copia acá — sólo se necesita para la imagen base.
COPY . .

EXPOSE 5173

# --host 0.0.0.0 es necesario para que Vite sea accesible fuera del contenedor
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
