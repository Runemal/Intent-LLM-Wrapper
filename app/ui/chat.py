import gradio as gr
import httpx

ChatHistory = list[dict[str, str]]


def build_chat_ui(api_base_url: str, *, request_timeout_seconds: float = 120.0) -> gr.Blocks:
    async def submit_message(
        message: str,
        history: ChatHistory,
    ) -> tuple[str, ChatHistory, ChatHistory]:
        if not message.strip():
            return "", history, history

        api_history = _normalize_history(history)
        async with httpx.AsyncClient(
            base_url=api_base_url, timeout=request_timeout_seconds
        ) as client:
            response = await client.post(
                "/api/v1/message",
                json={"query": message, "history": api_history[-20:]},
            )
            if response.is_error:
                answer = f"API error {response.status_code}: {response.text}"
            else:
                data = response.json()
                answer = (
                    f"{data['answer']}\n\n"
                    f"intent: `{data['intent']}`\n"
                    f"confidence: `{data['confidence']}`\n"
                    f"needs_clarification: `{data['needs_clarification']}`"
                )

        updated_history = [
            *history,
            {"role": "user", "content": message},
            {"role": "assistant", "content": answer},
        ]
        return "", updated_history, updated_history

    def clear_history() -> tuple[ChatHistory, ChatHistory]:
        return [], []

    with gr.Blocks(title="Intent LLM Wrapper") as demo:
        state = gr.State([])
        chatbot = gr.Chatbot(label="Intent LLM Wrapper")
        with gr.Row():
            textbox = gr.Textbox(
                placeholder="Enter your request...",
                show_label=False,
                scale=7,
            )
            clear = gr.Button("Clear", scale=1)

        textbox.submit(
            fn=submit_message,
            inputs=[textbox, state],
            outputs=[textbox, chatbot, state],
        )
        clear.click(fn=clear_history, outputs=[chatbot, state])

    return demo


def _normalize_history(history: list[object]) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    for item in history:
        if isinstance(item, dict):
            role = item.get("role")
            content = _clean_content(item.get("content"))
            if role in {"user", "assistant"} and content:
                messages.append({"role": role, "content": content})
            continue

        if isinstance(item, (list, tuple)) and len(item) >= 2:
            user_text, assistant_text = item[0], item[1]
            user_text = _clean_content(user_text)
            assistant_text = _clean_content(assistant_text)
            if user_text:
                messages.append({"role": "user", "content": user_text})
            if assistant_text:
                messages.append({"role": "assistant", "content": assistant_text})

    return messages


def _clean_content(content: object) -> str | None:
    if not isinstance(content, str):
        return None

    lines = []
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith(("intent:", "confidence:", "needs_clarification:")):
            continue
        lines.append(line)

    cleaned = "\n".join(lines).strip()
    return cleaned or None
