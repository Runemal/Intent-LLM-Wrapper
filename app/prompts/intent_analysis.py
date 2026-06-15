from jinja2 import Template

from app.schemas.intent import DialogMessage


def intent_analysis_prompt(query: str, history: list[DialogMessage]) -> str:
    template_string = """\
### Current user request

{{ query }}

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
    return template.render(query=query, history=history).strip()
