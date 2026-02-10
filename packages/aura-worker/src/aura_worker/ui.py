import os

import gradio as gr
from dotenv import load_dotenv

from .controller import WorkerController


def launch_interactive_node():
    """
    Launches the Aura Interactive Worker Node UI.
    Utilizes Async Metabolism for non-blocking execution in Colab/Jupyter.
    """
    load_dotenv()

    # Env Var Overrides
    ENV_HIVE_HOST = os.getenv("AURA_WORKER__HIVE_HOST", "hub.zae.life")
    ENV_FRP_TOKEN = os.getenv("AURA_WORKER__FRP_TOKEN", "")
    ENV_PUNK_KEY = os.getenv("AURA_WORKER__PUNK_KEY", "")
    ENV_NATS_URL = os.getenv("AURA_WORKER__NATS_URL", "nats://localhost:4222")

    controller = WorkerController()

    async def refresh_ui():
        node_status, nats_status, requests_processed = await controller.get_status()
        logs = await controller.get_ui_logs()
        return node_status, nats_status, requests_processed, logs

    with gr.Blocks(title="Aura Node", theme=gr.themes.Soft()) as demo:
        gr.Markdown("# 🐝 Aura Interactive Worker Node")
        gr.Markdown(
            "**Disclaimer:** For Research & Development Use Only. Do not use for commercial hosting."
        )

        with gr.Row():
            with gr.Column(scale=1):
                status_label = gr.Label(value="Idle", label="Brain Status")
                nats_label = gr.Label(value="🔴 Offline", label="NATS Pulse")
                stats_box = gr.Number(value=0, label="Requests Processed")
            with gr.Column(scale=2):
                with gr.Row():
                    model_input = gr.Textbox(value="mistral", label="Ollama Model")
                    hive_host_input = gr.Textbox(
                        value=ENV_HIVE_HOST, label="HIVE_HOST (Anchor)"
                    )
                    nats_url_input = gr.Textbox(
                        value=ENV_NATS_URL, label="NATS_URL (Bloodstream)"
                    )
                with gr.Row():
                    frp_token_input = gr.Textbox(
                        value=ENV_FRP_TOKEN, label="FRP_TOKEN", type="password"
                    )
                    punk_key_input = gr.Textbox(
                        value=ENV_PUNK_KEY, label="PUNK_KEY (Secret)", type="password"
                    )
                with gr.Row():
                    frp_port_input = gr.Number(
                        value=7000, label="FRP Port", precision=0
                    )

        with gr.Row():
            start_btn = gr.Button("Start Node", variant="primary")
            stop_btn = gr.Button("Stop Node", variant="stop")
            test_pulse_btn = gr.Button("Test Pulse", variant="secondary")

        log_output = gr.Textbox(
            lines=15,
            label="Agent Thinking / Logs",
            interactive=False,
            placeholder="Logs will appear here once the node starts...",
        )

        timer = gr.Timer(2)
        timer.tick(refresh_ui, outputs=[status_label, nats_label, stats_box, log_output])

        start_btn.click(
            controller.start,
            inputs=[
                model_input,
                hive_host_input,
                nats_url_input,
                frp_token_input,
                punk_key_input,
                frp_port_input,
            ],
            outputs=[log_output],
        )
        stop_btn.click(controller.stop, outputs=[log_output])
        test_pulse_btn.click(controller.test_pulse, outputs=[log_output])

    # Use prevent_thread_lock=True to allow the notebook to continue executing other cells
    demo.launch(share=True, inline=False, prevent_thread_lock=True)
