# 🐳 Docker Cheatsheet - Trading Bot

Guía rápida de comandos esenciales para gestionar el bot en producción.

---

## 📦 **1. Construcción y Arranque Inicial**

```bash
# Construir imagen y levantar el bot en segundo plano
docker-compose up -d --build
```

**Qué hace:**
- `-d`: Ejecuta en modo detached (segundo plano)
- `--build`: Fuerza reconstrucción de la imagen si hubo cambios en el código

**Primera ejecución:** Espera ~30-60 segundos para que el bot se conecte a TradingView.

---

## 📊 **2. Monitoreo de Logs en Tiempo Real**

```bash
# Ver logs en tiempo real (últimas 100 líneas)
docker logs -f --tail 100 trading-bot
```

**Atajos útiles:**
- `Ctrl+C`: Salir de los logs (el bot sigue corriendo)
- `--since 5m`: Ver logs de los últimos 5 minutos
- `--timestamps`: Mostrar timestamps en cada línea

---

## 🛑 **3. Detener el Bot (Graceful Shutdown)**

```bash
# Detención suave (permite que el bot cierre conexiones)
docker-compose stop
```

**Qué ocurre:**
- El bot recibe señal SIGTERM
- Cierra WebSockets y guarda datos antes de terminar
- Timeout: 10 segundos (configurable en `docker-compose.yml`)

**Alternativa rápida:** `docker stop trading-bot` (mismo efecto)

---

## 🔄 **4. Reiniciar Tras Cambios de Código**

```bash
# Reconstruir imagen y reiniciar el bot
docker-compose up -d --build

# O en dos pasos (más control):
docker-compose down
docker-compose up -d --build
```

**Importante:** Tus datos en `./data` NO se borran durante el reinicio.

---

## 🗑️ **5. Limpieza Completa (Eliminar Contenedores)**

```bash
# Detener y eliminar contenedores/redes
docker-compose down

# Limpieza profunda (incluye volúmenes anónimos)
docker-compose down -v

# Eliminar imagen del bot (liberar espacio)
docker rmi trading-bot-trading-bot
```

**⚠️ TRANQUILO:** Los archivos en `./data` (tu base de datos JSONL) están **a salvo** en el host. Solo se eliminan los contenedores/imágenes Docker.

---

## 🔍 **6. Comandos de Diagnóstico**

```bash
# Verificar estado del contenedor
docker ps

# Ver uso de recursos (CPU/RAM)
docker stats trading-bot

# Inspeccionar configuración del contenedor
docker inspect trading-bot

# Ejecutar shell dentro del contenedor (debug)
docker exec -it trading-bot /bin/bash
```

---

## 🚨 **7. Troubleshooting Rápido**

### **El bot no arranca:**
```bash
# Ver logs desde el inicio
docker logs trading-bot

# Verificar que .env existe y tiene las API keys
cat .env
```

### **Logs llenan el disco:**
```bash
# Ver tamaño actual de logs
docker inspect trading-bot --format='{{.LogPath}}' | xargs du -h

# Limpiar logs manualmente (úsalo con cuidado)
truncate -s 0 $(docker inspect --format='{{.LogPath}}' trading-bot)
```

### **Timezone incorrecta:**
```bash
# Verificar timezone dentro del contenedor
docker exec trading-bot date
# Debe mostrar: Argentina Time (ART / UTC-3)
```

---

## 📂 **Estructura de Archivos Críticos**

```
trading-bot/
├── Dockerfile              # Definición de la imagen
├── docker-compose.yml      # Orquestación del servicio
├── .env                    # Secrets (nunca commitear)
├── data/                   # 💾 Volumen persistente (JSONL database)
│   ├── trading_signals_dataset.jsonl
│   └── notifications/
└── logs/                   # 📝 Logs del bot (persistentes)
```

---

## 🎯 **Flujo de Trabajo Recomendado**

1. **Desarrollo Local:**  
   ```bash
   python main.py  # Probar sin Docker
   ```

2. **Deploy en Servidor:**  
   ```bash
   docker-compose up -d --build
   docker logs -f trading-bot  # Validar arranque
   ```

3. **Mantenimiento Diario:**  
   ```bash
   docker logs -f --tail 50 trading-bot  # Revisar actividad
   ```

4. **Actualizar Código:**  
   ```bash
   git pull
   docker-compose up -d --build
   ```

---

## 🔐 **Notas de Seguridad**

- **Nunca expongas puertos** en `docker-compose.yml` (el bot solo hace conexiones salientes)
- **Backup regular** de `./data/trading_signals_dataset.jsonl`
- **Rota el `.env`** si sospechas que las API keys fueron comprometidas

---

## 📞 **Comandos de Una Línea Útiles**

```bash
# Restart rápido
docker-compose restart

# Ver solo errores en logs
docker logs trading-bot 2>&1 | grep -i error

# Copiar archivo desde el contenedor al host
docker cp trading-bot:/app/data/trading_signals_dataset.jsonl ./backup.jsonl

# Ver variables de entorno del contenedor
docker exec trading-bot env
```

---

**✅ Listo.** Con estos comandos puedes gestionar el bot completamente. Para operación 24/7 en servidor, configura un cronjob que monitoree `docker ps` y te alerte si el bot se cae.
