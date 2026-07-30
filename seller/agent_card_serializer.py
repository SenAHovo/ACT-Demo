"""
类 A2A Agent Card 序列化器

将统一描述序列化为类 A2A Agent Card 格式（案例自定义结构，非 Google A2A 标准）。
"""

from .canonical_agent_description import get_canonical_description


def get_agent_card() -> dict:
    desc = get_canonical_description()
    return {
        "name": desc["name"],
        "description": desc["description"],
        "url": desc["service_endpoint"],
        "version": desc["version"],
        "capabilities": {
            "skills": [
                {
                    "id": s["skill_id"],
                    "name": s["name"],
                    "description": s["description"],
                }
                for s in desc["capabilities"]["skills"]
            ],
            "payment": desc["capabilities"]["payment"],
            "a2a": {
                "protocol": "A2A/v1",
                "taskEndpoint": f"{desc['service_endpoint']}/v1/a2a/tasks",
                "messageEndpoint": f"{desc['service_endpoint']}/v1/a2a/tasks/{{taskId}}/messages",
                "artifactEndpoint": f"{desc['service_endpoint']}/v1/a2a/tasks/{{taskId}}/artifacts",
            },
        },
        "defaultInputModes": ["text", "application/json"],
        "defaultOutputModes": ["text", "application/json"],
        "authentication": desc["authentication"],
    }
