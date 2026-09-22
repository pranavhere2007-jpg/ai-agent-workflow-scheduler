import gradio as gr
import concurrent.futures
import time
import html

# Import the core components from backend
from orchestrator import planner_decompose, route_task, execute_real_task
from auth_service import auth_manager

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

    # 2. Decompose
    try:
        plan = planner_decompose(prompt)
    except Exception as e:
        yield (
            f"<div class='status-pill error'>❌ Decomposition Error: {html.escape(str(e))}</div>",
            "",
            ""
        )
        return

    # 3. Route Tasks
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

    # 4. Concurrent Execution
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
# Authentication Handlers
# ----------------------------------------------------
def handle_send_otp(email: str):
    if not email or not email.strip():
        return (
            "<div class='status-pill error'>⚠️ Please enter your email address first.</div>",
            gr.update()
        )
    
    success, msg, dev_code = auth_manager.send_otp(email)
    if success:
        if dev_code:
            status_html = f"""
            <div class='status-pill success'>
                {html.escape(msg)}<br>
                <div style="margin-top: 6px; font-family: monospace; font-size: 14px; background: rgba(59, 130, 246, 0.2); padding: 4px 8px; border-radius: 4px; display: inline-block;">
                    🔑 Test OTP: <strong>{dev_code}</strong>
                </div>
            </div>
            """
            return status_html, gr.update(value=dev_code)
        else:
            status_html = f"<div class='status-pill success'>📬 {html.escape(msg)}</div>"
            return status_html, gr.update()
    else:
        status_html = f"<div class='status-pill error'>❌ {html.escape(msg)}</div>"
        return status_html, gr.update()

def handle_verify_otp(email: str, otp_code: str):
    if not email or not email.strip():
        return (
            gr.update(visible=True),  # keep login visible
            gr.update(visible=False), # keep main hidden
            "<div class='status-pill error'>⚠️ Email is missing. Please enter your email and request a code.</div>",
            "",                       # session email
            ""                        # header badge
        )
    if not otp_code or not otp_code.strip():
        return (
            gr.update(visible=True),
            gr.update(visible=False),
            "<div class='status-pill error'>⚠️ Please enter the 6-digit verification code.</div>",
            "",
            ""
        )
    
    verified, msg = auth_manager.verify_otp(email, otp_code)
    if verified:
        badge_html = f"""
        <div style="display: flex; align-items: center; gap: 8px; background: #1e293b; border: 1px solid #334155; padding: 6px 12px; border-radius: 20px; font-size: 12px; color: #cbd5e1;">
            <span style="width: 8px; height: 8px; border-radius: 50%; background: #10b981;"></span>
            <span>👤 {html.escape(email.strip().lower())}</span>
        </div>
        """
        return (
            gr.update(visible=False), # hide login view
            gr.update(visible=True),  # show main dashboard
            "",                       # clear login error
            email.strip().lower(),    # store email in state
            badge_html                # set profile badge
        )
    else:
        return (
            gr.update(visible=True),
            gr.update(visible=False),
            f"<div class='status-pill error'>❌ {html.escape(msg)}</div>",
            "",
            ""
        )

def handle_logout(email: str):
    if email:
        auth_manager.clear_session(email)
    return (
        gr.update(visible=True),  # show login view
        gr.update(visible=False), # hide main dashboard
        "<div class='status-pill success'>👋 You have been logged out successfully.</div>",
        "",                       # clear otp input
        "",                       # clear session email state
        ""                        # clear header badge
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
.login-card {
    max-width: 480px;
    margin: 40px auto !important;
    background: #0f172a;
    border: 1px solid #1e293b;
    border-radius: 16px;
    padding: 24px;
    box-shadow: 0 10px 30px rgba(0,0,0,0.5);
}
"""

with gr.Blocks(css=custom_css, title="Multi-Agent Orchestrator") as demo:
    # State tracking
    session_user_email = gr.State(value="")

    # ==========================================
    # 1. AUTHENTICATION VIEW (Google SMTP OTP)
    # ==========================================
    with gr.Column(visible=True, elem_classes=["login-card"]) as login_view:
        smtp_status_badge = (
            '<span style="background: rgba(16, 185, 129, 0.15); color: #34d399; border: 1px solid #10b98140; padding: 3px 10px; border-radius: 20px; font-size: 11px; font-weight: 600;">📧 Google SMTP Live (smtp.gmail.com:587)</span>'
            if auth_manager.is_smtp_configured() else
            '<span style="background: rgba(245, 158, 11, 0.15); color: #fbbf24; border: 1px solid #f59e0b40; padding: 3px 10px; border-radius: 20px; font-size: 11px; font-weight: 600;">⚙️ Dev Fallback Mode (.env credentials optional)</span>'
        )

        gr.HTML(f"""
        <div style="text-align: center; margin-bottom: 20px;">
            <div style="font-size: 40px; margin-bottom: 8px;">🧠</div>
            <h2 style="color: #f8fafc; font-size: 22px; font-weight: 800; margin: 0 0 6px 0;">
                Autonomous Orchestrator
            </h2>
            <p style="color: #94a3b8; font-size: 13px; margin: 0 0 12px 0;">
                Sign in with your email via Google SMTP One-Time Password
            </p>
            <div>{smtp_status_badge}</div>
        </div>
        """)

        login_status_banner = gr.HTML("")

        with gr.Group():
            email_input = gr.Textbox(
                label="Email Address",
                placeholder="name@example.com (or your @gmail.com)",
                lines=1
            )
            send_otp_btn = gr.Button("📨 Send Verification Code", variant="primary")

        with gr.Group():
            otp_input = gr.Textbox(
                label="6-Digit Verification Code",
                placeholder="Enter 6-digit code received via email",
                lines=1,
                max_lines=1
            )
            with gr.Row():
                verify_btn = gr.Button("🚀 Verify & Enter Workspace", variant="primary", scale=2)
                resend_btn = gr.Button("🔄 Resend Code", variant="secondary", scale=1)

        with gr.Accordion("ℹ️ Google SMTP Configuration Help", open=False):
            gr.Markdown("""
            **How Google SMTP Email Login Works:**
            - Delivery is processed via `smtp.gmail.com:587` with TLS encryption.
            - To connect your Gmail account, add your email and 16-character Google App Password into `.env`:
              ```env
              SMTP_HOST=smtp.gmail.com
              SMTP_PORT=587
              SMTP_USER=your_email@gmail.com
              SMTP_PASSWORD=abcd efgh ijkl mnop
              ```
            - If no `.env` credentials are set, the app runs in **Dev Mode** and generates a clickable/visible test OTP automatically!
            """)

    # ==========================================
    # 2. MAIN APPLICATION DASHBOARD
    # ==========================================
    with gr.Column(visible=False) as main_view:
        # Top Header Bar
        with gr.Row(elem_id="header-bar"):
            with gr.Column(scale=8):
                gr.HTML("""
                <div style="margin-bottom: 14px; padding-top: 8px;">
                    <h1 style="color: #f8fafc; font-size: 24px; font-weight: 800; margin: 0; display: flex; align-items: center; gap: 8px;">
                        <span>🧠</span> Autonomous Multi-Agent Orchestrator
                    </h1>
                    <p style="color: #94a3b8; font-size: 13px; margin: 4px 0 0 0;">
                        Dynamic Prompt Decomposition • Complexity-Cost Routing • Concurrent Execution Fleet
                    </p>
                </div>
                """)
            with gr.Column(scale=4):
                with gr.Row():
                    user_badge = gr.HTML("")
                    logout_btn = gr.Button("🚪 Sign Out", variant="stop", size="sm")

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
                    - **Planner:** Gemini 3.8 Flash (Structured JSON Decomposition)
                    - **Routing Heuristic:** `Score = (Cost × 1000) + (Latency × 1)` constrained by `Complexity ≤ Model Max`
                    - **Execution Fleet:** Groq OSS & Gemini 3.5 Flash via ThreadPool
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

    # ==========================================
    # 3. WIRE AUTHENTICATION ACTIONS
    # ==========================================
    # Send OTP
    send_otp_btn.click(
        fn=handle_send_otp,
        inputs=[email_input],
        outputs=[login_status_banner, otp_input]
    )
    resend_btn.click(
        fn=handle_send_otp,
        inputs=[email_input],
        outputs=[login_status_banner, otp_input]
    )

    # Verify OTP & Login
    verify_btn.click(
        fn=handle_verify_otp,
        inputs=[email_input, otp_input],
        outputs=[login_view, main_view, login_status_banner, session_user_email, user_badge]
    )

    # Logout
    logout_btn.click(
        fn=handle_logout,
        inputs=[session_user_email],
        outputs=[login_view, main_view, login_status_banner, otp_input, session_user_email, user_badge]
    )

if __name__ == "__main__":
    demo.launch(server_name="localhost", server_port=7860)