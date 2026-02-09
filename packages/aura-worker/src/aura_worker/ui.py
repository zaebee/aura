import os
import secrets
import gradio as gr
from dotenv import load_dotenv
from .node import AuraNode
from .tunnel import Umbilical
from .metabolism import HiveLogHandler

def launch_interactive_node():
    load_dotenv()

    # Env Var Overrides
    ENV_HIVE_HOST = os.getenv("AURA_WORKER__HIVE_HOST", "hub.zae.life")
    ENV_FRP_TOKEN = os.getenv("AURA_WORKER__FRP_TOKEN", "")
    ENV_PUNK_KEY = os.getenv("AURA_WORKER__PUNK_KEY", "")

    node = AuraNode()
    log_handler = HiveLogHandler()
    umbilical = [None]  # Using list to hold reference in closures

    def log(message):
        print(message)
        log_handler.write(message)

    def start_node(model, hive_host, frp_token, punk_key, frp_port, progress=gr.Progress()):
        if node.is_running:
            return "Node is already running."

        try:
            progress(0, desc="Starting Ollama...")
            node.start_ollama(log_callback=log)

            progress(0.3, desc=f"Pulling model {model}...")
            node.pull_model(model, log_callback=log)

            progress(0.7, desc="Establishing Umbilical...")
            umbilical[0] = Umbilical(
                hive_host=hive_host,
                frp_token=frp_token,
                punk_key=punk_key,
                frp_port=int(frp_port)
            )
            umbilical[0].start(log_callback=log)

            node.is_running = True
            node.status = "Connected"
            return "Node Started Successfully!"
        except Exception as e:
            log(f"Error starting node: {e}")
            stop_node()
            return f"Error: {e}"

    def stop_node():
        log("--- Stopping Aura Node ---")
        if umbilical[0]:
            umbilical[0].stop()
            umbilical[0] = None

        node.stop_ollama()
        node.is_running = False
        node.status = "Idle"
        return "Node Stopped"

    def refresh_ui():
        status = node.get_status()
        if node.is_running:
            # Check if processes are still alive
            if node.ollama_process and node.ollama_process.poll() is not None:
                node.status = "Error: Ollama process stopped"
                node.is_running = False
            elif umbilical[0] and not umbilical[0].is_alive:
                node.status = "Error: Umbilical process stopped"
                node.is_running = False

        return status, node.requests_processed, log_handler.get_logs()

    with gr.Blocks(title="Aura Node", theme=gr.themes.Soft()) as demo:
        gr.Markdown("# 🐝 Aura Interactive Worker Node")
        gr.Markdown(
            "**Disclaimer:** For Research & Development Use Only. Do not use for commercial hosting."
        )

        with gr.Row():
            with gr.Column(scale=1):
                status_label = gr.Label(value=node.get_status(), label="Brain Status")
                stats_box = gr.Number(
                    value=node.requests_processed, label="Requests Processed"
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
                    frp_port_input = gr.Textbox(value="7000", label="FRP Port")

        with gr.Row():
            start_btn = gr.Button("Start Node", variant="primary")
            stop_btn = gr.Button("Stop Node", variant="stop")

        log_output = gr.Textbox(lines=15, label="Agent Thinking / Logs", interactive=False)

        timer = gr.Timer(2)
        timer.tick(refresh_ui, outputs=[status_label, stats_box, log_output])

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
