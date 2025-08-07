## 🅰️ Bot A (in `/home/ubuntu/A_txt-v`)

### ✅ **1. Go to folder and set up venv**

```bash
cd /home/ubuntu/A_txt-v
python3 -m venv venv
source venv/bin/activate
sudo apt update && sudo apt upgrade
sudo apt install ffmpeg -y
pip install --upgrade pip
pip install -r requirements.txt
```

### 🚀 **2. Start Bot A in Background**

```bash
nohup python3 main.py > output.log 2>&1 &
```

---

## 🅱️ Bot B (in `/home/ubuntu/B_txt-v`)

### ✅ **1. Go to folder and set up venv**

```bash
cd /home/ubuntu/B_txt-v
python3 -m venv venv
source venv/bin/activate
sudo apt update && sudo apt upgrade
sudo apt install ffmpeg -y
pip install --upgrade pip
pip install -r requirements.txt
```

### 🚀 **2. Start Bot B in Background**

```bash
nohup python3 main.py > output.log 2>&1 &
```

---

## 🔍 **Check Logs (for either bot)**

```bash
tail -f output.log
```

> Use `Ctrl + C` to stop viewing logs (does **not** stop the bot).

---

## 🛑 **Stop Bot (A or B)**

---

### 🧠 Summary: How to identify your bots

If you run multiple bots with the same filename (`main.py`), use this process:

1. Get all matching processes:

   ```bash
   ps aux | grep main.py
   ```

2. For each PID, check its working directory:

   ```bash
   ls -l /proc/<PID>/cwd
   ```

That will tell you exactly which bot is running from which folder.

---

### ✅ Optional: One-liner script to see all running bots

You can use this command to list all running `main.py` bots with their folder:

```bash
for pid in $(pgrep -f main.py); do echo -n "PID $pid → "; readlink /proc/$pid/cwd; done
```

**Example output:**

```
PID 304845 → /app
PID 306681 → /home/ubuntu/A_txt-v
```

### 2. Kill it by PID:

```bash
kill <PID>
```

Example:

```bash
kill 313424
```

---

Let me know if you want to:

* Auto-start these on reboot
* Use a `.sh` script for starting both at once
* Or manage them via `systemctl` again but better handled

✅ You're fully set up for isolated, background bots without Docker.
