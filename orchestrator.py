import os
import time
import json
from typing import List
from pydantic import BaseModel, Field
import concurrent.futures
from dotenv import load_dotenv
from litellm import completion

# Load environment variables from the .env file
load_dotenv()

# ==========================================
# 1. DEFINE DATA STRUCTURES (PYDANTIC)
# ==========================================
class Subtask(BaseModel):
    task_id: int = Field(description="Unique ID for the subtask")
    description: str = Field(description="Clear instruction for the task")
    complexity: int = Field(description="Complexity score from 1 (simple text processing) to 10 (complex reasoning)")
    dependencies: List[int] = Field(default_factory=list, description="IDs of tasks that must be completed first")

class TaskPlan(BaseModel):
    subtasks: List[Subtask] = Field(description="List of subtasks required to fulfill the user prompt")

# ==========================================
# 2. MODEL REGISTRY (Gemini & Groq Only)
# ==========================================
MODEL_REGISTRY = {
    "gemini/gemini-3.8-flash": {"cost_per_1k": 0.0015, "latency_ms": 1200, "max_complexity": 10},
    "gemini/gemini-3.5-flash-lite": {"cost_per_1k": 0.00015, "latency_ms": 500, "max_complexity": 7},
    "groq/openai/gpt-oss-20b": {"cost_per_1k": 0.000075, "latency_ms": 200, "max_complexity": 5},
}

# ==========================================
# 3. ENGINE COMPONENTS
# ==========================================

def planner_decompose(prompt: str) -> TaskPlan:
    """
    Role: Breaks down the user prompt into subtasks using a high-reasoning LLM.
    """
    print(f"\n[PLANNER] Analyzing prompt: '{prompt}'")
    
    # Generate the JSON schema dynamically from the Pydantic model
    try:
        schema = TaskPlan.model_json_schema() # Pydantic v2
    except AttributeError:
        schema = TaskPlan.schema_json() # Pydantic v1
        
    system_prompt = (
        "You are an orchestration planner. Break down the user's prompt into a logical sequence of subtasks. "
        "Assign a complexity score from 1-10 (1=simple text formatting/extraction, 10=heavy reasoning/logic). "
        f"You MUST return ONLY a valid JSON object that strictly matches this schema:\n{json.dumps(schema)}"
    )
    
    # Make the API call to a highly capable Gemini model for planning
    response = completion(
        model="gemini/gemini-3.8-flash",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ],
        # LiteLLM supports forcing JSON output for Gemini natively
        response_format={"type": "json_object"} 
    )
    
    response_content = response.choices[0].message.content
    try:
        return TaskPlan.model_validate_json(response_content) # Pydantic v2
    except AttributeError:
        return TaskPlan.parse_raw(response_content) # Pydantic v1

def route_task(subtask: Subtask) -> str:
    """
    Role: Selects the best model based on complexity, cost, and latency weights.
    """
    best_model = None
    best_score = float('inf')

    # Weights for our routing formula
    WEIGHT_COST = 1000 
    WEIGHT_LATENCY = 1

    for model_name, stats in MODEL_REGISTRY.items():
        # Step 1: Can the model handle the complexity?
        if stats["max_complexity"] < subtask.complexity:
            continue
        
        # Step 2: Calculate suitability score (Lower is better)
        score = (stats["cost_per_1k"] * WEIGHT_COST) + (stats["latency_ms"] * WEIGHT_LATENCY)
        
        if score < best_score:
            best_score = score
            best_model = model_name

    # Fallback to the most capable model if routing fails
    return best_model or "gemini/gemini-3.8-flash" 

def execute_real_task(subtask: Subtask, model_name: str) -> str:
    """
    Role: Sends the task to the selected model with instructions to return a MOCK output.
    """
    print(f"[{model_name.upper()}] Executing Task {subtask.task_id}: {subtask.description}")
    
    system_prompt = (
        "You are a backend mock server. Return a realistic mocked confirmation for the requested task. "
        "E.g., if asked to book a ticket, return 'Ticket booked at [time] on [day]'. Do not converse."
    )
    
    response = completion(
        model=model_name,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": subtask.description}
        ]
    )
    return response.choices[0].message.content

# ==========================================
# 4. ORCHESTRATOR
# ==========================================
def process_user_prompt(prompt: str):
    # 1. Decompose
    plan = planner_decompose(prompt)
    print(f"[PLANNER] Generated {len(plan.subtasks)} subtasks.\n")

    results = {}
    
    # 2. Execute Tasks (Parallel execution for tasks without dependencies)
    with concurrent.futures.ThreadPoolExecutor() as executor:
        future_to_task = {}
        for task in plan.subtasks:
            # Route to find the best model
            selected_model = route_task(task)
            print(f"[ROUTER] Task {task.task_id} (Complexity: {task.complexity}) -> Routed to {selected_model}")
            
            # Submit for execution
            future = executor.submit(execute_real_task, task, selected_model)
            future_to_task[future] = task.task_id

        # 3. Aggregate Results
        for future in concurrent.futures.as_completed(future_to_task):
            task_id = future_to_task[future]
            try:
                result = future.result()
                results[task_id] = result
            except Exception as exc:
                results[task_id] = f"Task generated an exception: {exc}"

    print("\n[AGGREGATOR] Final Combined Output:")
    for task_id, output in sorted(results.items()):
        print(f"Task {task_id}: {output}")

# ==========================================
# RUN THE SYSTEM
# ==========================================
if __name__ == "__main__":
    user_input = "Plan a trip to Hyd and draft an email to my boss asking for leave."
    process_user_prompt(user_input)