# 🚀 Magicpin AI Bot — Merchant Growth Engine

An AI-powered backend system designed to **drive merchant engagement, improve CTR, and trigger real actions** using contextual signals like performance metrics, triggers, and category insights.

This bot is not a chatbot — it acts as a **conversion-focused growth assistant** for merchants.

---

## 🎯 Objective

* Detect opportunities from merchant + trigger data
* Generate **high-impact, personalized messages**
* Push merchants toward **clear business actions** (offers, posts, engagement)

---

## 🧠 Core Capabilities

* 📊 **Performance-Aware Messaging**
  Uses CTR and peer benchmarks to highlight missed opportunities

* 🎯 **Trigger-Based Actions**
  Responds to events like:

  * Performance drop
  * Research insights
  * Festival spikes
  * Customer recall

* 🏙️ **Contextual Personalization**
  Tailors messages using:

  * Merchant name
  * City
  * Category behavior

* ⚡ **Action-Oriented Responses**
  Avoids passive suggestions → directly moves toward execution

---

## 🔌 API Endpoints

### Health Check

```
GET /v1/healthz
```

### Metadata

```
GET /v1/metadata
```

### Context Ingestion

```
POST /v1/context
```

Receives category, merchant, and trigger data.

### Trigger Processing

```
POST /v1/tick
```

Generates actions based on incoming triggers.

### Conversation Handling

```
POST /v1/reply
```

Handles merchant replies (intent detection, auto-reply filtering, etc.)

---

## 💬 Sample Output

```
Clinic XYZ, aapka CTR 1.8% hai vs 3.2% category avg — iska matlab aap ~20+ potential patients miss kar rahe ho.

City me low-entry offers (₹299 range) consistently higher clicks laate hain.

Main abhi ek optimized post + offer draft kar rahi hoon — approve kar dena, we can push this live today 👍
```

---

## ⚙️ Tech Stack

* FastAPI
* Python
* Rule-based + data-driven message generation

---

## 🧩 Architecture Overview

1. Context pushed via `/v1/context`
2. Triggers processed in `/v1/tick`
3. Message generated using `compose()` logic
4. Replies handled via `/v1/reply`

---

## 🚀 Deployment

Live URL:

```
https://your-render-url.onrender.com
```

---

## 🛠️ Local Setup

```bash
pip install -r requirements.txt
python -m uvicorn main:app --reload
```

---

## 🔐 Environment Variables

```
OPENROUTER_API_KEY=your_api_key
```

---

## 📈 Design Philosophy

* Specific > Generic
* Action > Suggestion
* Context > Template

This system is built to behave like a **growth partner**, not a passive assistant.

---

## 👤 Author

Trisita Ghosh
B.Tech CSE (AI & ML)
Backend / Data Engineering / AI Systems

---
