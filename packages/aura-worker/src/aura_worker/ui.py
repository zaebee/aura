import os
import asyncio
import logging
import secrets

import gradio as gr
from dotenv import load_dotenv

from .metabolism import HiveLogHandler, MetabolicLoop
from .node import AuraNode
from .tunnel import Umbilical


class WorkerState:
    def __init__(self):
        self.node = AuraNode()
        self.log_handler: HiveLogHandler | None = None
        self.metabolism: MetabolicLoop | None = None
        self.umbilical: Umbilical | None = None
        self.worker_id = secrets.token_hex(4)


def launch_interactive_node():
    load_dotenv()

    # Env Var Overrides
    ENV_HIVE_HOST = os.getenv("AURA_WORKER__HIVE_HOST", "hub.zae.life")
    ENV_FRP_TOKEN = os.getenv("AURA_WORKER__FRP_TOKEN", "")
    ENV_PUNK_KEY = os.getenv("AURA_WORKER__PUNK_KEY", "")

    state = WorkerState()

    def log(message):
        print(message)
        if state.log_handler:
            state.log_handler.write(message)

    async def start_node(model, hive_host, frp_token, punk_key, frp_port, progress=None):
        if progress is None:
            progress = gr.Progress()
        if state.node.is_running:
            return "Node is already running."

        try:
            progress(0, desc="Starting Ollama...")
            state.node.start_ollama(log_callback=log)

            progress(0.3, desc=f"Pulling model {model}...")
            state.node.pull_model(model, log_callback=log)

            progress(0.7, desc="Establishing Umbilical...")
            state.umbilical = Umbilical(
                hive_host=hive_host,
                frp_token=frp_token,
                punk_key=punk_key,
                frp_port=int(frp_port),
                worker_id=state.worker_id
            )
            state.umbilical.start(log_callback=log)

            # Initialize Log Protein and Metabolic Loop
            progress(0.8, desc="Synchronizing with Hive Bloodstream...")
            state.log_handler = HiveLogHandler(worker_name=state.worker_id)
            state.metabolism = MetabolicLoop(worker_name=state.worker_id)

            # Setup standard logging to capture all info/error calls
            root_logger = logging.getLogger()
            root_logger.addHandler(state.log_handler)
            root_logger.setLevel(logging.INFO)

            await state.log_handler.start()
            await state.metabolism.start(kill_callback=stop_node)

            state.node.is_running = True
            state.node.status = "Connected"
            return "Node Started Successfully!"
        except Exception as e:
            log(f"Error starting node: {e}")
            await stop_node()
            return f"Error: {e}"

    async def stop_node():
        log("--- Stopping Aura Node ---")

        if state.metabolism:
            await state.metabolism.stop()
            state.metabolism = None

        if state.log_handler:
            # Remove from root logger
            logging.getLogger().removeHandler(state.log_handler)
            await state.log_handler.stop()
            state.log_handler = None

        if state.umbilical:
            state.umbilical.stop()
            state.umbilical = None

        state.node.stop_ollama()
        state.node.is_running = False
        state.node.status = "Idle"
        return "Node Stopped"

    def refresh_ui():
        status = state.node.get_status()
        nats_status = "🔴 Offline"

        if state.metabolism and state.metabolism.is_connected:
            nats_status = "🟢 Connected (Pulse Active)"
        elif state.node.is_running:
            nats_status = "🟠 Pending (Connecting...)"

        if state.node.is_running:
            # Check if processes are still alive
            if (
                state.node.ollama_process
                and state.node.ollama_process.poll() is not None
            ):
                state.node.status = "Error: Ollama process stopped"
                state.node.is_running = False
            elif state.umbilical and not state.umbilical.is_alive:
                state.node.status = "Error: Umbilical process stopped"
                state.node.is_running = False

        logs = state.log_handler.get_logs() if state.log_handler else "Logs pending..."
        return status, nats_status, state.node.requests_processed, logs

    with gr.Blocks(title="Aura Node", theme=gr.themes.Soft()) as demo:
        gr.Markdown("# 🐝 Aura Interactive Worker Node")
        gr.Markdown(
            "**Disclaimer:** For Research & Development Use Only. Do not use for commercial hosting."
        )

        with gr.Row():
            with gr.Column(scale=1):
                status_label = gr.Label(
                    value=state.node.get_status(), label="Brain Status"
                )
                nats_label = gr.Label(
                    value="🔴 Offline", label="NATS Pulse"
                )
                stats_box = gr.Number(
                    value=state.node.requests_processed, label="Requests Processed"
                )
            with gr.Column(scale=2):
                with gr.Row():
                    model_input = gr.Textbox(value="mistral", label="Ollama Model")
                    hive_host_input = gr.Textbox(
                        value=ENV_HIVE_HOST, label="HIVE_HOST (Anchor)"
                    )
                with gr.Row():
                    frp_token_input = gr.Textbox(
                        value=ENV_FRP_TOKEN, label="FRP_TOKEN", type="password"
                    )
                    punk_key_input = gr.Textbox(
                        value=ENV_PUNK_KEY, label="PUNK_KEY (Secret)", type="password"
                    )
                with gr.Row():
                    frp_port_input = gr.Number(value=7000, label="FRP Port", precision=0)

        with gr.Row():
            start_btn = gr.Button("Start Node", variant="primary")
            stop_btn = gr.Button("Stop Node", variant="stop")

        log_output = gr.Textbox(
            lines=15, label="Agent Thinking / Logs", interactive=False
        )

        timer = gr.Timer(2)
        timer.tick(refresh_ui, outputs=[status_label, nats_label, stats_box, log_output])

        start_btn.click(
            start_node,
            inputs=[
                model_input,
                hive_host_input,
                frp_token_input,
                punk_key_input,
                frp_port_input,
            ],
            outputs=[log_output],
        )
        stop_btn.click(stop_node, outputs=[log_output])

    demo.launch(share=True, inline=False)
