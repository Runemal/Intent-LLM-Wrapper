from jinja2 import Template

from app.schemas.intent import DialogMessage, IntentSegment


def response_generation_prompt(
    *,
    query: str,
    history: list[DialogMessage],
    intent_analysis: IntentSegment,
    language: str,
) -> str:
    template_string = """\
### Intent analysis result

intent: {{ intent_analysis.intent.value }}
language: {{ language }}
confidence: {{ intent_analysis.confidence }}
reasoning: {{ intent_analysis.reasoning }}
weather_location: {{ intent_analysis.weather_location }}

### Current user request

{{ query }}

Respond in: {{ language }}

### Dialogue history

{% if history %}
{% for message in history %}
- {{ message.role }}: {{ message.content }}
{% endfor %}
{% else %}
No previous messages.
{% endif %}
"""
    template = Template(template_string)
    return template.render(
        query=query,
        history=history,
        intent_analysis=intent_analysis,
        language=language,
    ).strip()
