# Docker Commands for Building and Managing the Container

These commands assume you are using a `docker-compose.yml` file in the current directory.

---

## 🛠️ Build the Image

Run this command in the project directory to build the service image defined in your Compose file:

```
docker compose build
```

---

## 🚀 Start the Container

Start your service in **detached mode** (runs in the background) with:

```
docker compose up -d
```

---

## 📜 View Logs

To follow logs from the running services, use:

```
docker compose logs -f
```

To follow logs for a specific service (e.g., `bot`):

```
docker compose logs -f bot
```

---

## 🛑 Stop and Remove the Deployment

Stop running containers and remove any networks, volumes, and images created by Compose:

```
docker compose down --volumes --rmi all --remove-orphans
```

---

## 🧹 Clean Up Docker Resources

Free up disk space by removing unused Docker data:

```
docker system prune -f --volumes
```

### Or remove each individually:

- Remove **stopped containers**:
  ```
  docker container prune -f
  ```

- Remove **unused images**:
  ```
  docker image prune -f
  ```

- Remove **unused networks**:
  ```
  docker network prune -f
  ```

- Remove **build cache**:
  ```
  docker builder prune -f
  ```

- Remove **unused volumes**:
  ```
  docker volume prune -f
  ```

---

> ✅ According to Docker documentation, `docker system prune` removes all stopped containers, unused networks, dangling images, and build cache. Adding the `--volumes` flag also prunes unused volumes.
