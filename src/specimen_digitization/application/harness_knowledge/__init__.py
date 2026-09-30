"""Each subcollection's harness knowledge (G29), named by the profile by id and
version; the pilot has the Insects knowledge only."""

from . import insects

KNOWLEDGE = {insects.KNOWLEDGE_ID: insects}


def instructions_for(prompt_text: str, knowledge_id: str, version: str) -> str:
    """The pinned prompt followed by the profile's harness knowledge; a
    knowledge id or version the code does not have is refused."""
    knowledge = KNOWLEDGE.get(knowledge_id)
    if knowledge is None or knowledge.KNOWLEDGE_VERSION != version:
        raise ValueError(f"harness_knowledge_unavailable:{knowledge_id}:{version}")
    return prompt_text + "\n\n" + knowledge.render()
