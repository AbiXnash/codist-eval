# Running MiroFish on Codist

MiroFish ([666ghj/MiroFish](https://github.com/666ghj/MiroFish), AGPL-3.0) builds a world of AI personas from seed
documents and simulates how they react. It is cloned at `~/dev/stolen-with-pride/MiroFish`.

## 1. Install (once)

Installing runs third-party install scripts, so run it yourself:

```bash
cd ~/dev/stolen-with-pride/MiroFish && npm run setup && cd backend && UV_PYTHON=python3.11 uv sync
```

Needs Node 18+ (26 is installed), Python 3.11 (installed) and uv (installed).

## 2. Configure `~/dev/stolen-with-pride/MiroFish/.env`

```bash
cp ~/dev/stolen-with-pride/MiroFish/.env.example ~/dev/stolen-with-pride/MiroFish/.env
```

**Model, choose one:**

- *Local, private, slower.* Ollama already answers OpenAI-style requests. Use `qwen3-nothink`, made by
  `./make-qwen3-nothink.sh` (already made on this Mac): qwen3:8b with its thinking switched off, so it answers
  directly in JSON. Plain `qwen3:8b` can spend its whole reply thinking and return nothing, which breaks MiroFish.
  ```
  LLM_API_KEY=ollama
  LLM_BASE_URL=http://localhost:11434/v1
  LLM_MODEL_NAME=qwen3-nothink
  ```
  `qwen2.5-coder:14b` also works but is tuned for code, so its personas are flatter. A simulation is many calls, so
  on a 16 GB Mac keep rounds under 20 and agents few.
- *Cloud, fast.* Any OpenAI-compatible service (the MiroFish default is Alibaba's `qwen-plus`). The seed brief is
  public information, so sending it out is fine; do not add private code or company documents.

**Memory graph, required:** `ZEP_API_KEY` from [app.getzep.com](https://app.getzep.com/) (free monthly quota). The
seed material and the simulation's memory are stored in Zep's cloud.

Remove the `LLM_BOOST_*` lines unless you use a second model.

## 3. Run

```bash
cd ~/dev/stolen-with-pride/MiroFish && npm run dev
```

Open http://localhost:3000, upload `~/dev/codist-eval/mirofish/seed/codist-brief.md`, and paste a question from
`questions.md`. The backend listens on 5001.

## 4. Reading the result

Treat the report as a rehearsal of opinions, not a measurement: the personas are the model's guesses about people.
Look for objections and ideas we have not thought of, then check them with real developers. Save each report next to
this file as `report-<question>-<date>.md`.
