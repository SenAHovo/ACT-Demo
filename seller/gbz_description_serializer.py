"""
GB/Z 185.4 描述序列化器

将统一描述映射为 GB/Z 185.4 字段描述。
"""

from .canonical_agent_description import get_canonical_description


def get_gbz_description() -> dict:
    desc = get_canonical_description()
    return {
        "agent_profile": {
            "agent_id": desc["agent_id"],
            "agent_id_scheme": desc["agent_id_scheme"],
            "agent_name": desc["name"],
            "description": desc["description"],
        },
        "capability_profile": {
            "services": [
                {
                    "service_id": s["skill_id"],
                    "service_name": s["name"],
                    "service_description": s["description"],
                }
                for s in desc["capabilities"]["skills"]
            ],
            "supported_interaction_protocols": ["GBZ_185_6"],
        },
        "security_profile": {
            "authentication_methods": ["local_credential"],
            "credential_type": "Ed25519",
            "signature_algorithm": "Ed25519",
        },
        "discovery_endpoint": f"{desc['service_endpoint']}/.well-known/agent-description.json",
        "agent_card_endpoint": f"{desc['service_endpoint']}/.well-known/agent-card.json",
    }
