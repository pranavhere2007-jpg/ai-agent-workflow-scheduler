import gradio as gr
import concurrent.futures
import time
import html

# Import the core components from your orchestrator backend[cite: 2]
from orchestrator import planner_decompose, route_task, execute_real_task

# ----------------------------------------------------
# Helper Functions for Visual Badges & Cards
# ----------------------------------------------------
def get_complexity_badge(score: int) -> str:
    """Returns a styled HTML badge for complexity levels."""
    if score <= 3:
        color = "#10b981"  # Emerald
        bg = "rgba(16, 185, 129, 0.15)"
        label = f"Score {score} (Low)"
    elif score <= 6:
        color = "#f59e0b"  # Amber
        bg = "rgba(245, 158, 11, 0.15)"
        label = f"Score {score} (Medium)"
    else:
        color = "#ef4444"  # Rose
        bg = "rgba(239, 68, 68, 0.15)"
        label = f"Score {score} (High)"
    
    return f'<span style="background:{bg}; color:{color}; border:1px solid {color}40; padding:2px 8px; border-radius:6px; font-weight:600; font-size:11px;">{label}</span>'

def get_model_pill(model_name: str) -> str:
    """Returns a styled pill distinguishing Google Gemini vs Groq vs Local."""
    if "gemini" in model_name.lower():
        color = "#38bdf8"  # Cyan / Sky
        bg = "rgba(56, 189, 248, 0.12)"
    elif "groq" in model_name.lower():
        color = "#fb923c"  # Orange
        bg = "rgba(251, 146, 60, 0.12)"
    else:
        color = "#a855f7"  # Purple
        bg = "rgba(168, 85, 247, 0.12)"

    return f'<span style="background:{bg}; color:{color}; border:1px solid {color}40; padding:2px 8px; border-radius:6px; font-family:monospace; font-size:11px;">{model_name}</span>'

def build_routing_table(plan, routing_map, statuses) -> str:
    """Builds a responsive HTML table for decomposing and routing states."""
    rows = ""
    for task in plan.subtasks:
        model = routing_map.get(task.task_id, "Pending...")
        status = statuses.get(task.task_id, "⏳ Queued")
        
        status_color = "#10b981" if "Completed" in status else ("#f59e0b" if "Running" in status else "#94a3b8")
        
        rows += f"""
        <tr style="border-bottom: 1px solid #1e293b;">
            <td style="padding: 10px 12px; font-weight: 700; color: #f8fafc;">#{task.task_id}</td>
            <td style="padding: 10px 12px; color: #cbd5e1; font-size: 13px;">{html.escape(task.description)}</td>
            <td style="padding: 10px 12px;">{get_complexity_badge(task.complexity)}</td>
            <td style="padding: 10px 12px;">{get_model_pill(model)}</td>
            <td style="padding: 10px 12px; font-size: 12px; font-weight: 600; color: {status_color};">{status}</td>
        </tr>
        """
        
    return f"""
    <div style="overflow-x:auto; border-radius: 10px; border: 1px solid #334155; background: #0f172a; margin-top: 10px;">
        <table style="width:100%; border-collapse: collapse; text-align: left; font-family: inherit;">
            <thead style="background: #1e293b; color: #94a3b8; font-size: 11px; text-transform: uppercase; letter-spacing: 0.05em;">
                <tr>
                    <th style="padding: 10px 12px;">ID</th>
                    <th style="padding: 10px 12px;">Subtask Description</th>
                    <th style="padding: 10px 12px;">Complexity</th>
                    <th style="padding: 10px 12px;">Assigned Model</th>
                    <th style="padding: 10px 12px;">Status</th>
                </tr>
            </thead>
            <tbody>
                {rows}
            </tbody>
        </table>
    </div>
    """

def build_results_view(plan, routing_map, results) -> str:
    """Builds clean deliverable cards for each completed worker subtask."""
    if not results:
        return "<p style='color:#64748b; font-size:13px; font-style:italic;'>Awaiting execution outputs...</p>"
        
    cards = ""
    for task in plan.subtasks:
        if task.task_id in results:
            output = results[task.task_id]
            is_err = output.startswith("Error:")
            border_color = "#ef4444" if is_err else "#334155"
            bg_header = "rgba(239, 68, 68, 0.08)" if is_err else "#1e293b"
            
            cards += f"""
            <div style="border: 1px solid {border_color}; border-radius: 8px; margin-bottom: 14px; overflow: hidden; background: #0b1329;">
                <div style="background: {bg_header}; padding: 10px 14px; display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #1e293b;">
                    <span style="font-weight: 700; color: #f8fafc; font-size: 13px;">Task #{task.task_id}: {html.escape(task.description[:60])}{'...' if len(task.description)>60 else ''}</span>
                    <div>{get_model_pill(routing_map.get(task.task_id, ''))}</div>
                </div>
                <div style="padding: 14px; font-family: monospace; font-size: 12px; color: #e2e8f0; white-space: pre-wrap; line-height: 1.5; background: #0a0f1d;">
                    {html.escape(output)}
                </div>
            </div>
            """
    return cards

# ----------------------------------------------------
# Main Orchestrator Streaming Pipeline
# ----------------------------------------------------
def run_orchestrator_pipeline(prompt):
    if not prompt.strip():
        yield (
            "<div class='status-pill error'>⚠️ Please enter a valid prompt to begin.</div>",
            "",
            ""
        )
        return

    start_time = time.time()
    
    # 1. State Initializing
    yield (
        "<div class='status-pill working'>⚡ Stage 1/3: Analyzing prompt and decomposing into subtasks...</div>",
        "<p style='color:#64748b;'>Querying the Planner LLM for structured task graph...</p>",
        ""
    )

    # 2. Decompose[cite: 2]
    try:
        plan = planner_decompose(prompt)
    except Exception as e:
        yield (
            f"<div class='status-pill error'>❌ Decomposition Error: {html.escape(str(e))}</div>",
            "",
            ""
        )
        return

    # 3. Route Tasks[cite: 2]
    routing_map = {}
    task_statuses = {}
    for task in plan.subtasks:
        assigned = route_task(task)
        routing_map[task.task_id] = assigned
        task_statuses[task.task_id] = "⏳ Queued"

    routing_html = build_routing_table(plan, routing_map, task_statuses)
    yield (
        f"<div class='status-pill working'>🔀 Stage 2/3: Planned {len(plan.subtasks)} subtasks. Dispatched to workers...</div>",
        routing_html,
        ""
    )

    # 4. Concurrent Execution[cite: 2]
    results = {}
    with concurrent.futures.ThreadPoolExecutor() as executor:
        future_to_task = {}
        for task in plan.subtasks:
            task_statuses[task.task_id] = "⚡ Running"
            future = executor.submit(execute_real_task, task, routing_map[task.task_id])
            future_to_task[future] = task.task_id

        # Update table with running state
        yield (
            f"<div class='status-pill working'>⚡ Stage 3/3: Running {len(plan.subtasks)} models concurrently...</div>",
            build_routing_table(plan, routing_map, task_statuses),
            ""
        )

        for future in concurrent.futures.as_completed(future_to_task):
            task_id = future_to_task[future]
            try:
                result = future.result()
                results[task_id] = result
                task_statuses[task_id] = "✅ Completed"
            except Exception as exc:
                results[task_id] = f"Error: {str(exc)}"
                task_statuses[task_id] = "❌ Failed"

            # Stream incremental execution progress
            yield (
                f"<div class='status-pill working'>⚡ Running... {len(results)}/{len(plan.subtasks)} tasks complete</div>",
                build_routing_table(plan, routing_map, task_statuses),
                build_results_view(plan, routing_map, results)
            )

    elapsed = round(time.time() - start_time, 2)
    final_banner = f"<div class='status-pill success'>🎉 Pipeline execution completed in {elapsed}s across {len(plan.subtasks)} tasks.</div>"
    
    yield (
        final_banner,
        build_routing_table(plan, routing_map, task_statuses),
        build_results_view(plan, routing_map, results)
    )

# ----------------------------------------------------
# Gradio UI Shell & Custom Dark Styling
# ----------------------------------------------------
custom_css = """
body, .gradio-container {
    background-color: #030712 !important;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
}
.status-pill {
    padding: 10px 16px;
    border-radius: 8px;
    font-size: 13px;
    font-weight: 600;
    margin-bottom: 12px;
}
.status-pill.working {
    background: rgba(59, 130, 246, 0.15);
    border: 1px solid rgba(59, 130, 246, 0.35);
    color: #60a5fa;
}
.status-pill.success {
    background: rgba(16, 185, 129, 0.15);
    border: 1px solid rgba(16, 185, 129, 0.35);
    color: #34d399;
}
.status-pill.error {
    background: rgba(239, 68, 68, 0.15);
    border: 1px solid rgba(239, 68, 68, 0.35);
    color: #f87171;
}
.preset-btn {
    font-size: 11px !important;
    padding: 4px 8px !important;
}
"""

with gr.Blocks(css=custom_css, title="Multi-Agent Orchestrator") as demo:
    with gr.Row():
        gr.HTML("""
        <div style="margin-bottom: 18px; padding-top: 8px;">
            <h1 style="color: #f8fafc; font-size: 24px; font-weight: 800; margin: 0; display: flex; align-items: center; gap: 8px;">
                <span>🧠</span> Autonomous Multi-Agent Orchestrator
            </h1>
            <p style="color: #94a3b8; font-size: 13px; margin: 4px 0 0 0;">
                Dynamic Prompt Decomposition • Complexity-Cost Routing • Concurrent Mock Execution
            </p>
        </div>
        """)

    with gr.Row():
        # LEFT COLUMN: Prompt inputs & Configurations
        with gr.Column(scale=4):
            with gr.Group():
                prompt_input = gr.Textbox(
                    label="User Prompt",
                    lines=4,
                    placeholder="Describe a multi-faceted goal (e.g. Plan a trip to Mumbai, book flights, and draft an absence email)...",
                    value="Plan a trip to Mumbai and apply for a 3 week vacation in my office"
                )
                
                with gr.Row():
                    run_btn = gr.Button("🚀 Launch Pipeline", variant="primary", scale=2)
                    clear_btn = gr.ClearButton([prompt_input], value="Clear", scale=1)

            gr.Markdown("**Quick Presets:**")
            with gr.Row():
                preset_1 = gr.Button("✈️ Trip & Vacation", elem_classes=["preset-btn"])
                preset_2 = gr.Button("💻 Tech Migration", elem_classes=["preset-btn"])
                preset_3 = gr.Button("🎉 Team Event", elem_classes=["preset-btn"])

            preset_1.click(lambda: "Plan a trip to Mumbai, reserve hotel, and send a 3-week leave notice to HR", outputs=prompt_input)
            preset_2.click(lambda: "Audit our MySQL database for high latency queries and write a migration proposal to PostgreSQL", outputs=prompt_input)
            preset_3.click(lambda: "Organize an offsite retreat in Goa for 15 engineers: book stay, agenda outline, and budget breakdown", outputs=prompt_input)

            with gr.Accordion("ℹ️ Active Engine Architecture", open=False):
                gr.Markdown("""
                - **Planner:** Gemini 3.8 Flash (Structured JSON Decomposition)[cite: 2]
                - **Routing Heuristic:** `Score = (Cost × 1000) + (Latency × 1)` constrained by `Complexity ≤ Model Max`[cite: 2]
                - **Execution Fleet:** Groq OSS & Gemini 3.5 Flash via ThreadPool[cite: 2]
                """)

        # RIGHT COLUMN: Interactive Status, Table & Deliverable Cards
        with gr.Column(scale=6):
            status_banner = gr.HTML("<div class='status-pill' style='background:#1e293b; color:#94a3b8;'>Ready. Enter a prompt and launch.</div>")
            
            with gr.Tabs():
                with gr.TabItem("📋 Task Pipeline & Routing"):
                    routing_display = gr.HTML("<p style='color:#64748b; font-size:13px; font-style:italic;'>Pipeline is idle.</p>")
                with gr.TabItem("📦 Generated Deliverables"):
                    results_display = gr.HTML("<p style='color:#64748b; font-size:13px; font-style:italic;'>Deliverable artifacts will render here as worker models finish.</p>")

    # Wire execution
    run_btn.click(
        fn=run_orchestrator_pipeline,
        inputs=prompt_input,
        outputs=[status_banner, routing_display, results_display]
    )

if __name__ == "__main__":
    demo.launch(server_name="localhost", server_port=7860)