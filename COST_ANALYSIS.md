# AI Sales Assistant — Cost Guide (Plain Language)

**Who this is for:** Managers, finance, and operations—**no technical background required.**  
**What it explains:** What drives the monthly bill, in everyday words, plus **example dollar amounts** so you can plan. Those amounts are **illustrative only**; plug in your real prices from Google, OpenAI, and Deepgram before signing off on a budget.

---

## In one minute: what you are paying for

Your product does two main “metered” jobs that show up on cloud invoices:

1. **Listening (speech-to-text)** — While someone has the assistant **listening to live audio** (microphone on, session running), a vendor **charges by time**—like a taxi meter for **each minute of audio**, not “per word.”
2. **Writing the coaching lines (the AI reply)** — Each time the system produces **new suggested lines** for the **salesperson** (see “What is a rep?” below) to say, a **language model** (Google Gemini by default, or OpenAI if you switch) charges roughly like **paying per page of text** sent in and sent back. Bigger context and longer replies cost a bit more.

Everything else (searching your own knowledge base on your servers, reranking results) is mostly **your computers’ electricity and hardware**, not a “per word” API fee—unless you host those in a paid cloud database.

---

## AI tools we actually use — names, jobs, and how each is charged

**Yes: when this document says “speech” or “listening cost,” that is [Deepgram](https://deepgram.com/)** — the **speech-to-text** service wired into this product (`DEEPGRAM_API_KEY`). It listens to live audio and returns transcripts.

The **“text AI”** line is either **Google Gemini** (default) or **OpenAI** (if your team switches the setting), not both at once for the main answers.

| AI tool (vendor) | What it does in this product | How the bill is calculated | Example numbers for planning* |
|------------------|------------------------------|----------------------------|--------------------------------|
| **[Deepgram](https://deepgram.com/pricing)** | **Speech → text** for live calls (streaming). Uses models like **Nova**; multilingual is supported. | **Per minute of audio** sent while the session is streaming (exact $/min depends on your plan and model). | **~$0.009 / streamed minute** for a multilingual-style tier — **verify** on Deepgram’s pricing page. |
| **[Google Gemini](https://ai.google.dev/pricing)** (default) | **Writes** the on-screen coaching suggestions; handles some **short translation** for search when the salesperson uses **Hindi script** and your documents are English. | **Per token** (input text + output text). Larger prompts (more document snippets + conversation memory) use more input tokens. | Often quoted ballpark for Flash-class models: **~$0.30 / 1M input tokens**, **~$2.50 / 1M output tokens** — **must verify** in your Google AI / Cloud console. |
| **[OpenAI](https://openai.com/api/pricing)** (optional) | **Same job as Gemini** if you configure the product to use OpenAI instead of Google for answers. | **Per token** (input + output). | Common ballpark for **gpt-4o-mini**: **~$0.15 / 1M input**, **~$0.60 / 1M output** — **must verify** on OpenAI’s site. |
| **Same Gemini or OpenAI** *(if you add it)* | **Post-call** report: **customer interest + caller performance** (one run after the call). | **Per token** — see **Post-call analysis — one table**. | **~$3 – $5 / month** at **20 × 60** calls (Gemini-style example). |

\*These dollar figures are **examples for spreadsheets only**. Your real invoice is the source of truth.

### What is **not** a separate “per question” cloud AI fee here

| Piece | Why it’s not listed like Deepgram/Gemini |
|-------|--------------------------------------------|
| **Qdrant** | This is your **vector database** (search over your own text). You pay for **servers or Qdrant Cloud**, not “tokens” to Google for every search. |
| **Embeddings + reranking** | Runs **inside your app** using open models — **no OpenAI/Gemini charge per embedding** in this codebase; cost shows up as **heavier server memory/CPU**. |

---

## Simple glossary (words we use in planning)

### What is a “rep”?

**“Rep”** is short for **sales representative**—in plain words, it is **the person on your team who is talking to the customer** (on the phone, video call, or in person) **and has the AI assistant turned on** to get suggested lines.

- At a bank, this might be a **relationship manager (RM)**.  
- At a developer, this might be a **sales advisor** or **agent**.  
- In this document, **“rep,” “salesperson,” and “person using the assistant”** mean the **same role**.

---

| If you see this… | It really means… |
|------------------|------------------|
| **Listening time / “mic on” time** | The assistant is **actively receiving live audio** for that session. This is what the speech vendor bills **by the minute**, even during silence. |
| **One suggested reply** (we used to say “coaching turn”) | The salesperson finishes a **phrase or sentence**; the system turns it into text, looks up facts, and shows **one new block of suggested lines**. Each of those cycles is **one billable “write”** from the text AI (plus the listening that already happened). |
| **Active salesperson / “someone using it live”** | Someone who **starts a session** and keeps the live assistant running—not someone who only opened a static page once. |
| **One call / one session** | From **Start** to **Stop** on the assistant for that conversation (could be 5 minutes or 45 minutes). |
| **Per question** | In this product, think **“each time the salesperson’s speech triggers a new on-screen suggestion”**—not strictly “one customer question.” More talking (short back-and-forth) can mean **more suggestions** than “big questions.” |
| **Total AI tools cost** | What you pay **Deepgram** (speech) **+** **Google** (Gemini) **or** **OpenAI** (if you use that instead)—the **paid cloud AI vendors** for listening and writing. *It does not include your own office computers or self-hosted Qdrant unless you count those separately.* |
| **“Speech API only” in a table** | Means **Deepgram only** for that column—the part of the bill for **turning audio into text**, priced by **time**, not by “number of suggestions.” |
| **Tokens** (optional) | How AI vendors **measure text size**—like counting pieces of words. You don’t need to manage tokens; just know **longer prompts and longer answers cost a bit more**. |

---

## Is this multilingual?

**Yes, the live assistant is built for multilingual use**, with a few plain-English caveats:

| Area | What happens |
|------|----------------|
| **Speech recognition** | By default the service uses a **multilingual** speech model so **English and many other languages** can be transcribed in the same session (see `DEEPGRAM_LANGUAGE=multi` in settings). |
| **Suggested lines the salesperson says** | The AI is instructed to **match the salesperson’s language** when it makes sense—for example **English**, **Hindi (Devanagari)**, or **mixed** English/Hindi in the same call. |
| **Your uploaded knowledge (facts, brochures)** | Search is tuned for **English documents**. If the salesperson speaks **Hindi**, the system can **translate that line internally** so search still finds the right English pages—then the **answer can still come back in Hindi** for them. So: **multilingual conversation, English-first knowledge base** unless you add more languages to the documents. |

**Cost note:** Hindi (and similar scripts) can sometimes add **one small extra AI call** for that internal “translate for search” step. Repeating the same phrase costs less because of caching.

---

## The table you asked for: per user, per call, per minute, per “question”

Below, **“AI suggestion”** = one time the system writes a new coaching block for the salesperson (see glossary).  
**“Total AI tools cost”** = **Deepgram** + **Gemini or OpenAI** (the paid cloud vendors for **listening** and **writing**). It does **not** include your own laptops or self-hosted Qdrant unless you count those separately.

**Example rates used below (verify on your contracts):**

- **Deepgram:** **~$0.009 per streamed minute** (example; multilingual tiers may differ).  
- **Gemini** (example): **~$0.002 – $0.006 per suggestion** depending on prompt size; OpenAI **gpt-4o-mini** is often **cheaper per token** but you still multiply by tokens used.

| How you want to think about it | What gets charged | **Deepgram** — speech only (example) | **Gemini or OpenAI** — writing suggestions (example) | **Total AI tools cost** (example) | Notes for non-tech readers |
|--------------------------------|-------------------|--------------------------------------|--------------------------------------------------------|-------------------------------------|------------------------------|
| **Per 1 minute** the microphone is live and streaming | Deepgram every minute; Gemini/OpenAI only when a new suggestion is generated | **~$0.009 / min** | **$0** if no suggestion that minute; **~$0.002 – $0.006** if **one** suggestion fires | **~$0.009 – $0.015 / min** | **Deepgram** = steady meter; **Google or OpenAI** = bursts when a phrase finishes. |
| **Per AI suggestion** (each new block of coaching text) | Gemini or OpenAI (Deepgram is billed by time, not “per suggestion”) | **—** | **~$0.002 – $0.006 each** | **~$0.002 – $0.006** (text only on this row) | One billable **write** from Google or OpenAI for that coaching block. |
| **Per “question”** (one line from the salesperson that triggers help) | Usually **one** suggestion | **—** | **~$0.002 – $0.006** | **~$0.002 – $0.006** (+ Deepgram for the **minute** you’re in) | More short lines per minute → more **Gemini/OpenAI** charges. |
| **One short call (example: 10 minutes, mic on the whole time)** | 10 min Deepgram + e.g. **8–20** suggestions | **~$0.09** | **~$0.02 – $0.12** | **~$0.11 – $0.22** | **Total** = **Deepgram + Gemini/OpenAI** for that call (example). |
| **One salesperson for a month (example: 20 hours “mic on”)** | **1,200 min** + suggestions | **~$11** | **~$1** (12 sugg./hour) **or ~$2–4** (30/hour) | **~$12** or **~$13–15** | **Per salesperson** = one person’s **Deepgram + text AI** (example). |
| **Whole company (many people)** | All minutes + all suggestions | Sum Deepgram | Sum Gemini/OpenAI | **Add both vendors** | Total paid AI tools = **sum across the team**. |

**How to use this table in a meeting:** **Total AI tools cost** ≈ **(minutes × Deepgram $/min) + (suggestions × average $/suggestion for Gemini or OpenAI)**.

---

## Why the bill can feel “high” or “spiky” (still plain English)

- **Long calls with the assistant always listening** add up **minute by minute** on speech billing—even if the customer is quiet.
- **Every new suggestion** sends **instructions + recent conversation memory + snippets from your documents** to the AI. That’s good for quality, but it means **each suggestion is not “one tiny sentence” of cost**—it’s a **full package of context** each time.
- After the **first** suggestion in a session, the system **remembers the last topic** on purpose, so it **does not reuse** the cheap “same question as yesterday” shortcut as often. **Quality goes up; repeated-stuff discount goes down.**

---

## Executive summary (for leadership)

| Topic | Plain summary |
|--------|----------------|
| **Main costs** | **(1)** Time with **live listening** on. **(2)** Number of **AI-written suggestions**. |
| **Total AI tools cost** | **Deepgram** (speech) **+** **Google Gemini** *or* **OpenAI** (writing)—add those vendor lines from your invoices. |
| **Server / infrastructure cost** | **Separate bill** (cloud VMs, Qdrant, Redis, disk)—see **Server and infrastructure costs** table below. Not the same invoice as Deepgram or Gemini. |
| **What usually costs the most** | Among **AI vendors**, **listening minutes** (Deepgram) are often the largest line. **Servers** can still be **material** for small teams and **grow** with traffic and redundancy. |
| **What makes AI cost creep** | **More suggestions per hour** and **longer internal “packages” of text** per suggestion (bigger memory and documents in the prompt). |
| **Multilingual** | **Yes** for speech and coaching lines; **knowledge search** is **English-document–first**, with **translation for search** when needed for Hindi script. |
| **Buffer for budgeting** | Add **20–40%** on top of spreadsheet estimates for retries, reconnects, and price changes. |
| **Future: post-call analysis** | One table: **~$3 – $5/mo** for **20 users × 60 calls** on Gemini-style rates (see **Post-call analysis — one table**). |

---

## Optional: what runs where (still simple)

| Piece | Paid like… | Simple note |
|-------|------------|-------------|
| **Speech → text** | Per **minute** of live audio | **Deepgram** while the session streams sound. |
| **Writing suggestions** | Per **amount of text** in and out | **Google Gemini** (default) or **OpenAI** if configured. |
| **Small translation for search** (sometimes) | Same as a **tiny** extra Gemini write | Only when the spoken line is in certain scripts (e.g. Hindi letters) and your documents are English. |
| **“Brain” search on your facts** | Your **server / database** bill | **Qdrant** + your app server—not priced “per token” like Gemini/OpenAI. |

---

## Example monthly picture (two styles of team)

**Assumptions (examples only):** **20 salespeople**, each **4 hours per working day** with the assistant **listening**, **22 workdays**; **Deepgram ~$0.009/min**; **Gemini/OpenAI ~$0.004/suggestion** average.

| Team style | Listening hours (whole team) | Suggestions (example) | **Deepgram** only (example) | **Gemini or OpenAI** only (example) | **Total AI tools cost** (example) |
|------------|-------------------------------|------------------------|-----------------------------|---------------------------------------|-------------------------------------|
| **Calmer calls** — fewer new suggestions per hour | 20 people × 4 h × 22 days = **1,760 person-hours** with the mic on → **105,600 minutes** | **10 suggestions per person-hour** → 1,760 × 10 = **17,600** | **~$950** | **~$70** | **~$1,020** |
| **Busier talk** — more back-and-forth | Same **105,600 minutes** | **30 suggestions per person-hour** → 1,760 × 30 = **52,800** | **~$950** | **~$211** | **~$1,160** |

*(How to read it: **1,760 person-hours** means “one hour with the assistant on” counted across all salespeople (e.g. 20 people × 88 hours each). Minutes = 1,760 × 60 = 105,600. **Total AI tools cost** = **Deepgram** (105,600 × ~$0.009) **+** **Gemini or OpenAI** (suggestion count × ~$0.004).)*

---

## Server and infrastructure costs (separate from Deepgram / Gemini / OpenAI)

**These are your computers in the cloud (or your data center)**—renting CPU, memory, disk, and sometimes managed databases. They show up on **AWS, Azure, Google Cloud, DigitalOcean**, etc., **not** on the Deepgram or Google AI invoice.

The backend is **memory-heavy** because it loads **embedding** and **reranking** models on the server (see `USAGE.md`—often **about 2–4 GB RAM** as a starting conversation with IT; production may use **more** for headroom).

### Server cost table (planning examples only*)

| What you’re paying for | Plain English | Typical starter shape (non‑technical) | Example monthly cost (very rough)** |
|------------------------|---------------|-------------------------------------|--------------------------------------|
| **Backend / API server** | The “brain” that connects to Deepgram & Gemini, searches your knowledge, runs embeddings & rerank | A **small–medium cloud server** with enough **RAM** (often **4–8 GB** or more for comfort) | **~$40 – $200 / month** for one modest VM (region & provider change this a lot) |
| **Qdrant (search database)** | Stores your property / FAQ chunks for fast lookup | **Same server** as the API in simple setups **or** a **second small service** if split | **~$0** if bundled on one VM **or** **~$25 – $150+ / month** extra if isolated or using **Qdrant Cloud** |
| **Redis (optional)** | Short‑term session memory and optional answer cache | Tiny add‑on **or** managed “cache” from your cloud | **~$0** if on same VM **or** **~$15 – $80 / month** if you buy a managed cache |
| **Load balancer / HTTPS** | Routes traffic securely if you have many users or high availability | Often **one small managed service** | **~$0 – $50 / month** (many small teams start at the low end) |
| **Disk & backups** | Saves logs, model cache, database files | Grows slowly | **~$5 – $40 / month** at small scale |
| **Web dashboard (UI)** | The page salespeople open in the browser | Often **served from the same API host** in small setups **or** cheap **static hosting** | **~$0** (bundled) **or** **~$0 – $25 / month** for a simple hosted frontend |
| **Office / dev machines** | Laptops for building and testing | Not “per call” | **Your HR / capex budget** — not counted below |

\* **Not a quote.** Your IT partner or cloud bill is authoritative.  
\** **US/EU–style public cloud, on‑demand-ish pricing, single region, low traffic.** Reserved instances or annual commits can be **cheaper**; enterprise support adds **cost**.

### Example: “all on one server” vs “split services”

| Setup style | Who it suits | How to think about server $ |
|-------------|--------------|-----------------------------|
| **One cloud VM** running API + Qdrant + Redis (like a tight **Docker Compose** setup) | Pilots, small teams | Often **one** line item: **~$60 – $250 / month** total server-side (example band). |
| **Split** (API on autoscaled VMs, managed Qdrant, managed Redis) | More users, stricter uptime | **Add** the rows above instead of $0 bundled—**total server + DB** might land **~$200 – $800+ / month** before traffic spikes. |

### Grand total (for management)

**Rough picture:**  
**Monthly bill ≈ (Deepgram + Gemini/OpenAI) + (servers + databases above) + (your people’s time).**  
Only the **first two columns** in the AI examples (~$1,020–$1,160) were **AI vendors**; **servers are extra** unless you already include them in another budget line.

If you add **post-call analysis** (customer interest + caller performance in **one** report after the call), budget a **small extra** Gemini/OpenAI line—usually **far below** live coaching if you run it **once per completed call** with a **reasonable-length** transcript.

---

## Post-call analysis — one table (tokens + total money)

**What it is:** After a call ends, **one** AI request returns **customer interest + caller performance** together (scores + short text). **Not shipped yet** — planning numbers only.  
**Rates used for “Total money”:** **$0.30 / 1M input tokens** + **$2.50 / 1M output tokens** (Gemini Flash–style; **replace with your invoice**).

| | **Per single post-call analysis** | **Monthly total — this feature only** |
|--|-----------------------------------|----------------------------------------|
| **Assumption** | 1 completed call | **20** salespeople × **60** completed calls each = **1,200** analyses / month |
| **# of AI calls** | **1** | **1,200** |
| **Input tokens** | **~4,000 – 6,500** (instructions + summary / transcript excerpt) | **~4.8M – 7.8M** (= 1,200 × the per-call input range) |
| **Output tokens** | **~600 – 900** (scores + short narrative) | **~0.72M – 1.08M** (= 1,200 × the per-call output range) |
| **Total tokens (input + output)** | **~5,000 – 7,500** | **~5.5M – 8.9M** (sum of the two rows above) |
| **≈ Total money (Gemini-style)** | **~$0.0027 – $0.0042** each analysis | **~$3 – $5 / month** for this add-on only |

### Is **~$3 – $5 / month** really all we pay for 20 users’ post-call analysis?

**For this feature only — yes, that order of magnitude is intentional** with the assumptions in the table:

- Each post-call run costs only **about a third of a cent to half a cent** (~**$0.003 – $0.004** per analysis). **1,200** of those per month is **~$3.6 – $5** in total.
- **Millions of tokens** can still be only **a few dollars** because the **price per million tokens** is small (e.g. **$0.30 per million input** tokens).

**This is not your whole product bill.** The **~$3 – $5** line is **only** the extra text-AI cost for **post-call** summaries. It **does not** include **Deepgram** (live speech), **live coaching** suggestions during the call, or **servers** — those are separate and usually **much larger** than post-call alone.

**When post-call cost goes up:** more than **60** calls per person, more than **20** users, **two** AI reports instead of one, **full long transcripts** every time, or a **pricier** model — then multiply or redo the formula.

**How the monthly $ was derived:**  
`(input_tokens / 1,000,000 × $0.30) + (output_tokens / 1,000,000 × $2.50)` **per analysis**, then × **1,200**. Low end uses **4,000 + 600** tokens; high end uses **6,500 + 900**. Vendors bill input and output on separate meters—this table already folds both into **one total $**.

**If your volume changes:** `monthly $ ≈ (# analyses) × (~$0.0027 – $0.0042)` for this compact design, or recalc with your real token counts. **Very long full transcripts** push input tokens up → **multiply $ up** in the same way.

---

## Cost ideas that operations can actually use

1. **Shorter “listening on” time** where safe (e.g. stop assistant between calls) → **directly lowers** the biggest meter.  
2. **Fewer unnecessary suggestions** (product settings, training salespeople to avoid ultra-short noise) → lowers the **second** meter.  
3. **Get real numbers from invoices** once a month: **Deepgram** (minutes/hours), **Google and/or OpenAI** (token or $ spend), and **cloud/server** bills (VMs, databases)—then divide by **number of people using the assistant** to get **your** true cost **per salesperson**.

---

## Finance checklist (simple)

- [ ] **Deepgram:** total **streamed audio minutes** (or hours) last month.  
- [ ] **Google (Gemini):** total spend and/or tokens last month (if you use default).  
- [ ] **OpenAI:** total spend last month (only if you switched the product to OpenAI).  
- [ ] **Number of active salespeople** (or seats) using the assistant.  
- [ ] **Cloud / server spend:** VMs, **Qdrant**, **Redis**, disk, load balancer (from your cloud console).  
- [ ] **Cost per salesperson** = (Deepgram + Gemini/OpenAI **+ servers/databases**) ÷ headcount.  
- [ ] If you ship **post-call scoring:** track **extra LLM calls** and **tokens per conversation** (vendor dashboards).  
- [ ] Revisit **every quarter** when prices or usage patterns change.

---

## Total investment — everything that makes the service live

Use this as a **checklist budget**: **recurring** (every month) vs **one-time / first year** (setup). Dollar bands are **examples**—replace with quotes from vendors and your IT partner.

### Recurring monthly (run the live product)

| # | Service / bucket | What it is for | Paid to (typical) | Example $ / month* |
|---|------------------|----------------|-------------------|-------------------|
| 1 | **Speech (listening)** | Live audio → text | **Deepgram** | From your usage: e.g. **~$950** for the heavy **20‑person** example earlier, or scale down with fewer minutes. |
| 2 | **Text AI — live coaching** | Suggested lines during the call | **Google (Gemini)** or **OpenAI** | From your usage: e.g. **~$70 – $210+** in the same **20‑person** examples (chatter‑dependent). |
| 3 | **Text AI — post-call insights** (optional) | One summary after each call | **Same** Gemini/OpenAI account | **~$3 – $5 / month** for **20 × 60** analyses (see **Post-call analysis — one table**). Scale with `# analyses × ~$0.0027–$0.0042`. |
| 4 | **Cloud servers** | API, embeddings, rerank | **AWS / Azure / GCP / etc.** | **~$60 – $250** (one modest stack) **or** **~$200 – $800+** split/high availability. |
| 5 | **Databases & cache** | Qdrant + optional Redis | Same cloud **or** managed DB vendors | Often **bundled** in row 4; else **~$25 – $150+** add‑on. |
| 6 | **Networking & security** | Load balancer, TLS, DNS | Cloud provider | **~$0 – $50** small scale. |
| 7 | **Website / dashboard hosting** | Where users open the UI | Cloud static hosting **or** bundled | **~$0 – $25**. |
| 8 | **Monitoring & logs** (recommended) | Uptime, errors | Datadog / Grafana Cloud / cloud native | **~$0 – $100+** depending on ambition. |
| | **Example subtotal (monthly)** | Rows 1–2 + 4 (no post‑call feature) | | **~$1,080 – $1,410** band (ties to earlier **AI ~$1,020–$1,160** + **~$60–$250** servers) |
| | **+ Post‑call scoring (row 3)** | Add when you launch it | | **+ your forecast** from conversations × tokens |

\*Examples only. **Row 3** is **zero** until you release that feature.

### One-time or first-year (get to “live”)

| # | Item | What it is for | Example cost* |
|---|------|----------------|---------------|
| O1 | **Engineering & QA** | Build, test, harden | **Internal time** or vendor **SOW** (varies widely). |
| O2 | **Knowledge setup** | Upload/clean property & FAQ content into Qdrant | Mostly **people time**; small cloud cost for ingest. |
| O3 | **Domains, certs, email** | Brand + trust | **~$15 – $100 / year** + optional business email. |
| O4 | **Security / privacy review** | Checklist for production | **$0** (internal) **or** consultant **$2k – $20k+** if required. |
| O5 | **Contingency** | Unknowns, retries, price moves | **15 – 30%** on top of recurring Year‑1 sum. |

\*Not a quote.

### How to read the “total” row

**Total monthly run-cost (illustrative)** ≈ **(1) + (2) + (3 if enabled) + (4) + (5–8)**.  
**Total to go live first time** ≈ **one-time table** + **first month’s recurring** + **training**.

---

## Technical references (for IT only)

| File | What it contains |
|------|------------------|
| `app/core/config.py` | Models, timeouts, multilingual defaults, cache settings. |
| `USAGE.md` | How to run the stack and rough server memory hints. |
| `app/modules/rag/prompts.py` | How answers choose **English / Hindi / mixed** tone. |
| `app/services/embedding_service.py` | Multilingual embeddings — **Hindi script** searches the English KB directly (no translation call). |
