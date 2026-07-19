# AI Calling Assistant – Full Production Guide
Author: Senior AI Architecture Blueprint  
Goal: Build a production-grade AI calling assistant similar in capability approach to Parakeet AI

---

# 1. Introduction

This document describes the **complete architecture, development plan, modules, code structure, data structure, real-time pipeline, and deployment strategy** for building a production-grade AI calling assistant.

The system listens to sales calls in real time and provides intelligent suggestions to the sales agent.

Example:

Client asks:
"What is price of 3BHK?"

AI suggests:
"3BHK starts from ₹1.8Cr depending on floor and configuration. It offers premium amenities and strong resale potential."

---

# 2. Core Objectives

Build an AI assistant that:

• listens to conversation  
• understands intent  
• retrieves relevant business knowledge  
• suggests best response instantly  
• improves sales conversion  

---

# 3. Core Technology Stack

Backend API
FastAPI

LLM
Gemini 1.5 Flash

Vector Database
Qdrant

Embeddings
Sentence Transformers

Realtime Speech-to-Text
Deepgram Streaming API

Cache
Redis

Deployment
Docker

Future scaling
Kubernetes

---

# 4. High Level Architecture

Audio Stream
↓
Streaming Gateway
↓
Speech-to-Text Engine
↓
Conversation Understanding
↓
RAG Retrieval
↓
LLM Response Generation
↓
Agent UI Suggestions

---

# 5. Full System Architecture

Calling Platform (Twilio / Meet / internal platform)
            ↓
WebSocket Streaming Gateway
            ↓
Deepgram Speech-to-Text
            ↓
Conversation Context Manager (Redis)
            ↓
RAG Retrieval Engine (Qdrant)
            ↓
LLM Engine (Gemini)
            ↓
Suggestion Engine
            ↓
Agent Dashboard UI

---

# 6. Production Folder Structure

app/

core/
    config.py
    logging.py

api/
    v1/
        query.py
    websocket/

services/
    embedding_service.py
    gemini_service.py
    qdrant_service.py
    deepgram_service.py
    redis_service.py

modules/

    rag/
        retriever.py
        reranker.py
        pipeline.py

    conversation/
        intent_detector.py
        entity_extractor.py
        state_manager.py

    coaching/
        suggestion_engine.py

scripts/
    ingest_data.py

data/
    raymond_realty_full.json

main.py

---

# 7. Data Architecture

Knowledge is stored in JSON and indexed in Qdrant.

Example:

{
"text": "3BHK starts from ₹1.8Cr",
"metadata": {
"category": "pricing",
"intent": "price_query",
"project": "raymond_realty"
}
}

---

# 8. Knowledge Categories

pricing
location
amenities
configuration
sales pitch
objection handling
finance
trust signals
investment logic

---

# 9. RAG Architecture

Retrieval Augmented Generation combines:

vector search
+ LLM reasoning

Flow:

user query
↓
embedding vector
↓
similarity search
↓
context retrieval
↓
LLM generates answer

---

# 10. Config Module

central config file

stores:

API keys
model configs
performance configs

Example:

class Settings:

    GEMINI_API_KEY = ""
    QDRANT_URL = "http://localhost:6333"

    EMBEDDING_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"

    TOP_K = 5

    MAX_TOKENS = 300

---

# 11. Logging Module

production logs track:

latency
errors
requests
performance

Example:

2026-03-22 19:20:33
RAG latency: 0.08 sec
LLM latency: 0.71 sec

---

# 12. Embedding Service

converts text into vectors.

model:

paraphrase-multilingual-MiniLM-L12-v2 (multilingual — Hindi/Marathi/English queries share one vector space, so no translation step is needed before search)

Example:

"What is price?"

→ vector representation

---

# 13. Vector Database (Qdrant)

stores embeddings

enables similarity search.

query example:

"price of 3bhk"

returns:

most relevant knowledge entries.

---

# 14. LLM Service

Gemini generates final response.

prompt structure:

role:
AI assistant helping sales agent

goal:
short helpful suggestions

tone:
professional
friendly

---

# 15. Conversation Intelligence Layer

extracts:

intent
entities
conversation state

Example:

user says:
"budget is 2 crore"

system stores:

budget=2cr

used in future responses.

---

# 16. Suggestion Engine

suggests:

best answer
upsell opportunity
objection handling line
follow-up question

Example:

"Highlight resale value benefits."

---

# 17. Real-Time Processing Pipeline

Step 1
audio chunk received

Step 2
speech converted to text

Step 3
intent detected

Step 4
vector search performed

Step 5
LLM generates answer

Step 6
suggestion displayed

target latency:

1-2 seconds

---

# 18. Performance Optimization

parallel processing:

run simultaneously:

intent detection
vector search
entity extraction

caching:

store common queries in Redis

partial transcript processing:

process live chunks instead of waiting full sentence.

embedding reuse:

avoid recomputing vectors.

---

# 19. Scaling Strategy

horizontal scaling

multiple API servers.

microservices split:

STT service
RAG service
LLM service

Qdrant cluster scaling.

---

# 20. Security

encrypt:

API keys
call transcripts

mask:

phone numbers
emails
PII data

---

# 21. Docker Architecture

services:

backend
qdrant
redis

docker compose runs entire stack.

---

# 22. Development Phases

Phase 1
RAG engine

Phase 2
Realtime speech integration

Phase 3
Agent UI dashboard

Phase 4
analytics insights

Phase 5
CRM integration

---

# 23. Production Checklist

response latency < 2 sec

stable websocket

accurate answers

no hallucinated pricing

fallback responses exist

retry logic exists

logging enabled

---

# 24. Future Enhancements

conversation scoring

sales coaching insights

emotion detection

lead qualification detection

auto CRM entry

call summary generation

tone analysis

multilingual support

---

# 25. End-to-End Flow Summary

audio
↓
transcript
↓
intent detection
↓
vector search
↓
LLM reasoning
↓
suggestion displayed

---

# 26. Final Result

enterprise-grade AI calling assistant

core strengths:

real-time intelligence
sales optimization
knowledge retrieval
conversation understanding

---

END OF DOCUMENT