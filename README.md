Absolutely! Here's the **complete, step-by-step command list** for each bot (A and B) — including:

* Going to folder
* Creating + activating venv
* Installing requirements
* Starting bot in background
* Viewing logs
* Stopping bot safely

---

## 🅰️ Bot A (in `/home/ubuntu/A_txt-v`)

### ✅ **1. Go to folder and set up venv**

```bash
cd /home/ubuntu/A_txt-v
python3 -m venv venv
source venv/bin/activate
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

### 1. Find process ID:

```bash
ps aux | grep main.py
```

Sample output:

```
ubuntu   313424  0.5  1.2  123456  65432 pts/0    S    13:55   0:00 python3 main.py
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
