# --- Ground Truth Labeling (Step 3) ---
# Do NOT use production output as expected for failing examples.
# Use an LLM judge to generate correct expected values.
import openai, os

client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def generate_ground_truth(input_value: dict, system_context: str) -> str:
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {
                "role": "system",
                "content": (
                    f"{system_context}\n\n"
                    "Given the input below, produce the ideal correct output. "
                    "Be concise and faithful to what the agent should do."
                )
            },
            {"role": "user", "content": str(input_value)}
        ]
    )
    return response.choices[0].message.content


# --- Deterministic Train/Validation Split (Step 4) ---
# Same row always lands in same split across flywheel iterations.
import hashlib

TRAIN_FRACTION = 0.8

def assign_split(row_id: str, seed: str = "flywheel-v1") -> str:
    hash_val = hashlib.sha256(f"{seed}:{row_id}".encode()).hexdigest()
    return "train" if int(hash_val, 16) % 100 < (TRAIN_FRACTION * 100) else "validation"


# --- Dataset Insert with Metadata (Step 5) ---
import braintrust

braintrust.login(api_key=os.getenv("BRAINTRUST_API_KEY"))
dataset = braintrust.init_dataset(project="<project-name>", name="<dataset-name>")

for row in labeled_rows:
    split = assign_split(row["trace_id"])
    dataset.insert({
        "input": row["input"],
        "expected": row["expected"],
        "tags": ["production", "flywheel-curated", split, row["bucket"]],
        "metadata": {
            "source_trace_id": row["trace_id"],
            "source_project_id": "<PROJECT_ID>",
            "production_score": row["score"],
            "bucket": row["bucket"],          # "passing" | "failing"
            "split": split,
            "labeler_model": "gpt-4o",
            "flywheel_iteration": "<current_iteration>"
        }
    })


# --- Filter to Validation Split in Eval File (Step 6) ---
dataset = braintrust.init_dataset(project="<project-name>", name="<dataset-name>")
rows = [r for r in dataset.fetch() if r.get("metadata", {}).get("split") == "validation"]
